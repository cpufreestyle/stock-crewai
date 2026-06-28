"""
Market data tools - Agent-callable market data interfaces
Wraps data_fetcher.py functions as BaseTool tools
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from typing import Type, Optional
from pydantic import BaseModel, Field
from tools.compat import BaseTool

import data_fetcher as df


# ── Market Heat ──────────────────────────────────────────────────────
class MarketHeatInput(BaseModel):
    """No input parameters required"""
    pass

class MarketHeatTool(BaseTool):
    name: str = "market_heat"
    description: str = "Get A-share market heat indicators: limit-up count, limit-down count, market status, rise/fall counts"

    def _run(self, **kwargs) -> str:
        try:
            heat = df.get_market_heat()
            return json.dumps({
                "limit_up_count": heat.get("涨停家数", "N/A"),
                "limit_down_count": heat.get("跌停家数", "N/A"),
                "market_status": heat.get("市场状态", "N/A"),
                "date": heat.get("日期", ""),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Market Regime ──────────────────────────────────────────────────────
class MarketRegimeInput(BaseModel):
    pass

class MarketRegimeTool(BaseTool):
    name: str = "market_regime"
    description: str = "Determine current A-share market regime (bull/bear/range) and confidence level"

    def _run(self, **kwargs) -> str:
        try:
            regime = df.get_market_regime()
            return json.dumps({
                "regime": regime.get("regime", "unknown"),
                "confidence": regime.get("confidence", 0),
                "signals": regime.get("signals", [])[:5],
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Sector Rotation ──────────────────────────────────────────────────────
class SectorRotationInput(BaseModel):
    top_n: int = Field(default=5, description="Return top N sectors")

class SectorRotationTool(BaseTool):
    name: str = "sector_rotation"
    description: str = "Get sector rotation ranking, find current strong and weak sectors"

    def _run(self, top_n: int = 5, **kwargs) -> str:
        try:
            sectors = df.get_sector_performance()
            if not sectors:
                return json.dumps({"error": "sector data temporarily unavailable"}, ensure_ascii=False)

            result = []
            for s in sectors[:top_n]:
                result.append({
                    "sector": s.get("name", ""),
                    "change_pct": f"{s.get('change_pct', 0):+.2f}%",
                    "leading_stock": s.get("top_stock", ""),
                })

            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Realtime Quotes ──────────────────────────────────────────────────────
class RealtimeQuotesInput(BaseModel):
    codes: str = Field(description="Comma-separated stock codes, e.g. '000858,600519'")

class RealtimeQuotesTool(BaseTool):
    name: str = "realtime_quotes"
    description: str = "Get stock realtime quotes: price, change%, volume, etc."

    def _run(self, codes: str = "", **kwargs) -> str:
        try:
            code_list = [c.strip() for c in codes.split(",") if c.strip()]
            if not code_list:
                return json.dumps({"error": "please provide stock codes"}, ensure_ascii=False)

            quotes = df.get_realtime_quotes(code_list)
            result = []
            for q in quotes:
                result.append({
                    "code": q.get("code", ""),
                    "name": q.get("name", ""),
                    "price": q.get("price", 0),
                    "change_pct": f"{q.get('change_pct', 0):+.2f}%",
                    "volume": q.get("volume", 0),
                })

            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Tool Registration ──────────────────────────────────────────────────────
def get_market_tools() -> list:
    """Return all market data tools"""
    return [
        MarketHeatTool(),
        MarketRegimeTool(),
        SectorRotationTool(),
        RealtimeQuotesTool(),
    ]


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    tools = get_market_tools()
    print("Market tools:")
    for t in tools:
        print(f"  - {t.name}: {t.description}")
