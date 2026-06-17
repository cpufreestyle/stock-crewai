"""
交易员 Agent - 综合分析做出交易决策
工具: execute_buy, execute_sell, set_stop_loss, view_portfolio, wechat_notify
支持 HOLD: 如果市场不适合，可以决定等待
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from typing import Any, Dict, List

from core.agent_base import AgentBase, AgentOutput
from tools.trade_tools import get_trade_tools
from tools.notify_tools import get_notify_tools

logger = logging.getLogger("agents.trader")


class TraderAgent(AgentBase):
    """交易员 — 综合研究员和风控意见，做出最终交易决策"""

    name = "trader"
    role = "交易员"
    goal = "综合研究员和风控意见，做出最终买入/卖出/持有决策，给出具体交易计划"
    backstory = """你是经验丰富的A股交易员，擅长择时和执行。
    你理解市场情绪、技术形态、消息面对股价的影响。
    你只在高确定性机会出手，避免频繁交易。如果市场不适合，你会选择等待。"""

    def __init__(self):
        super().__init__()
        self.tools = get_trade_tools() + get_notify_tools()

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """执行交易决策"""
        market_state = state.get_market_state()
        stock_picks = state.get_stock_picks()
        risk_assessment = state.get_risk_assessment()

        if not risk_assessment:
            return AgentOutput(success=False, error="没有风控评估数据")

        passed_picks = risk_assessment.get("passed_picks", [])

        logger.info(f"[Trader] making decision for {len(passed_picks)} approved picks...")

        try:
            # 1. 检查是否应该交易
            should_trade = market_state.get("should_trade", True)
            regime = market_state.get("regime", "震荡市")
            position_pct = market_state.get("position_pct", 50)

            if not should_trade:
                logger.info(f"[Trader] HOLD: market condition not suitable ({regime})")
                return AgentOutput(
                    success=True,
                    data={
                        "action": "HOLD",
                        "reason": f"市场状态{regime}不适合交易，等待更好时机",
                        "trades": [],
                    },
                    hold=True,
                    events=[{
                        "type": "agent_hold",
                        "source": self.name,
                        "data": {"reason": f"市场{regime}不适合交易"},
                    }],
                )

            # 2. 查看当前持仓
            vp_result = self.call_tool("view_portfolio")
            vp_data = json.loads(vp_result) if isinstance(vp_result, str) else vp_result

            # 3. 生成交易计划
            trades = []
            trade_plan = {
                "market_regime": regime,
                "suggested_position": f"{position_pct}%",
                "buys": [],
                "sells": [],
                "holds": [],
            }

            # 3a. 处理风控通过的买入
            for pick in passed_picks:
                code = pick.get("code", "")
                name = pick.get("name", "")
                price = float(pick.get("price", 0))
                shares = int(pick.get("shares", 0))
                stop_loss = float(pick.get("stop_loss", 0))
                take_profit = float(pick.get("take_profit", 0))

                if shares <= 0 or price <= 0:
                    continue

                # 执行买入
                buy_result = self.call_tool(
                    "execute_buy",
                    code=code,
                    name=name,
                    price=price,
                    shares=shares,
                    reason=f"评分{pick.get('score', 0)} {pick.get('rationale', '')}",
                )
                buy_data = json.loads(buy_result) if isinstance(buy_result, str) else buy_result

                if isinstance(buy_data, dict) and buy_data.get("success"):
                    # 设置止损止盈
                    self.call_tool("set_stop_loss", code=code, stop_loss=stop_loss, take_profit=take_profit)

                    trades.append({
                        "action": "buy",
                        "code": code,
                        "name": name,
                        "price": price,
                        "shares": shares,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                    })
                    trade_plan["buys"].append({
                        "code": code, "name": name, "price": price,
                        "shares": shares, "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "rationale": pick.get("rationale", ""),
                    })

                    # 通知
                    msg = f"📈 买入 {name}({code}) {shares}股@{price:.2f}元 止损{stop_loss} 目标{take_profit}"
                    self.call_tool("wechat_notify", message=msg)
                    self.call_tool("dashboard_notify", title="买入信号", message=msg, level="success")
                else:
                    error = buy_data.get("error", "未知错误") if isinstance(buy_data, dict) else "执行失败"
                    logger.warning(f"[Trader] buy failed: {code} → {error}")

            # 写入共享状态
            state.set_trade_plan(trade_plan)

            logger.info(f"[Trader] done: {len(trades)} trades executed")

            return AgentOutput(
                success=True,
                data=trade_plan,
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"trades_count": len(trades)},
                }],
            )

        except Exception as e:
            logger.error(f"[Trader] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """Trader 一般不会被退回"""
        logger.warning(f"[Trader] rejected by {from_agent}: {reason}")
        return AgentOutput(
            success=False,
            rejection=reason,
            data={"retry": True, "feedback": reason, "from": from_agent},
        )
