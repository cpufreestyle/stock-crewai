"""
选股研究员 Agent - 从候选池筛选优质股票
工具: stock_search, technical_analysis, backtest, news_sentiment
支持被风控退回后重新选股
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from typing import Any, Dict, List

from core.agent_base import AgentBase, AgentOutput
from tools.stock_tools import get_stock_tools
from tools.market_tools import get_market_tools

logger = logging.getLogger("agents.researcher")


class ResearcherAgent(AgentBase):
    """选股研究员 — 从候选池筛选3-5只最值得买入的股票"""

    name = "researcher"
    role = "A股研究员"
    goal = "从沪深300成分股中，通过多因子筛选找出3-5只最有投资价值的股票"
    backstory = """你是资深A股研究员，擅长基本面+技术面结合选股。
    你关注：估值（PE/PB）、成长性（净利润增速）、趋势（均线多头排列）、市场情绪。
    你使用数据驱动的方法，从多个维度评估股票。"""

    def __init__(self):
        super().__init__()
        self.tools = get_stock_tools() + get_market_tools()

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """执行选股研究"""
        # 读取上游（MarketWatcher）的市场状态
        market_state = state.get_market_state()
        feedback = task.get("feedback", "")  # 如果是被退回重试，这里会有风控反馈

        logger.info(f"[Researcher] starting research... (feedback: {feedback or 'none'})")

        try:
            # 1. 获取板块信息（辅助筛选）
            sector_result = self.call_tool("sector_rotation", top_n=5)
            sector_data = json.loads(sector_result) if isinstance(sector_result, str) else sector_result

            # 2. 搜索候选股票
            search_result = self.call_tool("stock_search", n_stocks=15, min_change=0, max_change=6)
            search_data = json.loads(search_result) if isinstance(search_result, str) else search_result

            if isinstance(search_data, dict) and "error" in search_data:
                logger.error(f"[Researcher] stock_search failed: {search_data['error']}")
                return AgentOutput(success=False, error=search_data["error"])

            candidates = search_data if isinstance(search_data, list) else []

            # 3. 对前几只候选股做技术分析
            detailed_picks = []
            for stock in candidates[:8]:
                code = stock.get("代码", stock.get("code", ""))
                if not code:
                    continue

                ta_result = self.call_tool("technical_analysis", code=code)
                ta_data = json.loads(ta_result) if isinstance(ta_result, str) else ta_result

                if isinstance(ta_data, dict) and "error" not in ta_data:
                    # 综合评分
                    score = self._calculate_score(stock, ta_data, market_state)
                    detailed_picks.append({
                        "code": code,
                        "name": stock.get("名称", stock.get("name", code)),
                        "sector": stock.get("行业", stock.get("sector", "")),
                        "price": ta_data.get("current", ta_data.get("close", ta_data.get("收盘价", 0))),
                        "change_pct": stock.get("5日涨跌", stock.get("5日涨跌", "0%")),
                        "tech_indicators": ta_data,
                        "score": score,
                        "rationale": self._generate_rationale(stock, ta_data, market_state),
                    })

            # 4. 按评分排序，取前5
            detailed_picks.sort(key=lambda x: x["score"], reverse=True)
            top_picks = detailed_picks[:5]

            # 5. 如果有风控反馈，调整选股
            if feedback:
                top_picks = self._adjust_for_feedback(top_picks, feedback)

            if not top_picks:
                return AgentOutput(
                    success=False,
                    error="未找到符合条件的股票",
                    data={"picks": []},
                )

            # 6. 对 top picks 做回测
            for pick in top_picks:
                bt_result = self.call_tool("backtest", code=pick["code"])
                bt_data = json.loads(bt_result) if isinstance(bt_result, str) else bt_result
                pick["backtest"] = bt_data

            # 写入共享状态
            state.set_stock_picks(top_picks)

            logger.info(f"[Researcher] found {len(top_picks)} picks: {[p['name'] for p in top_picks]}")

            return AgentOutput(
                success=True,
                data={
                    "picks": top_picks,
                    "market_context": market_state.get("regime", "未知"),
                    "total_candidates": len(candidates),
                    "filtered": len(detailed_picks),
                },
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"picks_count": len(top_picks)},
                }],
            )

        except Exception as e:
            logger.error(f"[Researcher] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def _calculate_score(self, stock: Dict, ta: Dict, market: Dict) -> float:
        """综合评分（0-100）"""
        score = 50  # 基础分

        # 趋势得分
        trend = ta.get("趋势", "")
        if trend == "多头":
            score += 15
        elif trend == "空头":
            score -= 10

        # RSI
        rsi = ta.get("RSI", 50)
        if 30 <= rsi <= 50:
            score += 10  # 超卖区反弹
        elif rsi > 70:
            score -= 10  # 超买
        elif 50 <= rsi <= 65:
            score += 5

        # 市场环境加分
        regime = market.get("regime", "震荡市")
        if regime == "牛市":
            score += 5
        elif regime == "熊市":
            score -= 10

        # 板块轮动加分
        sector = stock.get("行业", stock.get("sector", ""))
        top_sectors = market.get("top_sectors", [])
        if isinstance(top_sectors, list):
            for ts in top_sectors:
                if isinstance(ts, dict) and ts.get("板块") == sector:
                    score += 10
                    break

        return max(0, min(100, score))

    def _generate_rationale(self, stock: Dict, ta: Dict, market: Dict) -> str:
        """生成入选理由"""
        reasons = []
        if ta.get("趋势") == "多头":
            reasons.append("均线多头排列")
        rsi = ta.get("RSI", 50)
        if rsi < 40:
            reasons.append(f"RSI={rsi}偏低有反弹空间")
        elif 50 <= rsi <= 65:
            reasons.append(f"RSI={rsi}健康区间")

        sector = stock.get("行业", stock.get("sector", ""))
        top_sectors = market.get("top_sectors", [])
        if isinstance(top_sectors, list):
            for ts in top_sectors:
                if isinstance(ts, dict) and ts.get("板块") == sector:
                    reasons.append(f"所属{sector}板块强势")
                    break

        return "；".join(reasons) if reasons else "技术面尚可"

    def _adjust_for_feedback(self, picks: List[Dict], feedback: str) -> List[Dict]:
        """根据风控反馈调整选股"""
        # 如果风控反馈说风险收益比不足，过滤低分股
        if "风险收益" in feedback or "风险" in feedback:
            picks = [p for p in picks if p["score"] >= 60]
        if "仓位" in feedback:
            picks = picks[:3]  # 减少数量
        return picks

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """被风控退回 — 调整选股策略后重试"""
        logger.warning(f"[Researcher] rejected by {from_agent}: {reason}")
        if self.reject_count >= self.max_rejects:
            return AgentOutput(
                success=False,
                error=f"被退回{self.reject_count}次，放弃选股",
                rejection=reason,
            )

        return AgentOutput(
            success=False,
            error="需要重新选股",
            rejection=reason,
            data={"retry": True, "feedback": f"风控退回原因: {reason}", "from": from_agent},
        )
