import config
"""
CrewAI 主编排 - 多智能体炒股系统 v3.0
新增: 市场状态判断、板块轮动分析、推荐追踪
"""
from crewai import Crew, Process
from agents import StockResearchAgent, RiskAgent, TradingAgent, MarketWatcher
from tasks import (
    create_market_analysis_task,
    create_research_task,
    create_risk_task,
    create_trading_task
)
from concurrent.futures import ThreadPoolExecutor, as_completed
import data_fetcher as df
import portfolio_tracker as pt
from backtest import multi_strategy_backtest
import recommendation_tracker as rt
import risk_manager as rm
from datetime import datetime
import os
import sys


def prepare_market_data(n_stocks: int = 10) -> str:
    """准备市场数据给LLM分析（优化：并行获取 + 精简数量）"""
    lines = []
    
    # 市场情绪
    heat = df.get_market_heat()
    lines.append(f"市场情绪数据: 涨停={heat.get('涨停家数', 'N/A')}家, "
                 f"跌停={heat.get('跌停家数', 'N/A')}家, "
                 f"市场状态={heat.get('市场状态', 'N/A')}")
    
    # 市场状态判断（牛熊市）
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
    
    # 当前持仓
    portfolio_summary = pt.get_portfolio_summary()
    lines.append(f"\n当前持仓状态:\n{portfolio_summary}")
    
    # 从候选股票池中抽样（精简到 10 只）
    pool = df.get_index_components()["code"].tolist()[:n_stocks]
    
    # 并行获取所有股票行情（优化点）
    print(f"[并行] 正在获取 {len(pool)} 只股票行情...")
    prices_map = df.get_batch_stock_prices(pool)
    
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
                
                lines.append(
                    f"  {code} {name}({sector}): "
                    f"现价={tech.get('收盘价','N/A')}元 "
                    f"MA5={tech.get('MA5','N/A')} "
                    f"MA20={tech.get('MA20','N/A')} "
                    f"RSI={rsi}({rsi_status}) "
                    f"{trend}5日{ret:+.1f}%{ma_bull}"
                )
            else:
                lines.append(f"  {code} {name}: 数据获取失败")
        except Exception as e:
            lines.append(f"  {code}: 异常-{str(e)[:30]}")
    
    # 财经新闻摘要
    try:
        news = df.get_news_sentiment(days=2)
        if news:
            lines.append(f"\n近期财经要闻({len(news)}条):")
            for n in news[:5]:
                title = str(n.get("新闻标题", n.get("title", "")))[:60]
                date = n.get("发布时间", n.get("date", ""))
                lines.append(f"  [{date}] {title}")
    except:
        lines.append("\n(新闻数据暂时不可用)")
    
    return "\n".join(lines)


def run_backtest_for_picks(stock_codes: list) -> str:
    """对推荐股票做回测"""
    lines = ["\n=== 推荐股票回测 ==="]
    for code in stock_codes:
        r = multi_strategy_backtest(code)
        if "error" in r:
            lines.append(f"{code}: {r['error']}")
            continue
        lines.append(f"\n{code}:")
        for name, data in r.get("strategies", {}).items():
            lines.append(f"  {name}: 收益={data['收益率']} 回撤={data.get('最大回撤','N/A')} 胜率={data['胜率']} 持仓={data['当前持仓']}")
        lines.append(f"  最佳策略: {r.get('best_strategy')} ({r.get('best_return')})")
    return "\n".join(lines)


def notify_wechat(message: str):
    """通过 openclaw 发送微信通知"""
    try:
        # 使用 openclaw CLI 发送
        import subprocess
        result = subprocess.run(
            ["openclaw", "message", "send", "--channel", "wechat-access", "--message", message[:2000]],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[通知] 发送失败: {e}")
        return False


def run_daily_analysis(with_backtest: bool = True) -> str:
    """运行每日分析流程"""
    print(f"\n{'='*60}")
    print(f"  A股多智能体炒股系统 v3.0 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    # 1. 准备市场数据
    print("[1/8] 准备市场数据...")
    market_data = prepare_market_data()
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
    market_watcher = MarketWatcher().create()
    researcher = StockResearchAgent().create()
    risk_mgr = RiskAgent().create()
    trader = TradingAgent().create()
    print("[完成]\n")
    
    # 6. 构建任务链
    print("[5/8] 构建任务流水线...")
    
    market_task = create_market_analysis_task(market_watcher, market_data)
    
    research_task = create_research_task(
        researcher,
        market_analysis="{{market_task.output}}",
        stock_data=market_data
    )
    research_task.context = [market_task]
    
    risk_task = create_risk_task(
        risk_mgr,
        stock_picks="{{research_task.output}}",
        market_analysis="{{market_task.output}}"
    )
    risk_task.context = [research_task]
    
    trading_task = create_trading_task(
        trader,
        research="{{research_task.output}}",
        risk="{{risk_task.output}}",
        market="{{market_task.output}}"
    )
    trading_task.context = [risk_task]
    print("[完成]\n")
    
    # 7. 执行 Crew
    print("[6/8] 启动 CrewAI 编排（顺序模式，约2-4分钟）...")
    crew = Crew(
        agents=[market_watcher, researcher, risk_mgr, trader],
        tasks=[market_task, research_task, risk_task, trading_task],
        process=Process.sequential,  # 优化：从 hierarchical 改为 sequential，速度提升 2-3 倍
        verbose=True
    )
    
    result = crew.kickoff()
    result_str = str(result)
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
        stocks = rt.parse_trading_result(result_str)
        if stocks:
            # 获取市场状态
            heat = df.get_market_heat()
            regime = df.get_market_regime()
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
    full_report = f"# 炒股分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    full_report += result_str
    if backtest_text:
        full_report += f"\n\n{backtest_text}"
    
    # 风险报告
    try:
        pf = pt.load_portfolio()
        regime = df.get_market_regime()
        risk_report = rm.daily_risk_report(pf, regime.get("regime", "震荡市"))
        full_report += f"\n\n---\n{risk_report}\n"
    except:
        pass
    
    full_report += f"\n---\n{pt.get_portfolio_summary()}"
    
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
