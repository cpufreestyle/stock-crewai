"""
风控专家 Agent - 对选股进行独立风险评估
工具: kelly_position, position_size, risk_reward, portfolio_risk, circuit_breaker_check, stop_loss_advice
支持 REJECT: 如果风险收益比不足，可以退回研究员重新选股
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from typing import Any, Dict, List

from core.agent_base import AgentBase, AgentOutput
from tools.risk_tools import get_risk_tools
from tools.trade_tools import get_trade_tools

logger = logging.getLogger("agents.risk_manager")


class RiskManagerAgent(AgentBase):
    """风控专家 — 对选股进行独立风险评估，可退回研究员"""

    name = "risk_manager"
    role = "风控专家"
    goal = "对研究员的选股进行独立风险评估，确定仓位、止损止盈，风险收益比不足时退回研究员"
    backstory = """你是资深风控专家，曾在公募基金负责风险管理工作。
    你擅长：VaR分析、仓位管理、止损策略、相关性风险控制。
    你的原则是：保住本金 > 追求收益。风险收益比低于2:1的操作一律否决。"""

    def __init__(self):
        super().__init__()
        self.tools = get_risk_tools() + get_trade_tools()

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """执行风险评估"""
        # 读取上游数据
        market_state = state.get_market_state()
        stock_picks = state.get_stock_picks()

        if not stock_picks:
            return AgentOutput(success=False, error="没有选股数据，无法评估风险")

        logger.info(f"[RiskManager] assessing {len(stock_picks)} picks...")

        try:
            # 1. 熔断检查
            cb_result = self.call_tool("circuit_breaker_check")
            cb_data = json.loads(cb_result) if isinstance(cb_result, str) else cb_result

            if isinstance(cb_data, dict) and "否" in str(cb_data.get("是否允许交易", "")):
                return AgentOutput(
                    success=True,
                    data={"action": "STOP", "reason": "熔断器已触发，禁止交易"},
                    rejection="熔断器已触发",
                )

            # 2. 组合风险检查
            pr_result = self.call_tool("portfolio_risk")
            pr_data = json.loads(pr_result) if isinstance(pr_result, str) else pr_result

            # 3. 逐只评估
            assessed_picks = []
            rejected_codes = []
            for pick in stock_picks:
                code = pick.get("code", "")
                name = pick.get("name", "")
                price = float(pick.get("price", 0))

                if price <= 0:
                    rejected_codes.append(f"{code} 无有效价格")
                    continue

                # 3a. 计算止损价
                sl_result = self.call_tool("stop_loss_advice", entry_price=price, strategy="moderate")
                sl_data = json.loads(sl_result) if isinstance(sl_result, str) else sl_result

                stop_loss = sl_data.get("止损价", price * 0.92) if isinstance(sl_data, dict) else price * 0.92

                # 3b. 计算止盈价（风险收益比 ≥ 2:1）
                # 止损空间
                risk_per_share = price - stop_loss
                # 目标止盈（2:1风险收益比）
                target_profit = risk_per_share * 2
                take_profit = round(price + target_profit, 2)

                # 3c. 计算风险收益比
                rr_result = self.call_tool("risk_reward", entry=price, target=take_profit, stop=stop_loss)
                rr_data = json.loads(rr_result) if isinstance(rr_result, str) else rr_result

                risk_reward_ratio = rr_data.get("风险收益比", "0:1") if isinstance(rr_data, dict) else "0:1"
                is_valid = rr_data.get("是否可行", "❌") if isinstance(rr_data, dict) else "❌"

                # 3d. 计算仓位
                ps_result = self.call_tool("position_size", entry_price=price, stop_loss_pct=0.08)
                ps_data = json.loads(ps_result) if isinstance(ps_result, str) else ps_result

                shares = ps_data.get("买入股数", 0) if isinstance(ps_data, dict) else 0

                # 3e. 市场状态调整仓位
                regime = market_state.get("regime", "震荡市")
                position_multiplier = 1.0
                if regime == "熊市":
                    position_multiplier = 0.4  # 熊市减仓至40%
                elif regime == "牛市":
                    position_multiplier = 1.2  # 牛市可加仓20%

                adjusted_shares = max(100, int(shares * position_multiplier))

                # 判断是否通过
                passed = True
                reject_reason = ""

                if "否" in str(is_valid):
                    passed = False
                    reject_reason = f"{name} 风险收益比{risk_reward_ratio}不足2:1"

                if adjusted_shares < 100:
                    passed = False
                    reject_reason = f"{name} 计算仓位不足100股"

                assessed = {
                    "code": code,
                    "name": name,
                    "price": price,
                    "stop_loss": round(stop_loss, 2),
                    "take_profit": round(take_profit, 2),
                    "risk_reward_ratio": risk_reward_ratio,
                    "shares": adjusted_shares,
                    "position_value": round(adjusted_shares * price, 2),
                    "passed": passed,
                    "score": pick.get("score", 0),
                    "rationale": pick.get("rationale", ""),
                }

                if not passed:
                    rejected_codes.append(reject_reason)

                assessed_picks.append(assessed)

            # 4. 决策：是否需要退回研究员
            passed_picks = [p for p in assessed_picks if p["passed"]]
            failed_picks = [p for p in assessed_picks if not p["passed"]]

            should_reject = len(passed_picks) < 2  # 至少2只通过才继续
            rejection_reason = ""

            if should_reject and rejected_codes:
                rejection_reason = f"风控未通过: {'; '.join(rejected_codes[:3])}"

            # 写入共享状态
            assessment = {
                "passed_picks": passed_picks,
                "failed_picks": failed_picks,
                "portfolio_risk": pr_data,
                "circuit_breaker": cb_data,
                "rejection": rejection_reason,
                "market_regime": market_state.get("regime", "未知"),
            }
            state.set_risk_assessment(assessment)

            if should_reject:
                logger.warning(f"[RiskManager] REJECT: {rejection_reason}")
                return AgentOutput(
                    success=False,
                    rejection=rejection_reason,
                    data=assessment,
                    events=[{
                        "type": "agent_reject",
                        "source": self.name,
                        "target": "researcher",
                        "reason": rejection_reason,
                    }],
                )

            logger.info(f"[RiskManager] approved {len(passed_picks)}/{len(stock_picks)} picks")

            return AgentOutput(
                success=True,
                data=assessment,
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"approved": len(passed_picks), "rejected": len(failed_picks)},
                }],
            )

        except Exception as e:
            logger.error(f"[RiskManager] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """风控一般不会被退回，但 Trader 可以退回"""
        logger.warning(f"[RiskManager] rejected by {from_agent}: {reason}")
        if self.reject_count >= self.max_rejects:
            return AgentOutput(success=False, error=f"被退回{self.reject_count}次", rejection=reason)

        return AgentOutput(
            success=False,
            rejection=reason,
            data={"retry": True, "feedback": reason, "from": from_agent},
        )
