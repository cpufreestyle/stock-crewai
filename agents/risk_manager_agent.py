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
from typing import Any, Dict, List, Optional, Tuple

from core.agent_base import AgentBase, AgentOutput
from tools.risk_tools import get_risk_tools
from tools.trade_tools import get_trade_tools

logger = logging.getLogger("agents.risk_manager")

# 目标风险收益比，低于该值的操作一律否决
TARGET_RISK_REWARD = 2
# 至少这么多只选股通过风控才继续，否则退回研究员
MIN_PASSED_PICKS = 2
# A 股最小买入单位（一手）
MIN_BUY_SHARES = 100


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
            cb_data, breaker_stopped = self._check_circuit_breaker()
            if breaker_stopped:
                return AgentOutput(
                    success=True,
                    data={"action": "STOP", "reason": "熔断器已触发，禁止交易"},
                    rejection="熔断器已触发",
                )

            # 2. 组合风险检查
            pr_data = self._portfolio_risk()

            # 3. 逐只评估
            assessed_picks, rejected_codes = self._assess_all_picks(stock_picks, market_state)

            # 4. 汇总并决策：是否需要退回研究员
            assessment = self._build_assessment(
                assessed_picks, rejected_codes, pr_data, cb_data, market_state
            )
            return self._decide(state, stock_picks, assessment)

        except Exception as e:
            logger.error(f"[RiskManager] error: {e}")
            return AgentOutput(success=False, error=str(e))

    # ── 组合层检查 ────────────────────────────────────────────

    @staticmethod
    def _decode(raw: Any) -> Any:
        """工具返回值统一解包为字典"""
        return json.loads(raw) if isinstance(raw, str) else raw

    def _check_circuit_breaker(self) -> Tuple[Dict, bool]:
        """熔断检查，返回 (熔断数据, 是否禁止交易)"""
        cb_data = self._decode(self.call_tool("circuit_breaker_check"))
        stopped = isinstance(cb_data, dict) and "否" in str(cb_data.get("是否允许交易", ""))
        return cb_data, stopped

    def _portfolio_risk(self) -> Any:
        """组合风险检查"""
        return self._decode(self.call_tool("portfolio_risk"))

    # ── 逐只评估 ──────────────────────────────────────────────

    def _assess_all_picks(self, stock_picks: List[Dict], market_state: Dict) -> Tuple[List[Dict], List[str]]:
        """逐只评估选股，返回 (全部评估结果, 否决原因列表)"""
        assessed_picks = []
        rejected_codes = []
        for pick in stock_picks:
            assessed, reject_reason = self._assess_pick(pick, market_state)
            if reject_reason:
                rejected_codes.append(reject_reason)
            if assessed is not None:
                assessed_picks.append(assessed)
        return assessed_picks, rejected_codes

    def _assess_pick(self, pick: Dict, market_state: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """评估单只选股，返回 (评估结果, 否决原因)；无有效价格时评估结果为 None"""
        code = pick.get("code", "")
        name = pick.get("name", "")
        price = float(pick.get("price", 0))

        if price <= 0:
            return None, f"{code} 无有效价格"

        stop_loss = self._stop_loss(price)
        take_profit = self._take_profit(price, stop_loss)
        risk_reward_ratio, is_valid = self._risk_reward(price, take_profit, stop_loss)
        shares = self._base_shares(price)
        adjusted_shares = self._adjust_for_regime(shares, market_state)
        passed, reject_reason = self._judge(name, risk_reward_ratio, is_valid, adjusted_shares)

        assessed = {
            "code": code,
            "name": name,
            "price": price,
            "stop_loss": round(stop_loss, 2),
            "take_profit": take_profit,
            "risk_reward_ratio": risk_reward_ratio,
            "shares": adjusted_shares,
            "position_value": round(adjusted_shares * price, 2),
            "passed": passed,
            "score": pick.get("score", 0),
            "rationale": pick.get("rationale", ""),
        }
        return assessed, reject_reason

    def _stop_loss(self, price: float) -> float:
        """3a. 计算止损价，工具异常时回落到 -8%"""
        sl_data = self._decode(
            self.call_tool("stop_loss_advice", entry_price=price, strategy="moderate")
        )
        return sl_data.get("止损价", price * 0.92) if isinstance(sl_data, dict) else price * 0.92

    def _take_profit(self, price: float, stop_loss: float) -> float:
        """3b. 按目标风险收益比换算止盈价"""
        # 止损空间
        risk_per_share = price - stop_loss
        # 目标止盈（2:1风险收益比）
        target_profit = risk_per_share * TARGET_RISK_REWARD
        return round(price + target_profit, 2)

    def _risk_reward(self, price: float, take_profit: float, stop_loss: float) -> Tuple[str, str]:
        """3c. 计算风险收益比，返回 (比值, 是否可行)"""
        rr_data = self._decode(
            self.call_tool("risk_reward", entry=price, target=take_profit, stop=stop_loss)
        )
        if not isinstance(rr_data, dict):
            return "0:1", "❌"
        return rr_data.get("风险收益比", "0:1"), rr_data.get("是否可行", "❌")

    def _base_shares(self, price: float) -> float:
        """3d. 按仓位管理工具计算基础买入股数"""
        ps_data = self._decode(
            self.call_tool("position_size", entry_price=price, stop_loss_pct=0.08)
        )
        return ps_data.get("买入股数", 0) if isinstance(ps_data, dict) else 0

    def _adjust_for_regime(self, shares: float, market_state: Dict) -> int:
        """3e. 按市场状态调整仓位，且不低于一手"""
        position_multiplier = self._market_multiplier(market_state.get("regime", "震荡市"))
        return max(MIN_BUY_SHARES, int(shares * position_multiplier))

    @staticmethod
    def _market_multiplier(regime: str) -> float:
        """市场状态对应的仓位系数：熊市减仓至40%，牛市可加仓20%"""
        if regime == "熊市":
            return 0.4
        if regime == "牛市":
            return 1.2
        return 1.0

    @staticmethod
    def _judge(name: str, risk_reward_ratio: str, is_valid: str, shares: int) -> Tuple[bool, Optional[str]]:
        """判断单只是否通过风控，返回 (是否通过, 否决原因)"""
        if "否" in str(is_valid):
            return False, f"{name} 风险收益比{risk_reward_ratio}不足2:1"
        if shares < MIN_BUY_SHARES:
            return False, f"{name} 计算仓位不足100股"
        return True, None

    # ── 汇总与决策 ────────────────────────────────────────────

    def _build_assessment(self, assessed_picks: List[Dict], rejected_codes: List[str],
                         pr_data: Any, cb_data: Any, market_state: Dict) -> Dict:
        """汇总逐只评估结果并写入共享状态，返回风控结论"""
        passed_picks = [p for p in assessed_picks if p["passed"]]
        failed_picks = [p for p in assessed_picks if not p["passed"]]

        should_reject = len(passed_picks) < MIN_PASSED_PICKS  # 至少2只通过才继续
        rejection_reason = ""

        if should_reject and rejected_codes:
            rejection_reason = f"风控未通过: {'; '.join(rejected_codes[:3])}"

        assessment = {
            "passed_picks": passed_picks,
            "failed_picks": failed_picks,
            "portfolio_risk": pr_data,
            "circuit_breaker": cb_data,
            "rejection": rejection_reason,
            "market_regime": market_state.get("regime", "未知"),
        }
        return assessment

    def _decide(self, state: Any, stock_picks: List[Dict], assessment: Dict) -> AgentOutput:
        """把风控结论写入共享状态，通过则放行、不通过则退回研究员"""
        state.set_risk_assessment(assessment)

        should_reject = len(assessment["passed_picks"]) < MIN_PASSED_PICKS
        passed_picks = assessment["passed_picks"]
        failed_picks = assessment["failed_picks"]
        rejection_reason = assessment["rejection"]

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
