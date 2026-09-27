"""
动态调仓 Agent - 根据市场变化和持仓表现，动态调整仓位
在交易执行后、每日收盘前运行，也可盘中触发
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from typing import Any, Dict, List
from datetime import datetime

from core.agent_base import AgentBase, AgentOutput
from tools.trade_tools import get_trade_tools
from tools.risk_tools import get_risk_tools
from tools.notify_tools import get_notify_tools

logger = logging.getLogger("agents.rebalancer")


class PortfolioRebalancerAgent(AgentBase):
    """动态调仓师 — 根据市场变化和持仓表现，动态调整仓位"""

    name = "portfolio_rebalancer"
    role = "动态调仓师"
    goal = "根据市场状态变化、持仓盈亏、风险敞口，动态调整仓位，优化收益风险比"
    backstory = """你是专业的仓位管理专家，擅长根据市场变化动态调整持仓结构。
    你理解"截断亏损，让利润奔跑"的交易哲学。
    你关注：持仓盈亏、市场趋势变化、板块轮动、风险敞口。"""

    def __init__(self):
        super().__init__()
        self.tools = get_trade_tools() + get_risk_tools() + get_notify_tools()

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """执行动态调仓分析"""
        market_state = state.get_market_state()
        trade_plan = state.get_trade_plan()  # 从 Trader 获取交易计划

        logger.info(f"[Rebalancer] analyzing portfolio for rebalancing...")

        try:
            # 1. 查看当前持仓
            vp_result = self.call_tool("view_portfolio")
            portfolio = json.loads(vp_result) if isinstance(vp_result, str) else vp_result

            if not portfolio or not portfolio.get("holdings"):
                return AgentOutput(
                    success=True,
                    data={"action": "NO_ACTION", "reason": "无持仓，无需调仓"},
                    events=[{"type": "agent_complete", "source": self.name, "data": {"action": "none"}}],
                )

            holdings = portfolio.get("holdings", [])

            # 2. 分析每只持仓
            rebalance_actions = []
            
            for h in holdings:
                code = h.get("代码", h.get("code", ""))
                name = h.get("名称", h.get("name", ""))
                cost = float(h.get("成本价", h.get("cost", 0)))
                current = float(h.get("当前价", h.get("current_price", 0)))
                shares = int(h.get("持仓数量", h.get("shares", 0)))
                profit_pct = (current - cost) / cost * 100 if cost > 0 else 0

                # 决策逻辑
                action = self._decide_rebalance_action(h, market_state, profit_pct)

                if action["action"] != "HOLD":
                    rebalance_actions.append({
                        "code": code,
                        "name": name,
                        "current_profit_pct": profit_pct,
                        "action": action["action"],
                        "reason": action["reason"],
                        "suggested_shares": action.get("shares", 0),
                    })

            # 3. 生成调仓计划
            if not rebalance_actions:
                report = "动态调仓分析：当前持仓无需调整"
                actions_taken = []
            else:
                report = self._generate_rebalance_report(rebalance_actions)
                
                # 执行调仓（谨慎执行，只执行明确的止损/止盈）
                actions_taken = []
                for action in rebalance_actions:
                    if action["action"] == "SELL_STOP_LOSS" and action["current_profit_pct"] < -8:
                        # 执行止损
                        sell_result = self.call_tool(
                            "execute_sell",
                            code=action["code"],
                            name=action["name"],
                            price=0,  # 市价
                            shares=action["suggested_shares"] or holdings[0].get("持仓数量", 0),
                            reason=action["reason"],
                        )
                        sell_data = json.loads(sell_result) if isinstance(sell_result, str) else sell_result
                        if isinstance(sell_data, dict) and sell_data.get("success"):
                            actions_taken.append({"action": "STOP_LOSS", "code": action["code"]})
                            msg = f"🔴 止损卖出 {action['name']}({action['code']}) 亏损{action['current_profit_pct']:.1f}%"
                            self.call_tool("wechat_notify", message=msg)
                            
                    elif action["action"] == "TAKE_PROFIT" and action["current_profit_pct"] > 20:
                        # 部分止盈（卖出一半）
                        sell_shares = int(action["suggested_shares"] or holdings[0].get("持仓数量", 0) / 2)
                        if sell_shares > 0:
                            sell_result = self.call_tool(
                                "execute_sell",
                                code=action["code"],
                                name=action["name"],
                                price=0,
                                shares=sell_shares,
                                reason="分批止盈",
                            )
                            sell_data = json.loads(sell_result) if isinstance(sell_result, str) else sell_result
                            if isinstance(sell_data, dict) and sell_data.get("success"):
                                actions_taken.append({"action": "TAKE_PROFIT", "code": action["code"], "shares": sell_shares})
                                msg = f"🟢 分批止盈 {action['name']}({action['code']}) 卖出{sell_shares}股 盈利{action['current_profit_pct']:.1f}%"
                                self.call_tool("wechat_notify", message=msg)

            # 写入共享状态
            state.set_rebalance_plan({
                "actions": rebalance_actions,
                "executed": actions_taken,
                "report": report,
            })

            logger.info(f"[Rebalancer] complete: {len(actions_taken)} actions executed")

            return AgentOutput(
                success=True,
                data={
                    "rebalance_actions": rebalance_actions,
                    "actions_executed": actions_taken,
                    "report": report,
                },
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"actions_count": len(actions_taken)},
                }],
            )

        except Exception as e:
            logger.error(f"[Rebalancer] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def _decide_rebalance_action(self, holding: Dict, market: Dict, profit_pct: float) -> Dict:
        """决策是否需要调仓"""
        code = holding.get("代码", "")
        regime = market.get("regime", "震荡市") if market else "震荡市"
        
        # 止损
        if profit_pct < -8:
            return {"action": "SELL_STOP_LOSS", "reason": f"亏损{profit_pct:.1f}%，触发止损", "shares": 0}
        
        # 止盈
        if profit_pct > 30:
            return {"action": "TAKE_PROFIT", "reason": f"盈利{profit_pct:.1f}%，建议分批止盈", "shares": 0}
        
        # 熊市减仓
        if regime == "熊市" and profit_pct > 5:
            return {"action": "REDUCE", "reason": "熊市趋势，建议减仓保住利润", "shares": int(holding.get("持仓数量", 0) * 0.5)}
        
        # 牛市可以持有
        if regime == "牛市" and profit_pct > 0:
            return {"action": "HOLD", "reason": "牛市趋势，继续持有"}
        
        # 默认持有
        return {"action": "HOLD", "reason": "无需调整"}

    def _generate_rebalance_report(self, actions: List[Dict]) -> str:
        """生成调仓报告"""
        lines = ["# 动态调仓报告", ""]
        
        for a in actions:
            lines.append(f"## {a['name']} ({a['code']})")
            lines.append(f"- 当前盈亏: {a['current_profit_pct']:.1f}%")
            lines.append(f"- 建议操作: {a['action']}")
            lines.append(f"- 原因: {a['reason']}")
            if a.get("suggested_shares", 0) > 0:
                lines.append(f"- 建议数量: {a['suggested_shares']}股")
            lines.append("")
        
        return "\n".join(lines)

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """调仓建议一般不会被退回"""
        logger.warning(f"[Rebalancer] rejected by {from_agent}: {reason}")
        return AgentOutput(
            success=False,
            error="需要重新分析",
            rejection=reason,
            data={"retry": True, "feedback": reason, "from": from_agent},
        )
