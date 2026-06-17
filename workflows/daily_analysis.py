"""
每日分析工作流 - 替代原 crew.py:run_daily_analysis()
编排: MarketWatcher → Researcher → RiskManager → Trader
支持: REJECT 反馈循环（风控退回研究员重选）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from datetime import datetime

from core.orchestrator import Orchestrator, Workflow, WorkflowStep
from core.event_bus import EventType
from agents.market_watcher import MarketWatcherAgent
from agents.researcher import ResearcherAgent
from agents.risk_manager_agent import RiskManagerAgent
from agents.trader import TraderAgent

logger = logging.getLogger("workflows.daily_analysis")


def create_daily_analysis_workflow() -> Workflow:
    """创建每日分析工作流定义"""
    return Workflow(
        name="daily_analysis",
        description="每日A股分析：市场判断 → 选股 → 风控 → 交易",
        trigger_event=EventType.DAILY_TRIGGER,
        steps=[
            WorkflowStep(
                agent="market_watcher",
                on_reject="skip",      # 市场判断不会退回
                max_retries=1,
            ),
            WorkflowStep(
                agent="researcher",
                input_from="market_watcher",
                on_reject="retry",     # 被风控退回后重试
                max_retries=3,
            ),
            WorkflowStep(
                agent="risk_manager",
                input_from="researcher",
                on_reject="retry",     # Trader 退回后重试
                max_retries=2,
            ),
            WorkflowStep(
                agent="trader",
                input_from="risk_manager",
                on_reject="abort",     # Trader 不退回，不行就放弃
                max_retries=1,
            ),
        ],
    )


def create_orchestrator_with_agents() -> Orchestrator:
    """创建配置好 Agent 和工作流的编排器"""
    orch = Orchestrator()

    # 注册 Agent
    orch.register_agent(MarketWatcherAgent())
    orch.register_agent(ResearcherAgent())
    orch.register_agent(RiskManagerAgent())
    orch.register_agent(TraderAgent())

    # 注册工作流
    orch.register_workflow(create_daily_analysis_workflow())

    return orch


def run_daily_analysis() -> dict:
    """运行每日分析（替代原 crew.py:run_daily_analysis）"""
    logger.info(f"{'='*60}")
    logger.info(f"  A股多智能体协作系统 v5.0 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"{'='*60}")

    orch = create_orchestrator_with_agents()
    result = orch.execute_workflow("daily_analysis")

    logger.info(f"{'='*60}")
    logger.info(f"  分析完成")
    logger.info(f"{'='*60}")

    return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = run_daily_analysis()
    print(f"\n工作流结果: {result['workflow']}")
    for r in result["results"]:
        print(f"  step {r['step']}: {r['agent']} → success={r['success']}")
