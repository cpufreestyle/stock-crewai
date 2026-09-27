"""
回测验证 Agent - 对研究员推荐的股票进行历史回测验证
在研究员选股后、风控审核前插入，提供回测数据作为风控参考
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from typing import Any, Dict, List
from datetime import datetime

from core.agent_base import AgentBase, AgentOutput
from tools.stock_tools import get_stock_tools
from backtest import multi_strategy_backtest

logger = logging.getLogger("agents.backtest")


class BacktestAgent(AgentBase):
    """回测验证师 — 对候选股票进行历史回测，验证策略有效性"""

    name = "backtest_validator"
    role = "回测验证师"
    goal = "对研究员推荐的股票进行多策略回测，验证其历史表现，为风控审核提供数据支持"
    backstory = """你是专业的量化回测工程师，擅长用历史数据验证交易策略的有效性。
    你理解过度拟合的风险，关注策略在不同市场环境下的表现。
    你提供客观的回测数据，帮助团队避免买入历史表现差的股票。"""

    def __init__(self):
        super().__init__()
        # 回测不需要太多工具，主要是 stock_search（获取历史数据）
        self.tools = [t for t in get_stock_tools() if "search" in t.name or "backtest" in t.name]

    def run(self, task: Dict, state: Any) -> AgentOutput:
        """执行回测验证"""
        stock_picks = state.get_stock_picks()  # 从 Researcher 获取候选股票

        if not stock_picks:
            return AgentOutput(
                success=False,
                error="没有候选股票可供回测",
                data={"backtest_results": []},
            )

        logger.info(f"[Backtest] validating {len(stock_picks)} stocks...")

        try:
            backtest_results = []
            validated_picks = []

            for pick in stock_picks[:5]:  # 只回测前5只
                code = pick.get("code", "")
                name = pick.get("name", "")

                if not code:
                    continue

                # 执行多策略回测
                bt = multi_strategy_backtest(code)
                
                if "error" in bt:
                    logger.warning(f"[Backtest] {code} backtest failed: {bt['error']}")
                    continue

                # 解析回测结果
                strategies = bt.get("strategies", {})
                best_strategy = bt.get("best_strategy", "N/A")
                best_return = bt.get("best_return", "N/A")

                # 计算综合评分（基于回测）
                backtest_score = self._calculate_backtest_score(bt)

                backtest_results.append({
                    "code": code,
                    "name": name,
                    "backtest": bt,
                    "backtest_score": backtest_score,
                    "best_strategy": best_strategy,
                    "best_return": best_return,
                })

                # 将回测评分加入 pick
                pick["backtest_score"] = backtest_score
                pick["backtest_summary"] = (
                    f"最佳策略: {best_strategy} ({best_return}) | "
                    f"回测评分: {backtest_score}/100"
                )
                validated_picks.append(pick)

                logger.info(f"[Backtest] {code} {name}: score={backtest_score}, best={best_strategy}")

            # 按回测评分排序
            validated_picks.sort(key=lambda x: x.get("backtest_score", 0), reverse=True)

            # 写入共享状态
            state.set_backtest_results(backtest_results)

            # 更新 stock_picks（加入回测数据）
            state.set_stock_picks(validated_picks)

            # 生成回测报告
            report = self._generate_backtest_report(backtest_results)

            logger.info(f"[Backtest] validation complete: {len(validated_picks)} stocks validated")

            return AgentOutput(
                success=True,
                data={
                    "backtest_results": backtest_results,
                    "validated_picks": validated_picks,
                    "report": report,
                },
                events=[{
                    "type": "agent_complete",
                    "source": self.name,
                    "data": {"validated": len(validated_picks)},
                }],
            )

        except Exception as e:
            logger.error(f"[Backtest] error: {e}")
            return AgentOutput(success=False, error=str(e))

    def _calculate_backtest_score(self, bt: Dict) -> float:
        """根据回测结果计算评分（0-100）"""
        score = 50  # 基础分

        strategies = bt.get("strategies", {})
        if not strategies:
            return 30  # 无回测数据，低分

        # 最佳策略收益
        best_return_str = bt.get("best_return", "0%")
        try:
            ret = float(best_return_str.replace("%", ""))
            if ret > 20:
                score += 20
            elif ret > 10:
                score += 15
            elif ret > 5:
                score += 10
            elif ret < -10:
                score -= 20
            elif ret < 0:
                score -= 10
        except Exception:
            pass

        # 胜率
        for name, data in strategies.items():
            win_rate = data.get("胜率", "0%")
            try:
                wr = float(win_rate.replace("%", ""))
                if wr > 60:
                    score += 10
                elif wr > 50:
                    score += 5
                elif wr < 40:
                    score -= 10
            except Exception:
                pass

        # 最大回撤（越小越好）
        for name, data in strategies.items():
            dd = data.get("最大回撤", "0%")
            try:
                drawdown = float(dd.replace("%", "").replace("-", ""))
                if drawdown < 10:
                    score += 10
                elif drawdown < 20:
                    score += 5
                elif drawdown > 30:
                    score -= 15
            except Exception:
                pass

        return max(0, min(100, score))

    def _generate_backtest_report(self, results: List[Dict]) -> str:
        """生成回测报告"""
        lines = ["# 回测验证报告", ""]
        
        for r in results:
            code = r["code"]
            name = r["name"]
            score = r["backtest_score"]
            best = r["best_strategy"]
            ret = r["best_return"]

            lines.append(f"## {name} ({code})")
            lines.append(f"- 回测评分: {score}/100")
            lines.append(f"- 最佳策略: {best} ({ret})")
            
            # 详细策略表现
            bt = r.get("backtest", {})
            strategies = bt.get("strategies", {})
            if strategies:
                lines.append("- 策略详情:")
                for sname, sdata in strategies.items():
                    lines.append(
                        f"  - {sname}: 收益={sdata.get('收益率', 'N/A')} "
                        f"回撤={sdata.get('最大回撤', 'N/A')} "
                        f"胜率={sdata.get('胜率', 'N/A')}"
                    )
            lines.append("")

        return "\n".join(lines)

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """回测验证一般不会被退回"""
        logger.warning(f"[Backtest] rejected by {from_agent}: {reason}")
        return AgentOutput(
            success=False,
            error="需要重新回测",
            rejection=reason,
            data={"retry": True, "feedback": reason, "from": from_agent},
        )
