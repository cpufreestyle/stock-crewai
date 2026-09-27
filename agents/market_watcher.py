"""
市场观察员 Agent - 评估市场整体状态
工具: market_heat, market_regime, sector_rotation, realtime_quotes
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from typing import Any, Dict

from core.agent_base import AgentBase, AgentOutput
from tools.market_tools import get_market_tools

logger = logging.getLogger("agents.market_watcher")


class MarketWatcherAgent(AgentBase):
    """市场观察员 — 评估市场整体热度、牛熊状态、板块轮动"""

    name = "market_watcher"
    role = "市场观察员"
    goal = "评估当前A股市场整体热度、牛熊状态、热门板块，判断是否适合开仓"
    backstory = """你专注于A股整体市场情绪分析，
    通过换手率、北向资金、涨跌家数等指标判断市场状态。
    熊市轻仓或空仓，牛市积极布局。你的判断直接影响后续所有Agent的操作方向。"""

    def __init__(self):
        super().__init__()
        self.tools = get_market_tools()

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """执行市场分析"""
        logger.info(f"[MarketWatcher] starting analysis...")

        try:
            # 1. 获取市场热度
            heat_result = self.call_tool("market_heat")
            heat_data = json.loads(heat_result) if isinstance(heat_result, str) else heat_result

            # 2. 获取市场趋势
            regime_result = self.call_tool("market_regime")
            regime_data = json.loads(regime_result) if isinstance(regime_result, str) else regime_result

            # 3. 获取板块轮动
            sector_result = self.call_tool("sector_rotation", top_n=5)
            sector_data = json.loads(sector_result) if isinstance(sector_result, str) else sector_result

            # 4. 综合判断
            regime = regime_data.get("regime", "未知")
            confidence = regime_data.get("confidence", 0)

            # 根据市场状态建议仓位
            if regime == "牛市":
                suggested_position = "重仓（7-8成）"
                position_pct = 80
                should_trade = True
            elif regime == "熊市":
                suggested_position = "轻仓（2-3成）或空仓"
                position_pct = 30
                should_trade = confidence > 60
            else:
                suggested_position = "半仓（4-5成）"
                position_pct = 50
                should_trade = True

            # 构建市场状态
            market_state = {
                "regime": regime,
                "confidence": confidence,
                "signals": regime_data.get("signals", []),
                "heat": heat_data,
                "top_sectors": sector_data if isinstance(sector_data, list) else [],
                "suggested_position": suggested_position,
                "position_pct": position_pct,
                "should_trade": should_trade,
                "summary": f"市场状态: {regime}(置信度{confidence}%), 建议仓位: {suggested_position}",
            }

            # 写入共享状态
            state.set_market_state(market_state)

            logger.info(f"[MarketWatcher] done: {regime} (conf={confidence}%) → {suggested_position}")

            return AgentOutput(
                success=True,
                data=market_state,
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"regime": regime, "confidence": confidence},
                }],
            )

        except Exception as e:
            logger.error(f"[MarketWatcher] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """市场观察员一般不会被退回，但如果被退回，重新分析"""
        logger.warning(f"[MarketWatcher] rejected by {from_agent}: {reason}")
        return AgentOutput(
            success=False,
            error="需要重新分析",
            rejection=reason,
            data={"retry": True, "feedback": reason, "from": from_agent},
        )
