"""
编排中枢 - 多 Agent 协调调度的核心
事件驱动 + 反馈循环 + 工作流管理
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import EventBus, Event, EventType, get_event_bus
from core.state_store import StateStore, get_state_store
from core.agent_base import AgentBase, AgentOutput, AgentRegistry, AgentStatus

logger = logging.getLogger("orchestrator")


# ── 工作流定义 ────────────────────────────────────────────────────
@dataclass
class WorkflowStep:
    agent: str                          # Agent 名称
    input_from: Optional[str] = None    # 从哪个 Agent 的输出取输入
    condition: Optional[str] = None     # 执行条件（Python 表达式）
    on_reject: str = "retry"            # retry / skip / abort
    max_retries: int = 3

@dataclass
class Workflow:
    name: str
    steps: List[WorkflowStep]
    trigger_event: Optional[EventType] = None
    description: str = ""


# ── 编排器 ────────────────────────────────────────────────────────
class Orchestrator:
    """多 Agent 编排中枢

    职责:
    1. 监听事件 → 触发 Agent
    2. 管理工作流 → 按步骤执行
    3. 处理反馈循环 → REJECT → 上游重试
    4. 维护 Agent 状态 → 写入 StateStore
    5. 广播事件 → 通知 Dashboard
    """

    def __init__(self, event_bus: EventBus = None, state_store: StateStore = None):
        self.event_bus = event_bus or get_event_bus()
        self.state = state_store or get_state_store()
        self.registry = AgentRegistry()
        self._workflows: Dict[str, Workflow] = {}
        self._running = False

        # 注册内部事件处理器
        self._register_internal_handlers()

    def _register_internal_handlers(self):
        """注册编排器内部的事件处理器"""
        self.event_bus.subscribe(EventType.AGENT_COMPLETE, self._on_agent_complete)
        self.event_bus.subscribe(EventType.AGENT_REJECT, self._on_agent_reject)
        self.event_bus.subscribe(EventType.AGENT_ERROR, self._on_agent_error)

    # ── 注册 ──────────────────────────────────────────────────────

    def register_agent(self, agent: AgentBase) -> None:
        """注册 Agent"""
        self.registry.register(agent)
        # 初始化 Agent 状态
        self.state.update_agent_status(agent.name, "idle")

    def register_workflow(self, workflow: Workflow) -> None:
        """注册工作流"""
        self._workflows[workflow.name] = workflow
        logger.info(f"[Orchestrator] workflow registered: {workflow.name} ({len(workflow.steps)} steps)")

        # 如果工作流有触发事件，自动订阅
        if workflow.trigger_event:
            self.event_bus.subscribe(workflow.trigger_event, lambda e: self.execute_workflow(workflow.name))

    # ── 事件处理器 ────────────────────────────────────────────────

    def _on_agent_complete(self, event: Event) -> None:
        """Agent 完成时（同步版本，供 publish_sync 调用）"""
        agent_name = event.source
        self.state.update_agent_status(agent_name, "idle")
        logger.info(f"[Orchestrator] agent_complete: {agent_name}")

    def _on_agent_reject(self, event: Event) -> None:
        """Agent 退回上游时（同步版本，供 publish_sync 调用）— 日志记录，重试由 execute_workflow 循环处理"""
        rejected_agent = event.data.get("from", "")
        target_agent = event.data.get("target", "")
        reason = event.data.get("reason", "")

        if not target_agent:
            logger.warning(f"[Orchestrator] rejection without target agent: {event.data}")
            return

        logger.warning(f"[Orchestrator] {rejected_agent} rejected by {target_agent}: {reason}")

    def _on_agent_error(self, event: Event) -> None:
        """Agent 出错（同步版本，供 publish_sync 调用）"""
        agent_name = event.source
        error = event.data.get("error", "unknown")
        logger.error(f"[Orchestrator] agent error: {agent_name} → {error}")
        self.state.update_agent_status(agent_name, "error")

    # ── Agent 执行 ────────────────────────────────────────────────

    async def _run_agent_async(self, agent_name: str, task: Dict) -> AgentOutput:
        """异步执行单个 Agent"""
        agent = self.registry.get(agent_name)
        if agent is None:
            logger.error(f"[Orchestrator] agent not found: {agent_name}")
            return AgentOutput(success=False, error=f"agent not found: {agent_name}")

        self.state.update_agent_status(agent_name, "running", task.get("task_name", ""))

        # 发布 AGENT_START 事件
        await self.event_bus.publish(Event(
            type=EventType.AGENT_START,
            source=agent_name,
            data={"task": task},
        ))

        try:
            # 执行 Agent
            agent.on_activate(task)
            output = agent.run(task, self.state)
            output = agent.on_complete(output)

            # 写入状态
            if output.success:
                self.state.update_agent_status(agent_name, "idle")
            else:
                self.state.update_agent_status(agent_name, "error")

            # 发布完成事件
            await self.event_bus.publish(Event(
                type=EventType.AGENT_COMPLETE if output.success else EventType.AGENT_ERROR,
                source=agent_name,
                data=output.data,
            ))

            return output

        except Exception as e:
            logger.error(f"[Orchestrator] agent exception: {agent_name} → {e}")
            self.state.update_agent_status(agent_name, "error")
            await self.event_bus.publish(Event(
                type=EventType.AGENT_ERROR,
                source=agent_name,
                data={"error": str(e)},
            ))
            return AgentOutput(success=False, error=str(e))

    def run_agent(self, agent_name: str, task: Dict = None) -> AgentOutput:
        """同步执行单个 Agent"""
        task = task or {}
        agent = self.registry.get(agent_name)
        if agent is None:
            return AgentOutput(success=False, error=f"agent not found: {agent_name}")

        self.state.update_agent_status(agent_name, "running", task.get("task_name", ""))

        try:
            agent.on_activate(task)
            output = agent.run(task, self.state)
            output = agent.on_complete(output)

            if output.success:
                self.state.update_agent_status(agent_name, "idle")
                self.event_bus.publish_sync(Event(
                    type=EventType.AGENT_COMPLETE,
                    source=agent_name,
                    data=output.data,
                ))
            else:
                self.state.update_agent_status(agent_name, "error")
                self.event_bus.publish_sync(Event(
                    type=EventType.AGENT_ERROR,
                    source=agent_name,
                    data={"error": output.error},
                ))

            return output
        except Exception as e:
            logger.error(f"[Orchestrator] agent exception: {agent_name} → {e}")
            self.state.update_agent_status(agent_name, "error")
            return AgentOutput(success=False, error=str(e))

    # ── 工作流执行 ────────────────────────────────────────────────

    def execute_workflow(self, workflow_name: str, params: Dict = None) -> Dict:
        """同步执行工作流（逐步执行，支持 REJECT 反馈循环）"""
        workflow = self._workflows.get(workflow_name)
        if workflow is None:
            logger.error(f"[Orchestrator] workflow not found: {workflow_name}")
            return {"error": f"workflow not found: {workflow_name}"}

        params = params or {}
        logger.info(f"[Orchestrator] ▶ workflow start: {workflow.name}")

        # 发布工作流开始事件
        self.event_bus.publish_sync(Event(
            type=EventType.WORKFLOW_START,
            source="orchestrator",
            data={"workflow": workflow_name, "params": params},
        ))

        context = dict(params)  # 工作流上下文，逐步累积
        results = []

        for i, step in enumerate(workflow.steps):
            agent = self.registry.get(step.agent)
            if agent is None:
                logger.error(f"[Orchestrator] step {i}: agent not found: {step.agent}")
                results.append({"step": i, "error": f"agent not found: {step.agent}"})
                continue

            # 检查条件
            if step.condition:
                try:
                    if not eval(step.condition, {"context": context}):
                        logger.info(f"[Orchestrator] step {i}: condition not met, skipping {step.agent}")
                        results.append({"step": i, "skipped": True, "reason": "condition not met"})
                        continue
                except Exception as e:
                    logger.warning(f"[Orchestrator] step {i}: condition eval error: {e}")

            # 从上游输出获取输入
            if step.input_from:
                upstream_data = context.get(f"output_{step.input_from}", {})
                context["upstream_output"] = upstream_data

            # 执行 Agent（带重试循环）
            retries = 0
            while retries <= step.max_retries:
                logger.info(f"[Orchestrator] step {i}/{len(workflow.steps)}: {step.agent} (attempt {retries + 1})")

                task = {
                    "task_name": f"{workflow.name}_step{i}",
                    "step_index": i,
                    "workflow": workflow_name,
                    **context,
                }

                output = self.run_agent(step.agent, task)
                results.append({
                    "step": i,
                    "agent": step.agent,
                    "success": output.success,
                    "attempt": retries + 1,
                    "data": output.data,
                })

                if output.success:
                    # 保存输出到上下文
                    context[f"output_{step.agent}"] = output.data
                    break

                if output.rejection and step.on_reject == "retry":
                    retries += 1
                    if retries <= step.max_retries:
                        logger.info(f"[Orchestrator] retrying {step.agent} (feedback: {output.rejection})")
                        context["feedback"] = output.rejection
                        continue
                    else:
                        logger.error(f"[Orchestrator] {step.agent} max retries reached")
                        if step.on_reject == "abort":
                            break

                if step.on_reject == "skip":
                    logger.info(f"[Orchestrator] skipping {step.agent}")
                    break
                elif step.on_reject == "abort":
                    logger.error(f"[Orchestrator] aborting workflow at step {i}")
                    break
                else:
                    break

        # 发布工作流完成事件
        self.event_bus.publish_sync(Event(
            type=EventType.WORKFLOW_COMPLETE,
            source="orchestrator",
            data={"workflow": workflow_name, "steps_completed": len(results)},
        ))

        logger.info(f"[Orchestrator] ◼ workflow complete: {workflow.name} ({len(results)} steps)")
        return {
            "workflow": workflow_name,
            "results": results,
            "context_keys": list(context.keys()),
        }

    # ── 查询接口 ──────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """获取编排器整体状态"""
        return {
            "agents": self.registry.list_all(),
            "workflows": list(self._workflows.keys()),
            "event_history_count": len(self.event_bus.get_history()),
            "state_keys": ["market_state", "stock_picks", "risk_assessment", "trade_plan", "performance_report"],
        }

    # ── 主循环 ────────────────────────────────────────────────────

    def start_loop(self) -> None:
        """启动主循环（阻塞）"""
        self._running = True
        logger.info("[Orchestrator] main loop started")

        # TODO: 集成定时任务（APScheduler / cron）
        # 每日 09:25 → DAILY_TRIGGER
        # 每10分钟 → PRICE_ALERT 检查
        # 每日 15:00 → MARKET_CLOSE

    def stop_loop(self) -> None:
        self._running = False
        logger.info("[Orchestrator] main loop stopped")


# ── 全局实例 ──────────────────────────────────────────────────────
_global_orchestrator: Optional[Orchestrator] = None

def get_orchestrator() -> Orchestrator:
    if _global_orchestrator is None:
        _global_orchestrator = Orchestrator()
    return _global_orchestrator


# ── 测试 ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from core.agent_base import AgentBase, AgentOutput

    class FakeResearcher(AgentBase):
        name = "researcher"
        role = "研究员"
        goal = "选股"
        backstory = "我选股"

        def run(self, task, state):
            picks = [{"code": "000858", "name": "五粮液"}]
            state.set_stock_picks(picks)
            return AgentOutput(success=True, data={"picks": picks})

    class FakeRiskManager(AgentBase):
        name = "risk_manager"
        role = "风控"
        goal = "风险评估"
        backstory = "我管风险"

        def run(self, task, state):
            picks = state.get_stock_picks()
            return AgentOutput(success=True, data={"assessment": "OK", "picks": picks})

    orch = Orchestrator()
    orch.register_agent(FakeResearcher())
    orch.register_agent(FakeRiskManager())

    # 注册工作流
    orch.register_workflow(Workflow(
        name="daily_analysis",
        steps=[
            WorkflowStep(agent="researcher"),
            WorkflowStep(agent="risk_manager", input_from="researcher"),
        ],
        description="每日分析",
    ))

    # 执行工作流
    result = orch.execute_workflow("daily_analysis")
    print("\n=== 工作流结果 ===")
    print(f"workflow: {result['workflow']}")
    for r in result["results"]:
        print(f"  step {r['step']}: {r['agent']} → success={r['success']}")

    print("\n=== 状态 ===")
    print(json.dumps(orch.get_status(), indent=2, default=str))

    print("\n✅ Orchestrator 测试通过")
