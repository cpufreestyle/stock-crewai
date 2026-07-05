#!/usr/bin/env python3
"""
stock-crewai v5 完整运行入口

流程:
  1. 数据层：获取股票池行情
  2. 决策层：TradingAgents 四层 Agent 工作流（分析→辩论→交易→风控）
  3. 回测层：NautilusTrader 增强回测
  4. 输出层：决策报告 + 回测报告

用法:
  python run_v5.py                    # 扫描全部股票池
  python run_v5.py --stock 000333     # 单只分析
  python run_v5.py --backtest         # 回测模式
"""
import sys
import os
import json
import logging
import argparse
from datetime import datetime, timedelta

# 确保项目根目录在 path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("v5.runner")


def run_single_stock(stock_code: str, stock_name: str = "") -> dict:
    """对单只股票运行 v5 工作流"""
    from v5.graph.trading_workflow import build_trading_graph
    
    if not stock_name:
        stock_name = stock_code
    
    logger.info(f"{'='*60}")
    logger.info(f"  v5 TradingAgents: {stock_name}({stock_code})")
    logger.info(f"{'='*60}")
    
    # 初始状态
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
    
    # 构建并执行工作流
    app = build_trading_graph()
    final_state = app.invoke(initial_state)
    
    decision = final_state.get("final_decision", {})
    logger.info(f"决策结果: {decision.get('action', 'HOLD')} | 置信度: {decision.get('confidence', 0)}")
    
    return decision


def run_scan(stock_pool: list, limit: int = 10) -> list:
    """扫描股票池"""
    decisions = []
    for i, code in enumerate(stock_pool[:limit]):
        logger.info(f"[{i+1}/{min(len(stock_pool), limit)}] scanning {code}...")
        try:
            decision = run_single_stock(code)
            if decision.get("action") != "HOLD":
                decision["stock_code"] = code
                decisions.append(decision)
                logger.info(f"  → {decision.get('action')} @ {decision.get('price', 'N/A')}")
        except Exception as e:
            logger.error(f"  → error: {e}")
    
    logger.info(f"\n扫描完成: {len(decisions)}/{min(len(stock_pool), limit)} 有交易信号")
    return decisions


def run_backtest_mode(decisions: list = None, days: int = 90):
    """回测模式：对决策进行历史回测"""
    from v5.backtest.nautilus_bridge import run_v5_backtest
    from v5.data_adapters.ta_adapter import get_adapter
    
    if decisions is None:
        # 先扫描生成决策
        from v5.config import STOCK_POOL
        decisions = run_scan(STOCK_POOL, limit=5)
    
    if not decisions:
        logger.warning("无决策可回测")
        return
    
    # 获取历史数据
    adapter = get_adapter()
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    logger.info(f"获取历史数据 {start_date} → {end_date}...")
    historical_data = {}
    for d in decisions:
        code = d.get("stock_code", "")
        if not code:
            continue
        kline = adapter.get_kline_data(code, days=days)
        if kline and "klines" in kline:
            historical_data[code] = kline["klines"]
        elif kline and isinstance(kline, list):
            historical_data[code] = kline
    
    logger.info(f"历史数据: {len(historical_data)}/{len(decisions)} 只股票有数据")
    
    # 运行回测
    result = run_v5_backtest(
        decisions=decisions,
        historical_data=historical_data,
        start_date=start_date,
        end_date=end_date,
    )
    
    # 输出报告
    print("\n" + "="*60)
    print("  NautilusTrader 增强回测报告")
    print("="*60)
    print(f"  引擎: {result.get('engine', 'unknown')}")
    print(f"  初始资金: ¥{result.get('initial_capital', 0):,.0f}")
    print(f"  最终资金: ¥{result.get('final_capital', 0):,.0f}")
    print(f"  总收益率: {result.get('total_return_pct', 0):.2f}%")
    print(f"  夏普比率: {result.get('sharpe_ratio', 0):.2f}")
    print(f"  最大回撤: {result.get('max_drawdown_pct', 0):.2f}%")
    print(f"  胜率: {result.get('win_rate', 0):.1f}%")
    print(f"  盈亏比: {result.get('profit_loss_ratio', 0):.2f}")
    print(f"  总交易次数: {result.get('total_trades', 0)}")
    print(f"  手续费: ¥{result.get('total_commission', 0):,.2f}")
    print(f"  印花税: ¥{result.get('total_stamp_duty', 0):,.2f}")
    print(f"  滑点成本: ¥{result.get('total_slippage', 0):,.2f}")
    print("="*60)
    
    # 保存报告
    report_file = os.path.join(PROJECT_ROOT, "v5", "backtest_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"报告已保存: {report_file}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="stock-crewai v5 TradingAgents")
    parser.add_argument("--stock", type=str, help="单只股票代码分析")
    parser.add_argument("--name", type=str, default="", help="股票名称")
    parser.add_argument("--scan", action="store_true", help="扫描股票池")
    parser.add_argument("--backtest", action="store_true", help="回测模式")
    parser.add_argument("--limit", type=int, default=10, help="扫描数量限制")
    parser.add_argument("--days", type=int, default=90, help="回测天数")
    
    args = parser.parse_args()
    
    if args.stock:
        # 单只分析
        decision = run_single_stock(args.stock, args.name)
        print(json.dumps(decision, ensure_ascii=False, indent=2))
        
        if args.backtest:
            decisions = [{**decision, "stock_code": args.stock}]
            run_backtest_mode(decisions, args.days)
            
    elif args.scan or args.backtest:
        # 扫描模式
        from v5.config import STOCK_POOL
        decisions = run_scan(STOCK_POOL, args.limit)
        
        if args.backtest:
            run_backtest_mode(decisions, args.days)
        else:
            # 输出决策摘要
            for d in decisions:
                print(f"  {d.get('stock_code', '')}: {d.get('action', 'HOLD')} "
                      f"@ {d.get('price', 'N/A')} | {d.get('reason', '')[:80]}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
