"""
Trade execution tools - Agent-callable buy/sell execution interfaces
Wraps portfolio_tracker.py + broker_trader.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from pydantic import BaseModel, Field
from tools.compat import BaseTool

import portfolio_tracker as pt
import data_fetcher as df


# ── Execute Buy ──────────────────────────────────────────────────────
class ExecuteBuyInput(BaseModel):
    code: str = Field(description="Stock code")
    name: str = Field(default="", description="Stock name")
    price: float = Field(description="Buy price")
    shares: int = Field(description="Buy shares (must be multiple of 100)")
    reason: str = Field(default="", description="Buy reason")

class ExecuteBuyTool(BaseTool):
    name: str = "execute_buy"
    description: str = "Execute buy operation (virtual account), update position and funds. Checks fund sufficiency before buying."

    def _run(self, code: str = "", name: str = "", price: float = 0,
             shares: int = 0, reason: str = "", **kwargs) -> str:
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
    description: str = "Execute sell operation (virtual account), update position and funds. Can sell all or partially."

    def _run(self, code: str = "", price: float = 0, shares: int = 0,
             reason: str = "", **kwargs) -> str:
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
    description: str = "Set stop loss and take profit prices for a stock"

    def _run(self, code: str = "", stop_loss: float = 0, take_profit: float = 0, **kwargs) -> str:
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
            portfolio = pt.load_portfolio()
            summary = pt.get_portfolio_summary()
            return json.dumps({
                "raw": portfolio,
                "summary": summary,
            }, ensure_ascii=False, default=str)
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
