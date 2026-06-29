"""
情绪分析工具 - 基于新闻和社交媒体情绪评分
"""
import logging
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger("tools.sentiment")


def get_sentiment_tools() -> list:
    """返回 CrewAI Tool 列表"""
    from crewai.tools import tool as crewai_tool

    @crewai_tool("新闻情绪分析")
    def news_sentiment(stock_code: str = "", days: int = 3) -> str:
        """分析指定股票近期新闻情绪（正面/负面/中性），如未指定股票则分析市场整体情绪"""
        return _news_sentiment_tool(stock_code, days)

    @crewai_tool("社交媒体情绪")
    def social_sentiment(stock_code: str = "") -> str:
        """分析股票在社交媒体的讨论热度和情绪倾向"""
        return _social_sentiment_tool(stock_code)

    @crewai_tool("情绪评分")
    def sentiment_score(stock_code: str) -> str:
        """综合新闻+社交媒体，给出情绪评分（0-100，50为中性）"""
        return _stock_sentiment_score_tool(stock_code)

    return [news_sentiment, social_sentiment, sentiment_score]


# ── 内部实现 ────────────────────────────────────────────────────────

def _news_sentiment_tool(stock_code: str = "", days: int = 3) -> str:
    """新闻情绪分析实现"""
    try:
        from data_fetcher import get_news_sentiment
        news = get_news_sentiment(days=days)
        
        if not news:
            return "未获取到新闻数据"
        
        # 过滤特定股票的新闻
        if stock_code:
            filtered = [n for n in news if stock_code in str(n) or _match_stock(n, stock_code)]
            news = filtered if filtered else news[:5]
        
        # 简单情绪判断（基于关键词）
        positive_words = ["涨", "利好", "突破", "买入", "看好", "增长", "盈利", "超预期"]
        negative_words = ["跌", "利空", "破位", "卖出", "看空", "下滑", "亏损", "不及预期"]
        
        pos_count = neg_count = neu_count = 0
        for item in news[:10]:
            text = str(item.get("新闻标题", item.get("title", "")) + str(item.get("内容", "")))
            p = sum(w in text for w in positive_words)
            n = sum(w in text for w in negative_words)
            if p > n:
                pos_count += 1
            elif n > p:
                neg_count += 1
            else:
                neu_count += 1
        
        total = pos_count + neg_count + neu_count
        if total == 0:
            return "情绪：中性（无足够数据）"
        
        sentiment = "正面" if pos_count > neg_count else ("负面" if neg_count > pos_count else "中性")
        score = int((pos_count - neg_count) / total * 50 + 50)
        
        return (
            f"情绪分析（{stock_code or '市场整体'}）:\n"
            f"  正面: {pos_count}条 | 负面: {neg_count}条 | 中性: {neu_count}条\n"
            f"  综合情绪: {sentiment} | 情绪评分: {max(0, min(100, score))}/100"
        )
    except Exception as e:
        logger.error(f"新闻情绪分析失败: {e}")
        return f"情绪分析失败: {e}"


def _social_sentiment_tool(stock_code: str = "") -> str:
    """社交媒体情绪（简化版，基于可获取的数据源）"""
    # A股没有像Twitter这样的开放API，这里用可替代的数据源
    try:
        # 尝试从东方财富股吧获取讨论热度（简化版）
        if not stock_code:
            return "请指定股票代码以分析社交媒体情绪"
        
        # 简化实现：返回提示信息
        # 实际可接入：东方财富股吧爬虫、雪球热帖API等
        return (
            f"股票 {stock_code} 社交媒体情绪分析:\n"
            f"  (提示: 完整版需接入东方财富股吧或雪球API)\n"
            f"  当前使用新闻情绪作为替代指标\n"
            f"{_news_sentiment_tool(stock_code, days=2)}"
        )
    except Exception as e:
        return f"社交媒体情绪分析失败: {e}"


def _stock_sentiment_score_tool(stock_code: str) -> str:
    """综合情绪评分"""
    if not stock_code:
        return "请提供股票代码"
    
    news_result = _news_sentiment_tool(stock_code, days=3)
    
    # 解析评分
    try:
        score_line = [l for l in news_result.split("\n") if "评分" in l]
        score = 50
        if score_line:
            import re
            match = re.search(r"(\d+)/100", score_line[0])
            if match:
                score = int(match.group(1))
        
        # 给出交易建议
        if score >= 70:
            advice = "情绪极度乐观，注意反转风险"
        elif score >= 60:
            advice = "情绪偏乐观，可结合技术面买入"
        elif score <= 30:
            advice = "情绪极度悲观，可能是抄底机会"
        elif score <= 40:
            advice = "情绪偏悲观，可关注超跌反弹"
        else:
            advice = "情绪中性，观望为主"
        
        return f"{news_result}\n交易建议: {advice}"
    except Exception:
        return news_result


def _match_stock(news_item: dict, stock_code: str) -> bool:
    """检查新闻是否提及某股票"""
    text = str(news_item.get("新闻标题", "")) + str(news_item.get("title", ""))
    # 简单匹配：股票代码或名称
    return stock_code in text
