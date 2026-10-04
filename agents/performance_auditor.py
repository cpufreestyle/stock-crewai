"""
绩效审计员 Agent - 独立评估交易绩效
工具: view_portfolio（读取数据），自行计算指标
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from pathlib import Path
from typing import Any, Dict

from core.agent_base import AgentBase, AgentOutput
from tools.trade_tools import get_trade_tools

logger = logging.getLogger("agents.performance_auditor")


class PerformanceAuditorAgent(AgentBase):
    """绩效审计员 — 独立评估交易绩效，生成日报"""

    name = "performance_auditor"
    role = "绩效审计员"
    goal = "独立评估交易系统绩效（夏普比率、最大回撤、胜率等），生成每日绩效报告"
    backstory = """你是量化交易的绩效审计员，专门评估交易系统的表现。
    你用数据说话，关注：夏普比率、最大回撤、胜率、盈亏比。
    你会指出系统的弱点和改进方向。"""

    def __init__(self):
        super().__init__()
        self.tools = get_trade_tools()

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """计算绩效指标"""
        logger.info(f"[PerformanceAuditor] computing metrics...")

        try:
            # 1. 读取当前持仓
            vp_result = self.call_tool("view_portfolio")
            vp_data = json.loads(vp_result) if isinstance(vp_result, str) else vp_result

            portfolio = vp_data.get("raw", {}) if isinstance(vp_data, dict) else {}
            summary = vp_data.get("summary", "") if isinstance(vp_data, dict) else ""

            # 2. 从净值历史计算绩效指标
            metrics = self._calculate_metrics()

            # 3. 生成报告
            report = {
                "portfolio": {
                    "total_value": portfolio.get("total_value", 0),
                    "cash": portfolio.get("cash", 0),
                    "positions_count": len(portfolio.get("positions", {})),
                    "total_return_pct": portfolio.get("total_return_pct", 0),
                },
                "metrics": metrics,
                "summary_text": summary,
            }

            # 写入共享状态
            state.set_performance_report(report)

            logger.info(f"[PerformanceAuditor] done: sharpe={metrics.get('sharpe_ratio', 'N/A')}")

            return AgentOutput(
                success=True,
                data=report,
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"sharpe": metrics.get("sharpe_ratio", "N/A")},
                }],
            )

        except Exception as e:
            logger.error(f"[PerformanceAuditor] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def _calculate_metrics(self) -> Dict:
        """从净值历史文件计算绩效指标"""
        nv_file = Path(__file__).parent.parent / "net_value_history.json"

        if not nv_file.exists():
            return {"note": "净值历史数据不足"}

        try:
            with open(nv_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            if len(history) < 10:
                return {"note": f"数据不足（仅{len(history)}条）"}

            values = [h.get("total_value", 0) for h in history if h.get("total_value", 0) > 0]

            if len(values) < 10:
                return {"note": "有效数据不足"}

            # 指标计算统一走 performance_metrics（与 run_virtual_v4 / backtest 共用一份实现）
            from performance_metrics import compute_metrics
            m = compute_metrics(values)
            if m is None:
                return {"note": "无法计算收益率"}

            return {
                "sharpe_ratio": m["sharpe_ratio"],
                "max_drawdown": m["max_drawdown"],
                "annual_return": m["annual_return"],
                "annual_volatility": m["annual_volatility"],
                "win_rate": m["win_rate"],
                "data_points": m["total_days"],
            }

        except Exception as e:
            return {"error": str(e)}

