"""
数据适配器 - 桥接 stock-crewai 原有数据源 + 新增 Tushare 基本面数据
"""
import sys
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("v5.data_adapter")

# 添加项目根目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class DataAdapter:
    """统一数据接口 - 整合行情+基本面+新闻"""

    def __init__(self):
        from v5.config import DATA_SOURCES

        self.tushare_token = DATA_SOURCES["tushare"]["token"]
        self._tushare = None
        self._akshare = None

        # 延迟初始化
        logger.info("[DataAdapter] initialized")

    # ── 行情数据（复用 v4 新浪API）──

    def get_realtime_quote(self, stock_code: str) -> Dict:
        """获取实时行情 - 复用 v4 的新浪API"""
        try:
            from data_fetcher import fetch_realtime_quote
            return fetch_realtime_quote(stock_code)
        except Exception as e:
            logger.warning(f"[DataAdapter] sina realtime failed for {stock_code}: {e}")
            return {}

    def get_kline_data(self, stock_code: str, days: int = 60) -> Dict:
        """获取历史K线 - 复用 v4 的腾讯API"""
        try:
            from data_fetcher import fetch_kline_data
            return fetch_kline_data(stock_code, days)
        except Exception as e:
            logger.warning(f"[DataAdapter] kline failed for {stock_code}: {e}")
            return {}

    def get_technical_indicators(self, stock_code: str) -> Dict:
        """获取技术指标 - 复用 v4"""
        try:
            from technical_indicators import compute_all_indicators
            kline = self.get_kline_data(stock_code)
            if kline:
                return compute_all_indicators(kline)
        except Exception as e:
            logger.warning(f"[DataAdapter] tech indicators failed for {stock_code}: {e}")
        return {}

    # ── 基本面数据（新增 - Tushare）──

    def get_fundamentals(self, stock_code: str) -> Dict:
        """获取基本面数据 - PE/PB/ROE/净利润增速等"""
        if not self.tushare_token:
            logger.warning("[DataAdapter] no tushare token, using akshare fallback")
            return self._get_fundamentals_akshare(stock_code)

        try:
            ts = self._get_tushare()
            # 转换代码格式: 000333 -> 000333.SZ
            ts_code = self._to_tushare_code(stock_code)

            # 基本面指标
            daily_basic = ts.daily_basic(
                ts_code=ts_code,
                fields="ts_code,trade_date,pe,pb,ps,total_mv,circ_mv,turnover_rate,dv_ratio"
            )

            # 财务数据
            fina_indicator = ts.fina_indicator(
                ts_code=ts_code,
                fields="ts_code,ann_date,end_date,roe,roe_waa,grossprofit_margin,netprofit_margin,q_profit_yoy"
            )

            result = {
                "pe": None,
                "pb": None,
                "ps": None,
                "total_mv": None,
                "circ_mv": None,
                "turnover_rate": None,
                "dv_ratio": None,
                "roe": None,
                "grossprofit_margin": None,
                "netprofit_margin": None,
                "profit_yoy": None,
            }

            if daily_basic is not None and len(daily_basic) > 0:
                row = daily_basic.iloc[0].to_dict()
                for k in ["pe", "pb", "ps", "total_mv", "circ_mv", "turnover_rate", "dv_ratio"]:
                    if k in row and row[k] is not None:
                        result[k] = float(row[k])

            if fina_indicator is not None and len(fina_indicator) > 0:
                row = fina_indicator.iloc[0].to_dict()
                for k in ["roe", "grossprofit_margin", "netprofit_margin", "q_profit_yoy"]:
                    if k in row and row[k] is not None:
                        result[k] = float(row[k])
                if "q_profit_yoy" in row and row["q_profit_yoy"] is not None:
                    result["profit_yoy"] = float(row["q_profit_yoy"])

            logger.info(f"[DataAdapter] fundamentals for {stock_code}: PE={result['pe']}, PB={result['pb']}")
            return result

        except Exception as e:
            logger.error(f"[DataAdapter] tushare fundamentals failed for {stock_code}: {e}")
            return self._get_fundamentals_akshare(stock_code)

    def _get_fundamentals_akshare(self, stock_code: str) -> Dict:
        """AkShare 备用基本面数据"""
        try:
            ak = self._get_akshare()
            # 个股指标
            df = ak.stock_individual_info_em(symbol=stock_code)
            result = {}
            for _, row in df.iterrows():
                key = row.get("item", "")
                val = row.get("value", "")
                if key == "市盈率(动态)":
                    result["pe"] = float(val) if val and val != "-" else None
                elif key == "市净率":
                    result["pb"] = float(val) if val and val != "-" else None
                elif key == "总市值":
                    result["total_mv"] = float(val) if val and val != "-" else None
            return result
        except Exception as e:
            logger.warning(f"[DataAdapter] akshare fundamentals failed: {e}")
            return {}

    # ── 新闻数据（新增）──

    def get_news(self, stock_code: str, limit: int = 10) -> List[Dict]:
        """获取个股新闻 - AkShare"""
        try:
            ak = self._get_akshare()
            name = self._get_stock_name(stock_code)
            df = ak.stock_news_em(symbol=stock_code)
            news_list = []
            for _, row in df.head(limit).iterrows():
                news_list.append({
                    "title": row.get("新闻标题", ""),
                    "content": row.get("新闻内容", "")[:200],
                    "date": str(row.get("发布时间", "")),
                    "source": row.get("文章来源", ""),
                })
            logger.info(f"[DataAdapter] got {len(news_list)} news for {stock_code}")
            return news_list
        except Exception as e:
            logger.warning(f"[DataAdapter] news failed for {stock_code}: {e}")
            return []

    # ── 社交情绪（新增）──

    def get_social_sentiment(self, stock_code: str) -> Dict:
        """获取社交情绪 - 简化版，基于新闻标题情感分析"""
        news = self.get_news(stock_code, limit=5)
        if not news:
            return {"sentiment": "neutral", "score": 0, "source": "no_news"}

        # 简单关键词情感分析
        positive_words = ["利好", "增长", "突破", "上涨", "超预期", "增持", "回购", "创新高"]
        negative_words = ["利空", "下跌", "亏损", "减持", "违规", "暴雷", "退市", "警示", "风险"]

        titles = " ".join([n["title"] for n in news])
        pos_count = sum(1 for w in positive_words if w in titles)
        neg_count = sum(1 for w in negative_words if w in titles)

        if pos_count > neg_count:
            return {"sentiment": "positive", "score": pos_count - neg_count, "source": "news_keywords"}
        elif neg_count > pos_count:
            return {"sentiment": "negative", "score": neg_count - pos_count, "source": "news_keywords"}
        else:
            return {"sentiment": "neutral", "score": 0, "source": "news_keywords"}

    # ── 辅助方法 ──

    def _get_tushare(self):
        if self._tushare is None:
            import tushare as ts
            ts.set_token(self.tushare_token)
            self._tushare = ts.pro_api()
        return self._tushare

    def _get_akshare(self):
        if self._akshare is None:
            import akshare as ak
            self._akshare = ak
        return self._akshare

    def _to_tushare_code(self, code: str) -> str:
        """000333 -> 000333.SZ, 600519 -> 600519.SH"""
        if code.startswith("6"):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"

    def _get_stock_name(self, code: str) -> str:
        """通过实时行情获取股票名称"""
        q = self.get_realtime_quote(code)
        return q.get("name", code)


# 全局实例
_adapter: Optional[DataAdapter] = None


def get_adapter() -> DataAdapter:
    global _adapter
    if _adapter is None:
        _adapter = DataAdapter()
    return _adapter
