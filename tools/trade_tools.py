"""
Trade execution tools - Agent-callable buy/sell execution interfaces
Wraps portfolio_tracker.py + broker_trader.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from pydantic import BaseModel, Field
from tools.compat import BaseTool

import portfolio_tracker as pt
import data_fetcher as df

logger = logging.getLogger("tools.trade")

# 真值集合按环境变量惯例从宽：1/true/yes/on 都算开。
_TRUTHY = {"1", "true", "yes", "on"}

# 拼进三个写工具的 description：万一它们又被塞回某个 LLM 的工具集，
# 模型至少能提前知道这个工具在默认配置下只会拒绝，不至于反复重试烧光 max_iter。
_GATE_NOTE = " Refuses with advice_only=true unless ALLOW_AGENT_TRADING=1 is set."


def trading_allowed() -> bool:
    """下单类工具的总开关，默认拒绝。

    分析流水线不得改持仓：crew.py 每交易日 15:35 由计划任务无人值守触发，
    10-02 那次日报真的清仓了 000425 六百股并写进 result_latest.md 的"已执行操作"。
    crew.py 已在工具白名单层面剔除这三个工具，但 workflows/daily_analysis.py 走的是
    AgentBase.run() 旧编排路径，agents/*.py 的 self.tools 仍含 get_trade_tools()，
    手动跑 main.py 或点 web_dashboard 一样会真下单——所以这里再兜一道。
    run_virtual_v4.py 的模拟盘下单直接调 portfolio_tracker，不经过本模块，不受影响。
    """
    return (os.getenv("ALLOW_AGENT_TRADING", "") or "").strip().lower() in _TRUTHY


def _refusal(action: str) -> str:
    logger.warning(
        "[trade] %s 被拒：未设 ALLOW_AGENT_TRADING，当前为只出建议模式", action
    )
    return json.dumps({
        "success": False,
        "advice_only": True,
        "error": (
            f"{action} refused: agent trading is disabled. "
            "This pipeline only produces advice and must not modify portfolio.json. "
            "Set ALLOW_AGENT_TRADING=1 to enable real order placement."
        ),
    }, ensure_ascii=False)


# ── Execute Buy ──────────────────────────────────────────────────────
class ExecuteBuyInput(BaseModel):
    code: str = Field(description="Stock code")
    name: str = Field(default="", description="Stock name")
    price: float = Field(description="Buy price")
    shares: int = Field(description="Buy shares (must be multiple of 100)")
    reason: str = Field(default="", description="Buy reason")

class ExecuteBuyTool(BaseTool):
    name: str = "execute_buy"
    description: str = "Execute buy operation (virtual account), update position and funds. Checks fund sufficiency before buying." + _GATE_NOTE

    def _run(self, code: str = "", name: str = "", price: float = 0,
             shares: int = 0, reason: str = "", **kwargs) -> str:
        if not trading_allowed():
            return _refusal("execute_buy")
        try:
            if not code or price <= 0 or shares <= 0:
                return json.dumps({"error": "incomplete parameters: need code, price, shares"}, ensure_ascii=False)

            if shares % 100 != 0:
                shares = (shares // 100) * 100  # round to 100s
                if shares <= 0:
                    return json.dumps({"error": "shares less than 100"}, ensure_ascii=False)

            # Get realtime price (if price=0, use current price)
            current_prices = {}
            if price == 0:
                try:
                    quotes = df.get_realtime_quotes([code])
                    if quotes:
                        price = quotes[0].get("price", 0)
                        current_prices[code] = price
                except:
                    pass

            result = pt.update_position(
                stock_code=code,
                stock_name=name,
                action="buy",
                price=price,
                shares=shares,
                reason=reason,
                current_prices=current_prices if current_prices else {code: price},
            )

            if "error" in result:
                return json.dumps({"success": False, "error": result["error"]}, ensure_ascii=False)

            return json.dumps({
                "success": True,
                "action": "buy",
                "code": code,
                "name": name,
                "price": price,
                "shares": shares,
                "cost": price * shares,
                "message": f"Bought {name}({code}) {shares} shares @ {price:.2f}",
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


# ── Execute Sell ──────────────────────────────────────────────────────
class ExecuteSellInput(BaseModel):
    code: str = Field(description="Stock code")
    price: float = Field(default=0, description="Sell price (0=current price)")
    shares: int = Field(default=0, description="Sell shares (0=sell all)")
    reason: str = Field(default="", description="Sell reason")

class ExecuteSellTool(BaseTool):
    name: str = "execute_sell"
    description: str = "Execute sell operation (virtual account), update position and funds. Can sell all or partially." + _GATE_NOTE

    def _run(self, code: str = "", price: float = 0, shares: int = 0,
             reason: str = "", **kwargs) -> str:
        if not trading_allowed():
            return _refusal("execute_sell")
        try:
            if not code:
                return json.dumps({"error": "please provide stock code"}, ensure_ascii=False)

            # Load portfolio
            portfolio = pt.load_portfolio()
            positions = portfolio.get("positions", {})

            if code not in positions:
                return json.dumps({"error": f"not holding {code}"}, ensure_ascii=False)

            pos = positions[code]
            name = pos["name"]

            # If shares=0, sell all
            if shares <= 0:
                shares = pos["shares"]

            # Get realtime price
            current_prices = {}
            if price <= 0:
                try:
                    quotes = df.get_realtime_quotes([code])
                    if quotes:
                        price = quotes[0].get("price", 0)
                        current_prices[code] = price
                except:
                    price = pos.get("last_price", pos["avg_cost"])

            if not current_prices:
                current_prices = {code: price}

            result = pt.update_position(
                stock_code=code,
                stock_name=name,
                action="sell",
                price=price,
                shares=shares,
                reason=reason,
                current_prices=current_prices,
            )

            if "error" in result:
                return json.dumps({"success": False, "error": result["error"]}, ensure_ascii=False)

            pnl = (price - pos["avg_cost"]) * shares
            return json.dumps({
                "success": True,
                "action": "sell",
                "code": code,
                "name": name,
                "price": price,
                "shares": shares,
                "pnl": round(pnl, 2),
                "message": f"Sold {name}({code}) {shares} shares @ {price:.2f}, PnL {pnl:+.2f}",
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


# ── Set Stop Loss / Take Profit ──────────────────────────────────────────────────────
class SetStopLossInput(BaseModel):
    code: str = Field(description="Stock code")
    stop_loss: float = Field(description="Stop loss price")
    take_profit: float = Field(description="Take profit price")

class SetStopLossTool(BaseTool):
    name: str = "set_stop_loss"
    description: str = "Set stop loss and take profit prices for a stock" + _GATE_NOTE

    def _run(self, code: str = "", stop_loss: float = 0, take_profit: float = 0, **kwargs) -> str:
        if not trading_allowed():
            return _refusal("set_stop_loss")
        try:
            if not code:
                return json.dumps({"error": "please provide stock code"}, ensure_ascii=False)

            result = pt.set_stop_loss(code, stop_loss, take_profit)

            if "error" in result:
                return json.dumps({"success": False, "error": result["error"]}, ensure_ascii=False)

            return json.dumps({
                "success": True,
                "code": code,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "message": f"Set {code} stop_loss={stop_loss:.2f} take_profit={take_profit:.2f}",
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


# ── View Portfolio ──────────────────────────────────────────────────────
class ViewPortfolioInput(BaseModel):
    pass

class ViewPortfolioTool(BaseTool):
    name: str = "view_portfolio"
    description: str = "View current portfolio status: holdings, cash, total assets, PnL"

    def _run(self, **kwargs) -> str:
        try:
            # 只回 summary：raw 里整份 portfolio（含 last_price_time 等字段）
            # 对 27B 本地模型是纯 token 浪费，summary 已覆盖持仓/止损止盈/总资产。
            summary = pt.get_portfolio_summary()
            return json.dumps({"summary": summary}, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Tool Registration ──────────────────────────────────────────────────────
def get_trade_tools() -> list:
    """Return all trade execution tools"""
    return [
        ExecuteBuyTool(),
        ExecuteSellTool(),
        SetStopLossTool(),
        ViewPortfolioTool(),
    ]
