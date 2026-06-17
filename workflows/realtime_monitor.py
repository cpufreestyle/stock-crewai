"""
实时监控工作流 - 替代原 run_virtual_v4.py:run_once()
每10分钟检查止损止盈 + 异动监控
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from core.orchestrator import Orchestrator, Workflow, WorkflowStep
from core.event_bus import Event, EventType
from core.state_store import get_state_store
from agents.risk_manager_agent import RiskManagerAgent
from agents.trader import TraderAgent

import portfolio_tracker as pt
import data_fetcher as df

logger = logging.getLogger("workflows.realtime_monitor")

# 股票池
STOCK_POOL = [
    "000001", "000063", "000100", "000333", "000651",
    "000858", "000895", "002415", "002475", "002594",
    "600016", "600019", "600028", "600030", "600036",
    "600048", "600050", "600104", "600276", "600309",
    "600519", "600887", "600900", "601006", "601012",
    "601088", "601166", "601186", "601318", "601398",
    "601628", "601857", "601888", "601899", "603259",
]


def check_stop_loss_take_profit() -> list:
    """检查持仓止损止盈（替代 v4 的 check_portfolio_risk）"""
    alerts = []

    try:
        portfolio = pt.load_portfolio()
        positions = portfolio.get("positions", {})
        cash = portfolio.get("cash", 100000)
        total_capital = portfolio.get("total_capital", 100000)

        if not positions:
            return alerts

        # 获取实时行情
        codes = list(positions.keys())
        realtime = df.get_sina_realtime(codes) if hasattr(df, 'get_sina_realtime') else {}

        for code, pos in positions.items():
            if code in realtime:
                current_price = realtime[code].get("current", 0)
            else:
                current_price = pos.get("last_price", pos["avg_cost"])

            if current_price <= 0:
                continue

            cost = pos["avg_cost"]
            pnl_pct = (current_price - cost) / cost * 100

            stop_loss = pos.get("stop_loss", 0)
            take_profit = pos.get("take_profit", 0)

            # 止损检查
            if stop_loss > 0 and current_price <= stop_loss:
                alerts.append({
                    "code": code,
                    "name": pos["name"],
                    "action": "STOP_LOSS",
                    "price": current_price,
                    "pnl_pct": pnl_pct,
                    "reason": f"触发止损线（{pnl_pct:.2f}%，止损{stop_loss:.2f}）",
                    "priority": 2,  # 紧急
                })

            # 止盈检查
            elif take_profit > 0 and current_price >= take_profit:
                alerts.append({
                    "code": code,
                    "name": pos["name"],
                    "action": "TAKE_PROFIT",
                    "price": current_price,
                    "pnl_pct": pnl_pct,
                    "reason": f"触发止盈线（+{pnl_pct:.2f}%，止盈{take_profit:.2f}）",
                    "priority": 1,
                })

            # 接近止盈警告
            elif take_profit > 0 and pnl_pct >= 15:
                alerts.append({
                    "code": code,
                    "name": pos["name"],
                    "action": "WARNING",
                    "price": current_price,
                    "pnl_pct": pnl_pct,
                    "reason": f"接近止盈线（+{pnl_pct:.2f}%），注意回撤",
                    "priority": 0,
                })

    except Exception as e:
        logger.error(f"止损止盈检查失败: {e}")

    return alerts


def execute_alert_trades(alerts: list) -> list:
    """根据止损止盈信号执行交易"""
    executed = []

    for alert in alerts:
        if alert["action"] not in ["STOP_LOSS", "TAKE_PROFIT"]:
            continue

        code = alert["code"]
        price = alert["price"]

        try:
            portfolio = pt.load_portfolio()
            positions = portfolio.get("positions", {})
            if code not in positions:
                continue

            pos = positions[code]
            shares = pos["shares"]

            result = pt.update_position(
                stock_code=code,
                stock_name=pos["name"],
                action="sell",
                price=price,
                shares=shares,
                reason=alert["reason"],
                current_prices={code: price},
            )

            if "error" not in result:
                pnl = (price - pos["avg_cost"]) * shares
                executed.append({
                    "code": code,
                    "name": pos["name"],
                    "action": alert["action"],
                    "shares": shares,
                    "price": price,
                    "pnl": round(pnl, 2),
                    "reason": alert["reason"],
                })
                logger.info(f"已卖出 {pos['name']}({code}) {shares}股@{price:.2f} 盈亏{pnl:+.2f}元")
            else:
                logger.error(f"卖出失败: {code} → {result['error']}")

        except Exception as e:
            logger.error(f"执行卖出异常: {code} → {e}")

    return executed


def run_monitor_once() -> dict:
    """单次监控运行（替代 v4 的 run_once）"""
    now = datetime.now()
    logger.info(f"[Monitor] {now.strftime('%Y-%m-%d %H:%M')} 开始监控...")

    # 1. 止损止盈检查
    alerts = check_stop_loss_take_profit()

    # 2. 执行止损止盈
    executed = execute_alert_trades(alerts)

    # 3. 保存运行日志
    try:
        log_file = Path(__file__).parent.parent / "history" / f"run_log_{now.strftime('%Y%m%d_%H%M')}.json"
        log_file.parent.mkdir(exist_ok=True)

        portfolio = pt.load_portfolio()
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": now.isoformat(),
                "alerts": alerts,
                "executed": executed,
                "portfolio": portfolio,
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"日志保存失败: {e}")

    # 4. 写入 StateStore
    try:
        store = get_state_store()
        store.set("last_monitor_result", {
            "timestamp": now.isoformat(),
            "alerts_count": len(alerts),
            "executed_count": len(executed),
        })
    except:
        pass

    result = {
        "timestamp": now.isoformat(),
        "alerts": alerts,
        "executed": executed,
    }

    logger.info(f"[Monitor] done: {len(alerts)} alerts, {len(executed)} executed")
    return result


def run_monitor_loop(interval_minutes: int = 10):
    """循环监控（交易时段内）"""
    logger.info(f"[Monitor] starting loop (interval={interval_minutes}min)")

    while True:
        now = datetime.now()
        hour = now.hour

        # 仅交易时段运行
        if (9 <= hour < 12) or (13 <= hour < 15):
            try:
                run_monitor_once()
            except Exception as e:
                logger.error(f"监控运行出错: {e}")
        else:
            logger.info(f"[{now.strftime('%H:%M')}] 非交易时段，等待中...")

        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="循环运行")
    args = parser.parse_args()

    if args.loop:
        run_monitor_loop()
    else:
        result = run_monitor_once()
        print(json.dumps(result, ensure_ascii=False, indent=2))
