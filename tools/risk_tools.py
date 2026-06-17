"""
Risk management tools - Agent-callable risk assessment interfaces
Wraps risk_manager.py + circuit_breaker.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from pydantic import BaseModel, Field
from tools.compat import BaseTool

import risk_manager as rm
import portfolio_tracker as pt


# ── Kelly Position ──────────────────────────────────────────────────────
class KellyPositionInput(BaseModel):
    win_rate: float = Field(description="Win rate (0-1)")
    avg_win: float = Field(description="Average win ratio (e.g. 0.15)")
    avg_loss: float = Field(description="Average loss ratio (e.g. 0.10)")

class KellyPositionTool(BaseTool):
    name: str = "kelly_position"
    description: str = "Calculate optimal position ratio using Kelly formula, based on win rate and profit/loss ratio"

    def _run(self, win_rate: float = 0.5, avg_win: float = 0.15, avg_loss: float = 0.10, **kwargs) -> str:
        try:
            position = rm.kelly_criterion(win_rate, avg_win, avg_loss)
            return json.dumps({
                "win_rate": f"{win_rate*100:.1f}%",
                "avg_win": f"{avg_win*100:.1f}%",
                "avg_loss": f"{avg_loss*100:.1f}%",
                "kelly_position": f"{position*100:.1f}%",
                "suggestion": "position reasonable" if position > 0.05 else "suggest no trade (position too low)",
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Position Size ──────────────────────────────────────────────────────
class PositionSizeInput(BaseModel):
    entry_price: float = Field(description="Entry price")
    stop_loss_pct: float = Field(default=0.10, description="Stop loss percentage (default 10%)")
    risk_per_trade: float = Field(default=0.02, description="Risk per trade percentage (default 2%)")

class PositionSizeTool(BaseTool):
    name: str = "position_size"
    description: str = "Calculate buy shares and position size based on risk control"

    def _run(self, entry_price: float = 0, stop_loss_pct: float = 0.10,
             risk_per_trade: float = 0.02, **kwargs) -> str:
        try:
            if entry_price <= 0:
                return json.dumps({"error": "entry price must be > 0"}, ensure_ascii=False)

            portfolio = pt.load_portfolio()
            total_capital = portfolio.get("total_capital", 100000)

            result = rm.position_size(
                total_capital=total_capital,
                entry_price=entry_price,
                stop_loss_pct=stop_loss_pct,
                risk_per_trade=risk_per_trade,
            )

            return json.dumps({
                "total_capital": total_capital,
                "shares": result["shares"],
                "position_value": result["position_value"],
                "position_pct": f"{result['position_pct']:.1f}%",
                "risk_amount": result["risk_amount"],
                "stop_loss_price": result["stop_loss_price"],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Risk Reward Ratio ──────────────────────────────────────────────────────
class RiskRewardInput(BaseModel):
    entry: float = Field(description="Entry price")
    target: float = Field(description="Target price")
    stop: float = Field(description="Stop loss price")

class RiskRewardTool(BaseTool):
    name: str = "risk_reward"
    description: str = "Calculate risk-reward ratio, determine if trade is worthwhile (need >= 2:1)"

    def _run(self, entry: float = 0, target: float = 0, stop: float = 0, **kwargs) -> str:
        try:
            if entry <= 0 or target <= 0 or stop <= 0:
                return json.dumps({"error": "price parameters must be > 0"}, ensure_ascii=False)

            result = rm.risk_reward_ratio(entry, target, stop)

            return json.dumps({
                "entry": entry,
                "target": target,
                "stop": stop,
                "risk": result["risk"],
                "reward": result["reward"],
                "risk_reward_ratio": f"{result['risk_reward_ratio']:.1f}:1",
                "is_valid": "Yes" if result["is_valid"] else "No",
                "recommendation": result["recommendation"],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Portfolio Risk ──────────────────────────────────────────────────────
class PortfolioRiskInput(BaseModel):
    pass

class PortfolioRiskTool(BaseTool):
    name: str = "portfolio_risk"
    description: str = "Assess overall risk exposure of current portfolio (VaR, position ratios, etc.)"

    def _run(self, **kwargs) -> str:
        try:
            portfolio = pt.load_portfolio()
            positions = portfolio.get("positions", {})
            total_capital = portfolio.get("total_capital", 100000)

            if not positions:
                return json.dumps({"status": "empty position", "risk": "none"}, ensure_ascii=False)

            pos_list = []
            for code, pos in positions.items():
                pos_list.append({
                    "code": code,
                    "shares": pos["shares"],
                    "avg_cost": pos["avg_cost"],
                    "stop_loss": pos.get("stop_loss", 0),
                })

            result = rm.calculate_portfolio_risk(pos_list, total_capital)

            return json.dumps({
                "total_exposure": result["total_exposure"],
                "exposure_pct": f"{result['total_exposure_pct']:.1f}%",
                "var_1day_95": result["estimated_var_1day"],
                "var_5day_95": result["estimated_var_5day"],
                "positions_count": result["positions_count"],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Circuit Breaker Check ──────────────────────────────────────────────────────
class CircuitBreakerCheckInput(BaseModel):
    pass

class CircuitBreakerCheckTool(BaseTool):
    name: str = "circuit_breaker_check"
    description: str = "Check if risk control circuit breaker is triggered (consecutive losses / excessive drawdown)"

    def _run(self, **kwargs) -> str:
        try:
            from circuit_breaker import CircuitBreaker
            cb = CircuitBreaker()

            portfolio = pt.load_portfolio()
            total_value = portfolio.get("total_value", 100000)

            can_trade = cb.can_trade(total_value)

            return json.dumps({
                "can_trade": "Yes" if can_trade else "No (circuit breaker triggered)",
                "consecutive_stops": cb._state.get("consecutive_stops", 0),
                "is_tripped": cb._state.get("tripped", False),
                "trip_reason": cb._state.get("trip_reason", ""),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "can_trade": "Yes",
                "note": "circuit breaker module unavailable, default allow",
            }, ensure_ascii=False)


# ── Stop Loss Advice ──────────────────────────────────────────────────────
class StopLossAdviceInput(BaseModel):
    entry_price: float = Field(description="Entry price")
    strategy: str = Field(default="moderate", description="Strategy: conservative/moderate/aggressive")

class StopLossAdviceTool(BaseTool):
    name: str = "stop_loss_advice"
    description: str = "Recommend stop loss price based on strategy type (conservative 5%/moderate 8%/aggressive 12%)"

    def _run(self, entry_price: float = 0, strategy: str = "moderate", **kwargs) -> str:
        try:
            if entry_price <= 0:
                return json.dumps({"error": "entry price must be > 0"}, ensure_ascii=False)

            result = rm.recommended_stop_loss(entry_price, strategy)

            return json.dumps({
                "entry_price": entry_price,
                "strategy": strategy,
                "stop_loss_price": result["stop_loss_price"],
                "stop_loss_pct": f"{result['stop_loss_pct']:.1f}%",
                "max_loss_per_share": result["max_loss_per_share"],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Tool Registration ──────────────────────────────────────────────────────
def get_risk_tools() -> list:
    """Return all risk management tools"""
    return [
        KellyPositionTool(),
        PositionSizeTool(),
        RiskRewardTool(),
        PortfolioRiskTool(),
        CircuitBreakerCheckTool(),
        StopLossAdviceTool(),
    ]
