"""持仓跟踪模块 - 记录每日推荐并对比实际走势"""
import json
import os
import threading
from datetime import datetime
from typing import Dict, List

import data_fetcher as df


PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "history")

# CrewAI 用线程池跑任务，持仓会被多个线程同时读写；这个锁只保证单进程内互斥。
_PORTFOLIO_LOCK = threading.RLock()


def ensure_dirs():
    os.makedirs(HISTORY_DIR, exist_ok=True)


def load_portfolio() -> Dict:
    """加载当前持仓"""
    with _PORTFOLIO_LOCK:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "positions": {},
        "cash": 100000,
        "total_capital": 100000,
        "created": datetime.now().isoformat(),
        "total_value": 100000,
        "total_return_pct": 0.0
    }


def save_portfolio(portfolio: Dict):
    """保存持仓

    先写临时文件再 os.replace，并整段持锁：
    直接 open("w") 时各文件对象持有自己的偏移，truncate 不会重置别人的偏移，
    并发刷新会把 JSON 写撕裂（实测出现过结尾 `}.0\n}`、load_portfolio 直接抛异常）。
    读侧也必须走 load_portfolio，否则 Windows 上 replace 会因读句柄未共享 DELETE 而报 PermissionError。
    """
    ensure_dirs()
    tmp = PORTFOLIO_FILE + ".tmp"
    with _PORTFOLIO_LOCK:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(portfolio, f, ensure_ascii=False, indent=2)
            os.replace(tmp, PORTFOLIO_FILE)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def _position_last_price(pos: Dict) -> float:
    """Position last price chain: explicitly passed price > refreshed last_price > avg_cost."""
    price = pos.get("last_price")
    if price and float(price) > 0:
        return float(price)
    return pos["avg_cost"]


def refresh_position_prices() -> Dict[str, float]:
    """Batch refresh last_price for all holdings and persist to portfolio.json.

    Same data source as the candidate pool in crew.py (data_fetcher.get_realtime_quotes:
    East Money direct with Sina K-line fallback). Read-modify-write goes through
    load_portfolio/save_portfolio so it stays lock-protected and atomic.
    Returns {code: price}; returns {} and leaves the file untouched when there is
    nothing to refresh or all quote fetches fail.
    """
    portfolio = load_portfolio()
    positions = portfolio.get("positions", {})
    if not positions:
        return {}

    try:
        quotes = df.get_realtime_quotes(list(positions.keys()))
    except Exception:
        quotes = []

    price_map = {}
    for q in quotes or []:
        code = q.get("code")
        price = q.get("price")
        if code and price and float(price) > 0:
            price_map[code] = round(float(price), 2)

    if not price_map:
        return {}

    now = datetime.now().isoformat()
    for code, price in price_map.items():
        if code in positions:
            positions[code]["last_price"] = price
            positions[code]["last_price_time"] = now

    total_value = portfolio["cash"]
    for code, pos in positions.items():
        total_value += _position_last_price(pos) * pos["shares"]
    portfolio["total_value"] = round(total_value, 2)
    portfolio["total_return_pct"] = round(
        (total_value - portfolio["total_capital"]) / portfolio["total_capital"] * 100, 2
    )

    save_portfolio(portfolio)
    return price_map



def _append_trade_log(stock_code: str, stock_name: str, action: str, price: float,
                      shares: int, pnl: float, pnl_pct: float, reason: str):
    """追加一条交易流水（买入也要记账）。"""
    # 记录交易（买入也要记账：9/26 run6 发现 trades 文件 78 条全是 sell，
    # 之前记录块嵌在 sell 分支里，所有买入在流水账里无痕）
    ensure_dirs()
    trade_log = os.path.join(HISTORY_DIR, f"trades_{datetime.now().strftime('%Y%m')}.json")
    # 读-改-写整段进锁：Windows 上 os.replace 遇到别人正开句柄读旧文件会
    # WinError 5 拒绝访问（实测 8 写并发 22/64 失败），读也必须持锁。
    with _PORTFOLIO_LOCK:
        trades = []
        if os.path.exists(trade_log):
            with open(trade_log, "r", encoding="utf-8") as f:
                trades = json.load(f)
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
        # 与 portfolio.json 同样的原子写：裸 open("w") 曾把 trades_202609.json
        # 写成"合法数组 + 另一线程残片"，之后每次读都抛 UnicodeDecodeError，
        # execute_sell 连续报错重试烧光 max_iter（9/26 run4 实测）。
        tmp = trade_log + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(trades, f, ensure_ascii=False, indent=2)
            os.replace(tmp, trade_log)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def _apply_buy(portfolio: Dict, stock_code: str, stock_name: str,
               price: float, shares: int):
    """把一笔买入合进 portfolio（加仓按均价，新建按成本价），返回成本。"""
    cost = price * shares
    if cost > portfolio["cash"]:
        return None

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
            "last_price": round(price, 2),
            "buy_date": datetime.now().strftime("%Y-%m-%d"),
            "stop_loss": 0,
            "take_profit": 0
        }

    portfolio["cash"] -= cost
    return cost


def _apply_sell(portfolio: Dict, stock_code: str, price: float, shares: int) -> tuple:
    """把一笔卖出合进 portfolio（超额卖出按全卖处理），返回 (pnl, pnl_pct, 实际股数)。"""
    if stock_code not in portfolio["positions"]:
        return None

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
    return (pnl, pnl_pct, shares)


def _recalc_totals(portfolio: Dict, current_prices: dict):
    """按 现价 > last_price > avg_cost 取值链重算总资产与总收益率。"""
    total_value = portfolio["cash"]
    for code, pos in portfolio["positions"].items():
        if current_prices and code in current_prices:
            cp = current_prices[code]
            pos["last_price"] = round(float(cp), 2)
            pos["last_price_time"] = datetime.now().isoformat()
        else:
            cp = _position_last_price(pos)
        total_value += cp * pos["shares"]

    portfolio["total_value"] = round(total_value, 2)
    portfolio["total_return_pct"] = round(
        (total_value - portfolio["total_capital"]) / portfolio["total_capital"] * 100, 2
    )


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

    pnl = 0.0
    pnl_pct = 0.0

    if action == "buy":
        if _apply_buy(portfolio, stock_code, stock_name, price, shares) is None:
            return {"error": "资金不足"}

    elif action == "sell":
        sold = _apply_sell(portfolio, stock_code, price, shares)
        if sold is None:
            return {"error": f"未持有 {stock_code}"}
        pnl, pnl_pct, shares = sold

    if action in ("buy", "sell"):
        _append_trade_log(stock_code, stock_name, action, price, shares,
                          pnl, pnl_pct, reason)

    # 计算总资产（现价取值链：current_prices > last_price > avg_cost）
    _recalc_totals(portfolio, current_prices)

    save_portfolio(portfolio)
    return portfolio




def set_stop_loss(stock_code: str, stop_loss: float, take_profit: float = 0):
    """设置止损止盈

    返回字典，不返回 None：tools/trade_tools.py 的 SetStopLossTool 会做
    `"error" in result` 判断，返回 None 时直接抛 TypeError（9/26 实测 6 次）。
    """
    portfolio = load_portfolio()
    if stock_code not in portfolio["positions"]:
        return {"error": f"not holding {stock_code}"}
    portfolio["positions"][stock_code]["stop_loss"] = stop_loss
    portfolio["positions"][stock_code]["take_profit"] = take_profit
    save_portfolio(portfolio)
    return {
        "success": True,
        "code": stock_code,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "message": f"set {stock_code} stop_loss={stop_loss:.2f} take_profit={take_profit:.2f}",
    }


def check_stop_loss(current_prices: dict = None) -> List[Dict]:
    """检查止损止盈触发"""
    portfolio = load_portfolio()
    triggered = []

    for code, pos in portfolio["positions"].items():
        if current_prices and code in current_prices:
            current_price = current_prices[code]
        else:
            current_price = _position_last_price(pos)

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
            current = _position_last_price(pos)

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
    if month is None:
        month = datetime.now().strftime("%Y%m")

    trade_log = os.path.join(HISTORY_DIR, f"trades_{month}.json")
    if os.path.exists(trade_log):
        with open(trade_log, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


if __name__ == "__main__":
    print(get_portfolio_summary())

