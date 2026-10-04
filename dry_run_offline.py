"""离线干跑：不调用任何 LLM，只验证 数据层 -> 任务装配 -> prompt 体量 这条链路。

用途：端到端一次要几十分钟，任何装配期异常（数据源抛错、任务参数缺失）
都应该在这里先暴露，而不是在 Crew 跑到第 5 个任务时才炸。
"""
from dotenv import load_dotenv
load_dotenv()

import crew
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
# 必须走 crew.build_agents()：自己重建一份就会按默认全量工具装配，
# 与 crew.py 实际传参不一致，干跑从此验不出工具集回归（9/26 情绪工具就是这么漏的）。
ag = crew.build_agents()
mw = ag["market_watcher"]
rs = ag["researcher"]
sa = ag["sentiment_analyst"]
bv = ag["backtest_validator"]
rk = ag["risk_mgr"]
tr = ag["trader"]
rb = ag["rebalancer"]
for key in ("market_watcher", "researcher", "sentiment_analyst", "backtest_validator",
            "risk_mgr", "trader", "rebalancer"):
    a = ag[key]
    print(f"{key:18} tools -> {[t.name for t in a.tools]}  max_iter={a.max_iter}")

# 写操作工具一旦回到分析流水线，每跑一次日报就会改一次 portfolio.json
WRITE_TOOLS = {"execute_buy", "execute_sell", "set_stop_loss"}
leaks = {k: WRITE_TOOLS & {t.name for t in a.tools} for k, a in ag.items()}
leaks = {k: v for k, v in leaks.items() if v}
print(f"写操作工具泄漏 -> {leaks or '无'}")
assert not leaks, f"分析流水线不得携带下单类工具: {leaks}"

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
