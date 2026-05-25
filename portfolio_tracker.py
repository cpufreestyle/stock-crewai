"""持仓跟踪模块 - 记录每日推荐并对比实际走势"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from safe_io import safe_load_json, safe_save_json, safe_update_json
from config import PORTFOLIO_FILE
from db import load_portfolio_db, save_portfolio_db, save_trade, load_trades as load_trades_db
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "history")


def ensure_dirs():
    os.makedirs(HISTORY_DIR, exist_ok=True)


def load_portfolio() -> Dict:
    """加载当前持仓"""
    try:
        return load_portfolio_db()
    except Exception:
        return safe_load_json(
            PORTFOLIO_FILE,
            default={
                "positions": {},
                "cash": 100000,
                "total_capital": 100000,
                "created": datetime.now().isoformat(),
                "total_value": 100000,
                "total_return_pct": 0.0,
            },
        )


def save_portfolio(portfolio: Dict):
    """保存持仓"""
    ensure_dirs()
    try:
        save_portfolio_db(portfolio)
    except Exception:
        safe_save_json(PORTFOLIO_FILE, portfolio)


def update_position(
    stock_code: str,
    stock_name: str,
    action: str,
    price: float,
    shares: int,
    reason: str = "",
    current_prices: dict = None
) -> Dict:
    """更新持仓"""
    portfolio = load_portfolio()

    if action == "buy":
        cost = price * shares
        if cost > portfolio["cash"]:
            return {"error": "资金不足"}

        if stock_code in portfolio["positions"]:
            pos = portfolio["positions"][stock_code]
            total_shares = pos["shares"] + shares
            avg_cost = (pos["avg_cost"] * pos["shares"] + price * shares) / total_shares
            pos["shares"] = total_shares
            pos["avg_cost"] = round(avg_cost, 2)
        else:
            portfolio["positions"][stock_code] = {
                "name": stock_name,
                "shares": shares,
                "avg_cost": round(price, 2),
                "buy_date": datetime.now().strftime("%Y-%m-%d"),
                "stop_loss": 0,
                "take_profit": 0
            }

        portfolio["cash"] -= cost

    elif action == "sell":
        if stock_code not in portfolio["positions"]:
            return {"error": f"未持有 {stock_code}"}

        pos = portfolio["positions"][stock_code]
        if shares > pos["shares"]:
            shares = pos["shares"]

        revenue = price * shares
        pnl = (price - pos["avg_cost"]) * shares
        pnl_pct = (price - pos["avg_cost"]) / pos["avg_cost"] * 100

        pos["shares"] -= shares
        if pos["shares"] <= 0:
            del portfolio["positions"][stock_code]

        portfolio["cash"] += revenue

        # 记录交易
        ensure_dirs()
        trade_log = os.path.join(HISTORY_DIR, f"trades_{datetime.now().strftime('%Y%m')}.json")
        trades = safe_load_json(trade_log, default=[])
        trades.append({
            "date": datetime.now().isoformat(),
            "code": stock_code,
            "name": stock_name,
            "action": action,
            "price": price,
            "shares": shares,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "reason": reason
        })
        safe_save_json(trade_log, trades)

    # 计算总资产
    total_value = portfolio["cash"]
    for code, pos in portfolio["positions"].items():
        if current_prices and code in current_prices:
            cp = current_prices[code]
        else:
            cp = pos["avg_cost"]
        total_value += cp * pos["shares"]

    portfolio["total_value"] = round(total_value, 2)
    portfolio["total_return_pct"] = round(
        (total_value - portfolio["total_capital"]) / portfolio["total_capital"] * 100, 2
    )

    save_portfolio(portfolio)
    return portfolio


def set_stop_loss(stock_code: str, stop_loss: float, take_profit: float = 0):
    """设置止损止盈"""
    portfolio = load_portfolio()
    if stock_code in portfolio["positions"]:
        portfolio["positions"][stock_code]["stop_loss"] = stop_loss
        portfolio["positions"][stock_code]["take_profit"] = take_profit
        save_portfolio(portfolio)


def check_stop_loss(current_prices: dict = None) -> List[Dict]:
    """检查止损止盈触发"""
    portfolio = load_portfolio()
    triggered = []

    for code, pos in portfolio["positions"].items():
        if current_prices and code in current_prices:
            current_price = current_prices[code]
        else:
            current_price = pos["avg_cost"]

        if pos.get("stop_loss", 0) > 0 and current_price <= pos["stop_loss"]:
            triggered.append({
                "code": code,
                "name": pos["name"],
                "action": "STOP_LOSS",
                "current_price": current_price,
                "stop_loss": pos["stop_loss"],
                "pnl_pct": round((current_price - pos["avg_cost"]) / pos["avg_cost"] * 100, 2)
            })

        if pos.get("take_profit", 0) > 0 and current_price >= pos["take_profit"]:
            triggered.append({
                "code": code,
                "name": pos["name"],
                "action": "TAKE_PROFIT",
                "current_price": current_price,
                "take_profit": pos["take_profit"],
                "pnl_pct": round((current_price - pos["avg_cost"]) / pos["avg_cost"] * 100, 2)
            })

    return triggered


def auto_sell_triggered(triggered_list: List[Dict], current_prices: dict = None):
    """自动卖出触发的持仓"""
    results = []
    for t in triggered_list:
        code = t["code"]
        name = t["name"]
        current_price = t["current_price"]
        action = t["action"]

        portfolio = load_portfolio()
        if code not in portfolio["positions"]:
            continue

        pos = portfolio["positions"][code]
        shares = pos["shares"]

        result = update_position(
            code, name, "sell", current_price, shares,
            reason=f"自动{action} 价格={current_price}",
            current_prices=current_prices
        )

        if "error" not in result:
            results.append({
                "code": code,
                "name": name,
                "action": action,
                "price": current_price,
                "shares": shares,
                "pnl_pct": t["pnl_pct"]
            })

    return results


def get_portfolio_summary(current_prices: dict = None) -> str:
    """获取持仓摘要"""
    portfolio = load_portfolio()

    if not portfolio["positions"]:
        return f"当前空仓，现金: {portfolio['cash']:.2f}"

    lines = [
        f"当前持仓（总资产: {portfolio.get('total_value', 0):.2f}元, "
        f"总收益: {portfolio.get('total_return_pct', 0):+.2f}%, "
        f"现金: {portfolio['cash']:.2f}元）:"
    ]

    for code, pos in portfolio["positions"].items():
        if current_prices and code in current_prices:
            current = current_prices[code]
        else:
            current = pos["avg_cost"]

        pnl_pct = (current - pos["avg_cost"]) / pos["avg_cost"] * 100
        lines.append(
            f"  {code} {pos['name']}: {pos['shares']}股 @ {pos['avg_cost']:.2f}元, "
            f"现价{current:.2f}元 ({pnl_pct:+.2f}%), "
            f"止损={pos.get('stop_loss', '未设')}, 止盈={pos.get('take_profit', '未设')}"
        )

    triggered = check_stop_loss(current_prices)
    if triggered:
        lines.append("\n⚠ 触发信号:")
        for t in triggered:
            lines.append(f"  {t['name']}: {t['action']} @ {t['current_price']:.2f}元")

    return "\n".join(lines)


def save_daily_report(report_text: str):
    """保存每日分析报告"""
    ensure_dirs()
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    filepath = os.path.join(HISTORY_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)
    return filepath


def get_trade_history(month: str = None) -> List[Dict]:
    """获取交易历史"""
    try:
        return load_trades_db(month=month)
    except Exception:
        if month is None:
            month = datetime.now().strftime("%Y%m")
        trade_log = os.path.join(HISTORY_DIR, f"trades_{month}.json")
        return safe_load_json(trade_log, default=[])


if __name__ == "__main__":
    print(get_portfolio_summary())
