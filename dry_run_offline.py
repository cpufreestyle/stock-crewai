"""离线干跑：不调用任何 LLM，只验证 数据层 -> 任务装配 -> prompt 体量 这条链路。

用途：端到端一次要几十分钟，任何装配期异常（数据源抛错、任务参数缺失）
都应该在这里先暴露，而不是在 Crew 跑到第 5 个任务时才炸。
"""
from dotenv import load_dotenv
load_dotenv()

import crew
from agents.market_watcher import MarketWatcherAgent
from agents.researcher import ResearcherAgent
from agents.sentiment_agent import SentimentAgent
from agents.backtest_agent import BacktestAgent
from agents.risk_manager_agent import RiskManagerAgent
from agents.trader import TraderAgent
from agents.portfolio_rebalancer import PortfolioRebalancerAgent
from tools.stock_tools import FundamentalAnalysisTool
from tasks import (
    create_market_analysis_task, create_research_task, create_sentiment_task,
    create_backtest_task, create_risk_task, create_trading_task,
    create_rebalance_task,
)

print("=" * 60)
print("1) 数据层")
print("=" * 60)
md = crew.prepare_market_data()
print(f"market_data chars={len(md)} lines={md.count(chr(10)) + 1}")
print(f"内联估值行数 PE= -> {md.count('PE=')}  PB= -> {md.count('PB=')}")
print(f"显式缺口标记 -> {md.count('估值=暂缺')}  新闻不可用 -> {md.count('新闻数据暂不可用')}")

print("=" * 60)
print("2) Agent 与 Task 装配")
print("=" * 60)
mw = MarketWatcherAgent().create_crewai_agent()
rs = ResearcherAgent().create_crewai_agent(tools=[FundamentalAnalysisTool()])
sa = SentimentAgent().create_crewai_agent(tools=[])
bv = BacktestAgent().create_crewai_agent()
rk = RiskManagerAgent().create_crewai_agent()
tr = TraderAgent().create_crewai_agent()
rb = PortfolioRebalancerAgent().create_crewai_agent()
print(f"researcher tools -> {[t.name for t in rs.tools]}  max_iter={rs.max_iter}")
print(f"sentiment tools  -> {[t.name for t in sa.tools]}")
print(f"backtest tools   -> {[t.name for t in bv.tools]}")

M, R, K, T = "«市场»", "«研究»", "«风控»", "«交易»"
market_task = create_market_analysis_task(mw, md)
research_task = create_research_task(rs, market_analysis=M, stock_data=md)
research_task.context = [market_task]
sentiment_task = create_sentiment_task(sa, stock_picks=R)
sentiment_task.context = [research_task]
backtest_task = create_backtest_task(bv, stock_picks=R)
backtest_task.context = [research_task, sentiment_task]
risk_task = create_risk_task(rk, stock_picks=R, market_analysis=M)
risk_task.context = [research_task, market_task, backtest_task]
trading_task = create_trading_task(tr, research=R, risk=K, market=M)
trading_task.context = [research_task, risk_task, market_task]
rebalance_task = create_rebalance_task(rb, trade_plan=T, market_state=M)
rebalance_task.context = [trading_task, market_task, risk_task]

tasks = [market_task, research_task, sentiment_task, backtest_task,
         risk_task, trading_task, rebalance_task]
print("=" * 60)
print("3) prompt 体量（描述 + context 注入的上游输出长度，按 1 token ~= 1.6 中文字符估）")
print("=" * 60)
worst = 0
NOMINAL_OUT = 1200  # 实测单任务输出约 1000~1700 中文字符，取 1200
for i, t in enumerate(tasks, 1):
    own = len(t.description)
    ctx_list = t.context if isinstance(t.context, list) else []
    ctx = sum(len(x.description) for x in ctx_list)
    # 运行时 context 注入的是上游"输出"而非"描述"，这里按标称输出量补算
    real = own + ctx + NOMINAL_OUT * len(ctx_list)
    est = real / 1.6
    worst = max(worst, est)
    print(f"  task{i} 上游数={len(ctx_list)} 描述={own:5} 上游描述={ctx:5} 估算 prompt ≈ {est:6.0f} token")
print(f"\n峰值下限估算 {worst:.0f} token（不含 system prompt / 工具模式 / 前序真实输出）")
print("提醒：StepFun 端点上下文若不足，故障表现是 Invalid response from LLM call。")
