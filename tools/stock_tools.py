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
    code: str = Field(description="Stock code, e.g. '000858'")

class FundamentalAnalysisTool(BaseTool):
    name: str = "fundamental_analysis"
    description: str = "Get stock fundamental indicators (PE/PB/ROE/MarketCap/Revenue/Profit)"

    def _run(self, code: str = "", **kwargs) -> str:
        try:
            if not code:
                return json.dumps({"error": "please provide stock code"}, ensure_ascii=False)

            # Try to fetch fundamental data
            # In production, this would call a real API (e.g., AKShare, Tushare)
            # For now, return sample data structure
            
            # TODO: Implement real fundamental data fetching
            # Example using AKShare:
            # import akshare as ak
            # df = ak.stock_financial_analysis_indicator(symbol=code)
            
            # Sample data structure
            fundamental_data = {
                "code": code,
                "name": self._get_stock_name(code),
                "PE": None,   # 市盈率
                "PB": None,   # 市净率
                "ROE": None,  # 净资产收益率
                "MarketCap": None,  # 总市值
                "Revenue_growth": None,  # 营收增速
                "Profit_growth": None,  # 利润增速
                "Debt_ratio": None,  # 资产负债率
                "Dividend_yield": None,  # 股息率
            }
            
            # Try to fetch real data if data_fetcher supports it
            if hasattr(df, 'get_fundamental_data'):
                real_data = df.get_fundamental_data(code)
                if real_data and 'error' not in real_data:
                    fundamental_data.update(real_data)
            
            return json.dumps(fundamental_data, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _get_stock_name(self, code: str) -> str:
        """Get stock name from pool"""
        for s in df.A_SHARE_POOL:
            if s["code"] == code:
                return s["name"]
        return code


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
    code: str = Field(description="Stock code")

class BacktestTool(BaseTool):
    name: str = "backtest"
    description: str = "Run multi-strategy backtest for specified stock, return returns, max drawdown, win rate"

    def _run(self, code: str = "", **kwargs) -> str:
        try:
            if not code:
                return json.dumps({"error": "please provide stock code"}, ensure_ascii=False)

            from backtest import multi_strategy_backtest
            result = multi_strategy_backtest(code)

            if "error" in result:
                return json.dumps(result, ensure_ascii=False)

            strategies = []
            for name, data in result.get("strategies", {}).items():
                strategies.append({
                    "strategy": name,
                    "return_rate": data.get("收益率", "N/A"),
                    "max_drawdown": data.get("最大回撤", "N/A"),
                    "win_rate": data.get("胜率", "N/A"),
                    "current_position": data.get("当前持仓", "N/A"),
                })

            return json.dumps({
                "code": code,
                "strategies": strategies,
                "best_strategy": result.get("best_strategy", "N/A"),
                "best_return": result.get("best_return", "N/A"),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


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
