"""
情绪分析 Agent - 分析市场情绪和新闻情绪，为选股提供情绪维度参考
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from typing import Any, Dict, List

from core.agent_base import AgentBase, AgentOutput
from tools.sentiment_tools import get_sentiment_tools

logger = logging.getLogger("agents.sentiment")


class SentimentAgent(AgentBase):
    """情绪分析师 — 分析市场和个股情绪，给出情绪评分和交易建议"""

    name = "sentiment_analyst"
    role = "情绪分析师"
    goal = "分析市场整体情绪和候选股票的情绪倾向，识别情绪极值带来的交易机会"
    backstory = """你是专业的情绪分析师，擅长从新闻、舆论和市场行为中识别情绪极值。
    你理解"别人贪婪时恐惧，别人恐惧时贪婪"的反向操作逻辑。
    你关注：新闻情绪、社交媒体热度、市场恐慌/贪婪指数。"""

    def __init__(self):
        super().__init__()
        self.tools = get_sentiment_tools()

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """执行情绪分析"""
        stock_picks = state.get_stock_picks()  # 从 Researcher 获取候选股票
        market_state = state.get_market_state()

        logger.info(f"[Sentiment] analyzing sentiment for {len(stock_picks) if stock_picks else 0} stocks...")

        try:
            sentiment_results = []

            # 1. 市场整体情绪
            market_sentiment = self.call_tool("news_sentiment", stock_code="", days=3)
            sentiment_results.append({
                "type": "market",
                "result": market_sentiment,
            })

            # 2. 逐个分析候选股票的情绪
            if stock_picks:
                for pick in stock_picks[:5]:  # 只分析前5只
                    code = pick.get("code", "")
                    name = pick.get("name", "")
                    
                    if not code:
                        continue

                    score_result = self.call_tool("sentiment_score", stock_code=code)
                    sentiment_results.append({
                        "type": "stock",
                        "code": code,
                        "name": name,
                        "result": score_result,
                    })

                    # 将情绪评分加入 pick
                    try:
                        import re
                        match = re.search(r"(\d+)/100", score_result)
                        if match:
                            pick["sentiment_score"] = int(match.group(1))
                    except Exception:
                        pick["sentiment_score"] = 50  # 默认中性

            # 3. 生成情绪报告
            report = self._generate_sentiment_report(sentiment_results, market_state)

            # 写入共享状态
            state.set_sentiment_analysis({
                "market_sentiment": market_sentiment,
                "stock_sentiment": [
                    {"code": r["code"], "name": r["name"], "result": r["result"]}
                    for r in sentiment_results if r["type"] == "stock"
                ],
                "report": report,
            })

            logger.info(f"[Sentiment] analysis complete: {len(sentiment_results)} items analyzed")

            return AgentOutput(
                success=True,
                data={
                    "sentiment_results": sentiment_results,
                    "report": report,
                    "market_mood": self._classify_market_mood(market_sentiment),
                },
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"analyzed": len(sentiment_results)},
                }],
            )

        except Exception as e:
            logger.error(f"[Sentiment] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def _generate_sentiment_report(self, results: List[Dict], market: Dict) -> str:
        """生成情绪分析报告"""
        lines = ["# 情绪分析报告", ""]
        
        for r in results:
            if r["type"] == "market":
                lines.append(f"## 市场整体情绪\n{r['result']}\n")
            else:
                lines.append(f"## {r['name']} ({r['code']})\n{r['result']}\n")
        
        # 交易建议
        regime = market.get("regime", "震荡市") if market else "震荡市"
        lines.append(f"## 综合建议")
        lines.append(f"- 当前市场趋势: {regime}")
        lines.append(f"- 情绪极值往往预示反转，建议结合技术面确认")
        lines.append(f"- 情绪评分 > 70 的股票的回调风险较高")
        lines.append(f"- 情绪评分 < 30 的股票可能存在超跌反弹机会")
        
        return "\n".join(lines)

    def _classify_market_mood(self, sentiment_str: str) -> str:
        """从情绪字符串中提取市场情绪分类"""
        if "正面" in sentiment_str or "乐观" in sentiment_str:
            return "optimistic"
        elif "负面" in sentiment_str or "悲观" in sentiment_str:
            return "pessimistic"
        else:
            return "neutral"

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """情绪分析一般不会被退回，但可以被要求重新分析"""
        logger.warning(f"[Sentiment] rejected by {from_agent}: {reason}")
        return AgentOutput(
            success=False,
            error="需要重新分析情绪",
            rejection=reason,
            data={"retry": True, "feedback": reason, "from": from_agent},
        )
