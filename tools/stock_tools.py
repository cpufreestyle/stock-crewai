"""
Stock research and analysis tools - Agent-callable stock screening/technical analysis interfaces
Wraps data_fetcher.py + technical_indicators.py + backtest.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from typing import Optional
from pydantic import BaseModel, Field
from tools.compat import BaseTool

import data_fetcher as df


# ── Fundamental Analysis ──────────────────────────────────────────────
class FundamentalAnalysisInput(BaseModel):
    code: str = Field(description="Stock code, e.g. '000858'. Multiple codes may be separated by commas.")

class FundamentalAnalysisTool(BaseTool):
    name: str = "fundamental_analysis"
    description: str = "Get stock fundamental indicators (PE/PB/MarketCap) for one or several codes in a single call"

    def _run(self, code: str = "", **kwargs) -> str:
        try:
            if not code:
                return json.dumps({"error": "please provide stock code"}, ensure_ascii=False)

            codes = [c.strip() for c in str(code).replace(" ", ",").split(",") if c.strip()]
            batch = df.get_fundamental_batch(codes)
            if not batch:
                # 取不到数据时必须显式报错：返回一串 None 字段会让智能体以为"字段本来就没有"，
                # 实测研究员因此对 5 只股票逐个调用本工具、耗尽 max_iter 后只输出提示语回显。
                return json.dumps({
                    "error": f"fundamental data unavailable for {','.join(codes)}; "
                             f"估值以下方内联行情数据为准，勿再重复调用本工具",
                }, ensure_ascii=False)

            items = [{"code": c, **batch.get(c, {"error": "no data"})} for c in codes]
            return json.dumps(items if len(items) > 1 else items[0], ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Stock Search ──────────────────────────────────────────────────────
class StockSearchInput(BaseModel):
    n_stocks: int = Field(default=10, description="Number of stocks to sample from pool")
    min_change: float = Field(default=0, description="Minimum change %")
    max_change: float = Field(default=6, description="Maximum change %")

class StockSearchTool(BaseTool):
    name: str = "stock_search"
    description: str = "Screen stocks from CSI300 candidate pool, return technical indicators (MA/RSI/change%, etc.)"

    def _run(self, n_stocks: int = 10, min_change: float = 0, max_change: float = 6, **kwargs) -> str:
        try:
            pool = df.get_index_components()["code"].tolist()[:n_stocks]
            prices_map = df.get_batch_stock_prices(pool)

            results = []
            for code in pool:
                price_data = prices_map.get(code)
                if price_data is None or price_data.empty:
                    continue

                tech = df.calculate_technical(price_data)
                name = code
                sector = ""
                for s in df.A_SHARE_POOL:
                    if s["code"] == code:
                        name = s["name"]
                        sector = s["sector"]
                        break

                change_pct = tech.get("5日涨跌", 0)
                if not (min_change <= change_pct <= max_change):
                    continue

                results.append({
                    "code": code,
                    "name": name,
                    "sector": sector,
                    "close": tech.get("收盘价", "N/A"),
                    "MA5": tech.get("MA5", "N/A"),
                    "MA20": tech.get("MA20", "N/A"),
                    "RSI": tech.get("RSI", 50),
                    "change_5d": f"{change_pct:+.1f}%",
                    "MA_bullish": tech.get("MA5", 0) > tech.get("MA20", 999),
                })

            # Sort by 5-day change
            results.sort(key=lambda x: float(x["change_5d"].replace("%", "").replace("+", "")), reverse=True)

            return json.dumps(results[:10], ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Technical Analysis ──────────────────────────────────────────────────────
class TechnicalAnalysisInput(BaseModel):
    code: str = Field(description="Stock code, e.g. '000858'")

class TechnicalAnalysisTool(BaseTool):
    name: str = "technical_analysis"
    description: str = "Calculate single stock technical indicators and signals (MA/MACD/RSI/KDJ/Bollinger)"

    def _run(self, code: str = "", **kwargs) -> str:
        try:
            if not code:
                return json.dumps({"error": "please provide stock code"}, ensure_ascii=False)

            # Try using technical_indicators module
            try:
                import technical_indicators as ti
                analysis = ti.analyze_stock(code)
                if "error" not in analysis:
                    return json.dumps(analysis, ensure_ascii=False, default=str)
            except ImportError:
                pass

            # Fallback: use data_fetcher's simple technical indicators
            pool = [code]
            prices_map = df.get_batch_stock_prices(pool)
            price_data = prices_map.get(code)

            if price_data is None or price_data.empty:
                return json.dumps({"error": f"cannot get data for {code}"}, ensure_ascii=False)

            tech = df.calculate_technical(price_data)

            # Find stock name
            name = code
            for s in df.A_SHARE_POOL:
                if s["code"] == code:
                    name = s["name"]
                    break

            return json.dumps({
                "code": code,
                "name": name,
                "close": tech.get("收盘价"),
                "MA5": tech.get("MA5"),
                "MA10": tech.get("MA10"),
                "MA20": tech.get("MA20"),
                "RSI": tech.get("RSI"),
                "MACD": tech.get("MACD"),
                "MACD_signal": tech.get("MACD_signal"),
                "MACD_hist": tech.get("MACD_hist"),
                "BOLL_upper": tech.get("BOLL_upper"),
                "BOLL_mid": tech.get("BOLL_mid"),
                "BOLL_lower": tech.get("BOLL_lower"),
                "change_5d": tech.get("5日涨跌"),
                "trend": "bullish" if tech.get("MA5", 0) > tech.get("MA20", 999) else "bearish",
            }, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── News Sentiment ──────────────────────────────────────────────────────
class NewsSentimentInput(BaseModel):
    days: int = Field(default=2, description="Get news from last N days")
    keyword: str = Field(default="", description="Search keyword")

class NewsSentimentTool(BaseTool):
    name: str = "news_sentiment"
    description: str = "Get recent financial news and sentiment analysis"

    def _run(self, days: int = 2, keyword: str = "", **kwargs) -> str:
        try:
            news = df.get_news_sentiment(days=days)
            if not news:
                return json.dumps({"info": "no news data available"}, ensure_ascii=False)

            results = []
            for n in news[:8]:
                results.append({
                    "title": str(n.get("新闻标题", n.get("title", "")))[:80],
                    "time": n.get("发布时间", n.get("date", "")),
                    "source": n.get("来源", n.get("source", "")),
                })

            return json.dumps(results, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


# ── Backtest ──────────────────────────────────────────────────────
class BacktestInput(BaseModel):
    code: str = Field(description="Stock code, or several codes separated by commas to backtest all of them in one call")

class BacktestTool(BaseTool):
    name: str = "backtest"
    description: str = "Run multi-strategy backtest for one or several comma-separated stocks; returns returns, max drawdown, win rate"

    def _run(self, code: str = "", **kwargs) -> str:
        try:
            if not code:
                return json.dumps({"error": "please provide stock code"}, ensure_ascii=False)

            from backtest import multi_strategy_backtest

            codes = [c.strip() for c in str(code).replace(" ", ",").split(",") if c.strip()]

            def _one(c: str) -> dict:
                result = multi_strategy_backtest(c)
                if "error" in result:
                    return {"code": c, **result}
                strategies = []
                for name, data in result.get("strategies", {}).items():
                    strategies.append({
                        "strategy": name,
                        "return_rate": data.get("收益率", "N/A"),
                        "max_drawdown": data.get("最大回撤", "N/A"),
                        "win_rate": data.get("胜率", "N/A"),
                        "current_position": data.get("当前持仓", "N/A"),
                    })
                return {
                    "code": c,
                    "strategies": strategies,
                    "best_strategy": result.get("best_strategy", "N/A"),
                    "best_return": result.get("best_return", "N/A"),
                }

            # 多只一次跑完：逐只调用会把 max_iter 一轮轮烧光（run6 研究员就是这么失败的）
            results = [_one(c) for c in codes]
            return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Tool Registration ──────────────────────────────────────────────────────
def get_stock_tools() -> list:
    """Return all stock research/analysis tools"""
    return [
        FundamentalAnalysisTool(),
        StockSearchTool(),
        TechnicalAnalysisTool(),
        NewsSentimentTool(),
        BacktestTool(),
    ]
