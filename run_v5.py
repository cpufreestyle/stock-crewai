#!/usr/bin/env python3
"""
stock-crewai v5.0 - TradingAgents 集成版
基于 LangGraph 多智能体工作流 + DeepSeek LLM + ChromaDB 记忆

用法:
    python run_v5.py              # 单次运行
    python run_v5.py --loop       # 循环模式（交易时段每10分钟）
    python run_v5.py --backtest   # 回测模式
"""
import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "v5_run.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("v5.main")

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


def run_single_stock(stock_code: str, stock_name: str = "") -> dict:
    """对单只股票运行 TradingAgents 工作流"""
    from v5.graph.trading_workflow import build_trading_graph
    from v5.data_adapters.ta_adapter import get_adapter

    adapter = get_adapter()

    # 获取名称
    if not stock_name:
        quote = adapter.get_realtime_quote(stock_code)
        stock_name = quote.get("name", stock_code)

    logger.info(f"═══ TradingAgents v5 ═══ {stock_name}({stock_code}) ═══")

    # 构建初始状态
    initial_state = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "market_data": {},
        "news_data": [],
        "social_data": {},
        "fundamentals": {},
        "analysis_reports": [],
        "bull_argument": "",
        "bear_argument": "",
        "debate_round": 0,
        "debate_history": [],
        "trade_proposal": {},
        "risk_assessment": {},
        "final_decision": {},
        "recalled_memories": [],
    }

    # 运行工作流
    graph = build_trading_graph()
    result = graph.invoke(initial_state)

    decision = result.get("final_decision", {})
    logger.info(f"═══ 决策: {decision.get('action', 'HOLD')} | "
                f"信心: {decision.get('confidence', 0)} | "
                f"理由: {decision.get('reason', '')[:100]} ═══")

    return result


def run_scan(candidates: list = None):
    """扫描候选股票池，运行工作流"""
    from v5.config import STOCK_POOL

    if candidates is None:
        candidates = STOCK_POOL[:10]  # 默认取前10只

    logger.info(f"──── TradingAgents v5 扫描开始，共 {len(candidates)} 只股票 ────")

    results = []
    for i, code in enumerate(candidates):
        logger.info(f"[{i+1}/{len(candidates)}] 处理 {code}...")
        try:
            result = run_single_stock(code)
            results.append(result)
        except Exception as e:
            logger.error(f"处理 {code} 失败: {e}", exc_info=True)

    # 汇总
    buy_list = [r for r in results if r.get("final_decision", {}).get("action") == "BUY"]
    sell_list = [r for r in results if r.get("final_decision", {}).get("action") == "SELL"]

    logger.info(f"──── 扫描完成: {len(buy_list)} 只买入, {len(sell_list)} 只卖出, "
                f"{len(results) - len(buy_list) - len(sell_list)} 只持有 ────")

    # 打印买入建议
    if buy_list:
        logger.info("──── 买入建议 ────")
        for r in buy_list:
            d = r["final_decision"]
            logger.info(f"  {r['stock_name']}({r['stock_code']}): "
                        f"价格={d.get('price', 'N/A')}, 数量={d.get('volume', 0)}, "
                        f"止损={d.get('stop_loss', 'N/A')}, 止盈={d.get('take_profit', 'N/A')}")

    # 执行交易（对接 v4 的 portfolio_tracker）
    if buy_list:
        execute_trades(buy_list)

    # 检查持仓止损止盈
    check_positions()

    # 发送通知
    send_notification(results)

    return results


def execute_trades(buy_list: list):
    """执行买入交易 - 对接 v4 portfolio_tracker"""
    try:
        from portfolio_tracker import PortfolioTracker
        tracker = PortfolioTracker()

        for r in buy_list:
            d = r["final_decision"]
            code = r["stock_code"]
            volume = d.get("volume", 100)
            price = d.get("price") or r.get("market_data", {}).get("price", 0)

            if price > 0 and volume > 0:
                logger.info(f"执行买入: {code} {volume}股 @ {price}")
                tracker.buy(code, r["stock_name"], volume, price)

                # 设置止损止盈
                if d.get("stop_loss"):
                    tracker.set_stop_loss(code, d["stop_loss"])
                if d.get("take_profit"):
                    tracker.set_take_profit(code, d["take_profit"])

    except Exception as e:
        logger.error(f"执行交易失败: {e}", exc_info=True)


def check_positions():
    """检查持仓止损止盈 - 复用 v4 逻辑"""
    try:
        from portfolio_tracker import PortfolioTracker
        tracker = PortfolioTracker()
        tracker.check_stop_loss_profit()
    except Exception as e:
        logger.error(f"检查持仓失败: {e}")


def send_notification(results: list):
    """发送企业微信通知"""
    try:
        from wechat_notifier import send_trading_summary
        buy_list = [r for r in results if r.get("final_decision", {}).get("action") == "BUY"]
        sell_list = [r for r in results if r.get("final_decision", {}).get("action") == "SELL"]

        if buy_list or sell_list:
            send_trading_summary(buy_list, sell_list)
            logger.info("通知已发送")
    except Exception as e:
        logger.warning(f"通知发送失败: {e}")


def is_trading_time() -> bool:
    """判断是否在A股交易时段"""
    now = datetime.now()
    # 周末不交易
    if now.weekday() >= 5:
        return False
    # 9:25-11:30, 13:00-15:00
    t = now.hour * 100 + now.minute
    return (925 <= t <= 1130) or (1300 <= t <= 1500)


def loop_mode():
    """循环模式 - 交易时段每10分钟运行一次"""
    from v5.config import SCAN_INTERVAL_MINUTES

    logger.info(f"──── TradingAgents v5 循环模式，间隔 {SCAN_INTERVAL_MINUTES} 分钟 ────")

    while True:
        if is_trading_time():
            try:
                run_scan()
            except Exception as e:
                logger.error(f"扫描失败: {e}", exc_info=True)

            logger.info(f"等待 {SCAN_INTERVAL_MINUTES} 分钟...")
            time.sleep(SCAN_INTERVAL_MINUTES * 60)
        else:
            # 非交易时段，每5分钟检查一次
            next_time = "次日 09:25" if datetime.now().hour >= 15 else "今日 09:25"
            logger.info(f"非交易时段，下次交易: {next_time}")
            time.sleep(300)


def backtest_mode(start_date: str, end_date: str):
    """回测模式"""
    logger.info(f"──── 回测模式: {start_date} → {end_date} ────")
    # TODO: 对接 v4 backtest.py
    logger.info("回测功能开发中...")


def main():
    parser = argparse.ArgumentParser(description="stock-crewai v5 - TradingAgents")
    parser.add_argument("--loop", action="store_true", help="循环模式")
    parser.add_argument("--backtest", action="store_true", help="回测模式")
    parser.add_argument("--stock", type=str, help="单只股票测试")
    args = parser.parse_args()

    # 检查 API Key
    if not os.getenv("DEEPSEEK_API_KEY"):
        logger.error("请设置 DEEPSEEK_API_KEY 环境变量！")
        logger.info("获取地址: https://platform.deepseek.com/")
        sys.exit(1)

    if args.stock:
        # 单只股票测试
        result = run_single_stock(args.stock)
        print(json.dumps(result.get("final_decision", {}), ensure_ascii=False, indent=2))
    elif args.backtest:
        backtest_mode("2026-01-01", "2026-06-30")
    elif args.loop:
        loop_mode()
    else:
        # 单次扫描
        run_scan()


if __name__ == "__main__":
    main()
