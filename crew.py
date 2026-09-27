from dotenv import load_dotenv
load_dotenv()
import config
"""
CrewAI 主编排 - 多智能体炒股系统 v3.0
新增: 市场状态判断、板块轮动分析、推荐追踪
"""
from crewai import Crew, Process
from agents import (ResearcherAgent, RiskManagerAgent, TraderAgent, MarketWatcherAgent,
                                SentimentAgent, BacktestAgent, PortfolioRebalancerAgent)
from tasks import (
    create_market_analysis_task,
    create_research_task,
    create_risk_task,
    create_trading_task,
    create_sentiment_task,
    create_backtest_task,
    create_rebalance_task,
)
from concurrent.futures import ThreadPoolExecutor, as_completed
import data_fetcher as df
import portfolio_tracker as pt
from tools.stock_tools import FundamentalAnalysisTool
from tools.risk_tools import (StopLossAdviceTool, RiskRewardTool,
                              PortfolioRiskTool, CircuitBreakerCheckTool)
from backtest import multi_strategy_backtest
import recommendation_tracker as rt
import trading_plan as tp_plan
import risk_manager as rm
from collections import Counter
from datetime import datetime
import os
import sys

# 任务描述里指代上游输出的固定措辞。
# 上游输出本体由 Task.context 注入，这里只需要告诉智能体去哪儿找，不能写成 {{xx.output}}。
CTX_REF_MARKET = "（见下方上下文中「市场状态分析」任务的输出）"
CTX_REF_RESEARCH = "（见下方上下文中「选股研究」任务的输出）"
CTX_REF_RISK = "（见下方上下文中「风险评估」任务的输出）"
CTX_REF_TRADING = "（见下方上下文中「交易计划」任务的输出）"


def prepare_market_data(n_stocks: int = 10, heat: dict = None, regime: dict = None) -> str:
    """准备市场数据给LLM分析（优化：并行获取 + 精简数量）

    heat/regime 可由调用方预先获取后传入，避免 run_daily_analysis
    在保存报告阶段重复请求（get_market_heat 走 akshare 无缓存，
    重复调一次多等数秒且可能失败）。
    """
    lines = []
    
    # 市场情绪
    if heat is None:
        heat = df.get_market_heat()
    lines.append(f"市场情绪数据: 涨停={heat.get('涨停家数', 'N/A')}家, "
                 f"跌停={heat.get('跌停家数', 'N/A')}家, "
                 f"市场状态={heat.get('市场状态', 'N/A')}")
    
    # 市场状态判断（牛熊市）
    if regime is None:
        regime = df.get_market_regime()
    if regime.get("regime") != "未知":
        lines.append(f"\n市场趋势: 【{regime.get('regime', 'N/A')}】置信度{regime.get('confidence', 0)}%")
        for sig in regime.get("signals", [])[:4]:
            lines.append(f"  - {sig}")
    
    # 板块轮动
    sectors = df.get_sector_performance()
    if sectors:
        lines.append(f"\n强势板块 TOP5:")
        for s in sectors[:5]:
            lines.append(f"  {s['name']}: {s['change_pct']:+.2f}%")
    
    # 当前持仓（先批量刷新 last_price：get_portfolio_summary / check_stop_loss
    # 拿不到外部报价时会退到成本价，报告里所有持仓就都显示
    # “现价=成本”，风控/调仓会基于陈旧价格决策）
    try:
        refreshed = pt.refresh_position_prices()
        print(f"[持仓现价] 已刷新 {len(refreshed)} 只")
    except Exception as e:
        print(f"[警告] 持仓现价刷新失败: {e}")
    portfolio_summary = pt.get_portfolio_summary()
    lines.append(f"\n当前持仓状态:\n{portfolio_summary}")
    
    # 从候选股票池中抽样（精简到 10 只）
    pool = df.get_index_components()["code"].tolist()[:n_stocks]
    
    # 并行获取所有股票行情（优化点）
    print(f"[并行] 正在获取 {len(pool)} 只股票行情...")
    prices_map = df.get_batch_stock_prices(pool)
    # 估值一次批量取回并内联：研究员据此判断，不必逐只调 fundamental_analysis
    fund_map = df.get_fundamental_batch(pool)

    lines.append(f"\n候选股票池行情（共{len(pool)}只，分析最近90天）:")
    
    for code in pool:
        try:
            price_data = prices_map.get(code)
            name = code
            sector = ""
            for s in df.A_SHARE_POOL:
                if s["code"] == code:
                    name = s["name"]
                    sector = s["sector"]
                    break
            
            if price_data is not None and not price_data.empty:
                tech = df.calculate_technical(price_data)
                
                ma_bull = ""
                if tech.get("MA5") and tech.get("MA20"):
                    if tech["MA5"] > tech["MA20"]:
                        ma_bull = "✓"
                
                rsi = tech.get("RSI", 50)
                rsi_status = "超买" if rsi > 70 else ("超卖" if rsi < 30 else "正常")
                
                ret = tech.get("5日涨跌%", 0)
                trend = "↑" if ret > 2 else ("↓" if ret < -2 else "→")

                fund = fund_map.get(code) or {}
                if fund:
                    valuation = (f"PE={fund.get('PE', 'N/A')} "
                                 f"PB={fund.get('PB', 'N/A')} "
                                 f"总市值={fund.get('总市值(亿)', 'N/A')}亿")
                else:
                    valuation = "估值=暂缺(勿凭印象编造)"

                lines.append(
                    f"  {code} {name}({sector}): "
                    f"现价={tech.get('收盘价','N/A')}元 "
                    f"MA5={tech.get('MA5','N/A')} "
                    f"MA20={tech.get('MA20','N/A')} "
                    f"RSI={rsi}({rsi_status}) "
                    f"{trend}5日{ret:+.1f}%{ma_bull} "
                    f"{valuation}"
                )
            else:
                lines.append(f"  {code} {name}: 数据获取失败")
        except Exception as e:
            lines.append(f"  {code}: 异常-{str(e)[:30]}")
    
    # 财经新闻摘要
    news = []
    try:
        news = df.get_news_sentiment(days=2)
    except Exception:
        news = []
    if news:
        lines.append(f"\n近期财经要闻({len(news)}条):")
        for n in news[:5]:
            title = str(n.get("新闻标题", n.get("title", "")))[:60]
            date = n.get("发布时间", n.get("date", ""))
            lines.append(f"  [{date}] {title}")
    else:
        # get_news_sentiment 内部吞异常返回 []，静默缺席会让智能体自己编"政策利好"，
        # 所以这里必须留一行显式缺口说明（实测 akshare 1.18.94 的 stock_news_em 抛 ArrowInvalid）。
        lines.append("\n(新闻数据暂不可用：不得引用新闻作为催化剂依据，需要时写\"无\")")
    
    return "\n".join(lines)


def run_backtest_for_picks(stock_codes: list) -> str:
    """对推荐股票做回测（并行，缩短收尾等待）"""
    lines = ["\n=== 推荐股票回测 ==="]

    def _one(code: str):
        try:
            return multi_strategy_backtest(code)
        except Exception as e:
            return {"error": str(e)}

    results = {}
    if stock_codes:
        # ex.map 保序；多只股票时并发拉历史 K 线，
        # 底层 get_stock_price 本就是缓存 + 网络，互不干扰。
        with ThreadPoolExecutor(max_workers=min(5, len(stock_codes))) as ex:
            for code, r in zip(stock_codes, ex.map(_one, stock_codes)):
                results[code] = r

    for code in stock_codes:
        r = results[code]
        if "error" in r:
            lines.append(f"{code}: {r['error']}")
            continue
        lines.append(f"\n{code}:")
        for name, data in r.get("strategies", {}).items():
            lines.append(f"  {name}: 收益={data['收益率']} 回撤={data.get('最大回撤','N/A')} 胜率={data['胜率']} 持仓={data['当前持仓']}")
        lines.append(f"  最佳策略: {r.get('best_strategy')} ({r.get('best_return')})")
    return "\n".join(lines)


def _looks_degenerate(text: str) -> bool:
    """检测本地小模型的退化输出（单字符整行复读等）。

    9/26 run7 实测：交易呓/调仓师两个任务整段输出 @@@@ 复读，CrewAI
    视为正常完成。同样的 prompt 单独重跑又正常（见 repro_trader.py），
    属抑制模型随机退化，只能检测 + 告警，不能依靠模型自庡。
    """
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 50:
        return True
    lines = [l.strip() for l in stripped.splitlines() if l.strip()]
    if not lines:
        return True
    # 单字符整行复读（run7 的 @ 行）占多数 -> 退化
    junk = sum(1 for l in lines if len(set(l)) == 1 and len(l) >= 10)
    if junk / len(lines) > 0.5:
        return True
    # 同一行高度重复（复读的另一种形态）。注意不用全文
    # 字符集大小做判据：中文本身唯一字符就少，会误伤正常报告。
    top = Counter(lines).most_common(1)[0][1]
    return top / len(lines) > 0.6


def check_degenerate_tasks(crew) -> list:
    """检查每个任务输出是否退化，返回告警行列表。"""
    warnings = []
    for idx, task in enumerate(getattr(crew, "tasks", []) or [], 1):
        raw = ""
        try:
            raw = task.output.raw if task.output is not None else ""
        except Exception:
            raw = ""
        if _looks_degenerate(raw):
            label = (getattr(task, "description", "") or "").strip().splitlines()
            label = label[0][:30] if label else f"task{idx}"
            warnings.append(f"task{idx}[{label}] 输出退化（{len(raw)} 字，单字符复读）")
    return warnings


def notify_wechat(message: str):
    """通过 openclaw 发送微信通知（静默失败，cron delivery 已接管通知）"""
    try:
        import subprocess, shutil
        if shutil.which("openclaw") is None:
            return False  # 静默跳过，cron delivery 会处理
        result = subprocess.run(
            ["openclaw", "message", "send", "--channel", "wechat-access", "--message", message[:2000]],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False  # 静默跳过


def run_daily_analysis(with_backtest: bool = True) -> str:
    """运行每日分析流程"""
    print(f"\n{'='*60}")
    print(f"  A股多智能体炒股系统 v3.0 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    # 1. 准备市场数据（heat/regime 先取好，步骤 8/9 复用，避免二次请求）
    print("[1/8] 准备市场数据...")
    heat = df.get_market_heat()
    regime = df.get_market_regime()
    market_data = prepare_market_data(heat=heat, regime=regime)
    print("[完成]\n")
    
    # 2. 检查 API Key
    api_key = config.API_KEY
    if not api_key or api_key == "sk-your-key-here":
        print("[错误] 请先在 .env 中配置 API Key")
        return "未配置 API Key"
    
    # 3. 检查止损止盈
    print("[2/8] 检查持仓止损止盈...")
    triggered = pt.check_stop_loss()
    if triggered:
        for t in triggered:
            msg = f"⚠ {t['name']}: {t['action']} @ {t['current_price']}元 ({t.get('loss_pct', t.get('profit_pct', 0))}%)"
            print(msg)
            notify_wechat(msg)
    print("[完成]\n")
    
    # 4. 追踪历史推荐
    print("[3/8] 追踪历史推荐表现...")
    try:
        perf = rt.get_performance_summary([5, 10])
        print(perf[:500])
    except Exception as e:
        print(f"追踪失败: {e}")
    print("[完成]\n")
    
    # 5. 创建 Agents
    print("[4/8] 初始化 CrewAI Agents...")
    market_watcher = MarketWatcherAgent().create_crewai_agent()
    # 候选池的行情/估值/板块/新闻已由 prepare_market_data 内联进任务描述，
    # 这里只留批量版 fundamental_analysis：run6 实测给它 9 个工具会逐只调
    # technical_analysis / news_sentiment（38 次调用），烧光 max_iter 后只吐框架提示语回显。
    researcher = ResearcherAgent().create_crewai_agent(tools=[FundamentalAnalysisTool()])
    # 风控/交易员/调仓三个智能体要按持仓逐只调 stop_loss_advice / risk_reward /
    # set_stop_loss / execute_sell（9/26 实测风控 8 轮就撞上限，回显框架收尾提示语，
    # 下游交易员同样只回显）。这三个智能体单独放宽 max_iter，其余仍走 AGENT_MAX_ITER。
    # 风控只给"评估类"工具：position_size 是买入 sizing、kelly_position 要胜率历史，
    # 都不在本任务范围内——9/26 实测风控拿到全套后在 position_size 上反复微调
    # risk_per_trade（0.008→0.009→0.0085），48 次调用把迭代烧光，触发与 run6 同款的
    # 假成功（回显框架收尾提示语 + 大面积 @ 填充），下游交易员/调仓同样被毒化成 @ 复读。
    # 写操作工具（execute_*/set_stop_loss）不给风控：本任务只出"建议"，不下单。
    risk_mgr = RiskManagerAgent().create_crewai_agent(
        tools=[StopLossAdviceTool(), RiskRewardTool(),
               PortfolioRiskTool(), CircuitBreakerCheckTool()],
        max_iter=25,
    )
    trader = TraderAgent().create_crewai_agent(max_iter=25)
    # 新增 Agent
    # 情绪分析不给工具：tools/sentiment_tools.py 里三个工具最终都走 _news_sentiment_tool，
    # 而它的唯一数据源 akshare stock_news_em 目前必抛 ArrowInvalid。更糟的是
    # _stock_sentiment_score_tool 解析失败评分时会静默返回 50/100，等于把"接口挂了"
    # 伪装成"情绪中性"喂给下游。任务提示词也已改为只用 context 里的量价数据打分。
    sentiment_analyst = SentimentAgent().create_crewai_agent(tools=[])
    backtest_validator = BacktestAgent().create_crewai_agent()
    rebalancer = PortfolioRebalancerAgent().create_crewai_agent(max_iter=25)
    print("[完成]\n")
    
    # 6. 构建任务链
    print("[5/8] 构建任务流水线...")

    # 说明：CrewAI 不会把描述里的 "{{某任务.output}}" 内插成上游输出，
    # 那种写法会把占位符原样送进 prompt（实测风控/交易/调仓任务都中招）。
    # 唯一的传递机制是 Task.context，所以下面把描述里引用到的每个上游任务都补进 context。
    market_task = create_market_analysis_task(market_watcher, market_data)

    research_task = create_research_task(
        researcher,
        market_analysis=CTX_REF_MARKET,
        stock_data=market_data
    )
    research_task.context = [market_task]
    
    risk_task = create_risk_task(
        risk_mgr,
        stock_picks=CTX_REF_RESEARCH,
        market_analysis=CTX_REF_MARKET
    )
    
    trading_task = create_trading_task(
        trader,
        research=CTX_REF_RESEARCH,
        risk=CTX_REF_RISK,
        market=CTX_REF_MARKET
    )

    # 新增任务（在 research_task 之后、risk_task 之前插入情绪分析和回测）
    sentiment_task = create_sentiment_task(
        sentiment_analyst,
        stock_picks=CTX_REF_RESEARCH
    )
    sentiment_task.context = [research_task]

    backtest_task = create_backtest_task(
        backtest_validator,
        stock_picks=CTX_REF_RESEARCH
    )
    backtest_task.context = [research_task, sentiment_task]

    # 风控需要同时看到：选股结论、市场状态、回测验证结果
    risk_task.context = [research_task, market_task, backtest_task]
    trading_task.context = [research_task, risk_task, market_task]

    # 在 trading_task 之后添加调仓任务
    rebalance_task = create_rebalance_task(
        rebalancer,
        trade_plan=CTX_REF_TRADING,
        market_state=CTX_REF_MARKET
    )
    rebalance_task.context = [trading_task, market_task, risk_task]
    print("[完成]\n")
    
    # 7. 执行 Crew
    print("[6/8] 启动 CrewAI 编排（顺序模式，约2-4分钟）...")
    crew = Crew(
        agents=[market_watcher, researcher, sentiment_analyst, backtest_validator, risk_mgr, trader, rebalancer],
        tasks=[market_task, research_task, sentiment_task, backtest_task, risk_task, trading_task, rebalance_task],
        process=Process.sequential,  # 优化：从 hierarchical 改为 sequential，速度提升 2-3 倍
        verbose=True
    )
    
    result = crew.kickoff()
    result_str = str(result)
    plan = None

    # 退化输出检查：本地模型偶发 @ 复读（run7 交易呓/调仓师），
    # CrewAI 不会报错，这里显式抢回来，避免报告里混入垃圾还不知情。
    degenerate = check_degenerate_tasks(crew)
    for w in degenerate:
        print(f"\n🚨 [假成功] {w}\n")
    print("[完成]\n")
    
    # 8. 回测
    print("[7/8] 对推荐股票进行历史回测...")
    backtest_text = ""
    if with_backtest:
        import re
        codes = re.findall(r'\b(000\d{3}|002\d{3}|600\d{3}|601\d{3}|603\d{3})\b', result_str)
        unique_codes = list(set(codes))[:5]
        if unique_codes:
            backtest_text = run_backtest_for_picks(unique_codes)
            print(backtest_text)
    print("[完成]\n")
    
    # 9. 保存推荐记录
    print("[8/8] 保存推荐记录...")
    try:
        # 结构化交易计划优先（参照 TradingAgents 的 pydantic schema 模式）；
        # 解析不到才回退旧的自由文本正则路径，不改变旧行为。
        plan = tp_plan.parse_trading_plan(result_str)
        parse_mode = "structured"
        if plan is not None:
            stocks = tp_plan.plan_to_recommendations(plan)
            print(f"[结构化解析] {len(plan.actions)} 条动作，可追踪推荐 {len(stocks)} 只")
        else:
            stocks = rt.parse_trading_result(result_str)
            parse_mode = "legacy-regex"
            print("[结构化解析] 未命中 JSON 块，回退自由文本解析")
        if stocks:
            # 复用 [1/8] 已取的 heat/regime，不再重复请求
            rt.save_recommendation(
                stocks=stocks,
                market_status=heat.get("市场状态", ""),
                recommended_position=regime.get("regime", ""),
                notes=f"推荐{len(stocks)}只股票"
            )
            print(f"已保存 {len(stocks)} 只推荐股票到追踪系统")
    except Exception as e:
        print(f"保存推荐失败: {e}")
    
    # 保存完整报告
    if degenerate:
        result_str = ("\n> 🚨 警告：以下任务输出退化（单字符复读），内容不可用："
                      + "\u3001".join(degenerate) + "\n\n") + result_str

    full_report = f"# 炒股分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    full_report += result_str
    if backtest_text:
        full_report += f"\n\n{backtest_text}"
    
    # 风险报告
    try:
        pf = pt.load_portfolio()
        risk_report = rm.daily_risk_report(pf, regime.get("regime", "震荡市"))
        full_report += f"\n\n---\n{risk_report}\n"
    except:
        pass
    
    full_report += f"\n---\n{pt.get_portfolio_summary()}"
    if plan is not None:
        full_report += "\n\n---\n" + tp_plan.render_plan_summary(plan) + "\n"
    
    with open("result_latest.md", "w", encoding="utf-8") as f:
        f.write(full_report)
    pt.save_daily_report(full_report)
    
    # 微信通知
    short_summary = f"📊 炒股分析 {datetime.now().strftime('%m-%d %H:%M')}\n\n"
    short_summary += result_str[:600]
    if backtest_text:
        short_summary += f"\n\n{backtest_text[:300]}"
    notify_wechat(short_summary)
    
    return full_report


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # 设置 UTF-8 输出
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
    
    result = run_daily_analysis(with_backtest=True)
    print(f"\n{'='*60}")
    print("  最终交易计划 + 回测")
    print(f"{'='*60}")
    print(result)
    print("\n[已保存] result_latest.md + history/")
