"""
Agent 基类 - 统一所有 Agent 的接口、生命周期、工具调用
"""
import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orchestrator")


# ── Agent 状态枚举 ────────────────────────────────────────────────
class AgentStatus(str, Enum):
    IDLE     = "idle"
    RUNNING  = "running"
    WAITING  = "waiting"    # 等待上游输入或人工审批
    ERROR    = "error"
    REJECTED = "rejected"   # 被下游退回


# ── Agent 输出 ────────────────────────────────────────────────────
@dataclass
class AgentOutput:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    rejection: Optional[str] = None   # 如果退回上游，写明原因
    hold: bool = False                # Trader 决定等待
    events: List[Dict] = field(default_factory=list)  # 要发布的事件
    error: Optional[str] = None


# ── Agent 基类 ────────────────────────────────────────────────────
class AgentBase(ABC):
    """所有 Agent 的统一基类

    子类必须实现:
        - run(task, state) → AgentOutput
        - role, goal, backstory 属性

    可选覆写:
        - on_reject(reason, from_agent) → AgentOutput
    """

    # ── 子类必须定义 ──
    name: str = "base_agent"
    role: str = ""
    goal: str = ""
    backstory: str = ""
    tools: List[Any] = []       # CrewAI Tool 列表

    # ── 运行时状态 ──
    status: AgentStatus = AgentStatus.IDLE
    last_run_time: float = 0
    last_output: Optional[AgentOutput] = None
    reject_count: int = 0      # 被退回次数
    max_rejects: int = 3       # 最大重试次数

    # ── LLM 配置 ──
    _llm = None

    def get_llm(self):
        """获取 LLM 实例（延迟初始化）"""
        if self._llm is None:
            from agents import get_llm
            self._llm = get_llm()
        return self._llm

    # ── 生命周期钩子 ──────────────────────────────────────────────

    def on_activate(self, context: Dict) -> None:
        """被编排器激活时调用（前置准备）"""
        self.status = AgentStatus.RUNNING
        self.reject_count = 0
        logger.info(f"[Agent:{self.name}] activated | context keys: {list(context.keys())}")

    def on_complete(self, output: AgentOutput) -> AgentOutput:
        """任务完成后调用（后置处理）"""
        self.status = AgentStatus.IDLE
        self.last_run_time = time.time()
        self.last_output = output
        logger.info(f"[Agent:{self.name}] complete | success={output.success} | data keys: {list(output.data.keys())}")
        return output

    def on_reject(self, reason: str, from_agent: str) -> AgentOutput:
        """被下游 Agent 退回时调用"""
        self.reject_count += 1
        logger.warning(f"[Agent:{self.name}] rejected by {from_agent} (#{self.reject_count}): {reason}")

        if self.reject_count >= self.max_rejects:
            logger.error(f"[Agent:{self.name}] max rejects reached ({self.max_rejects}), giving up")
            return AgentOutput(
                success=False,
                error=f"被退回{self.reject_count}次，放弃: {reason}",
                rejection=reason,
            )

        self.status = AgentStatus.REJECTED
        # 默认：直接重跑（子类可覆写此逻辑，加入 reason 修正提示）
        return self._retry_with_feedback(reason, from_agent)

    def _retry_with_feedback(self, reason: str, from_agent: str) -> AgentOutput:
        """带反馈重试（子类可覆写以调整 prompt）"""
        logger.info(f"[Agent:{self.name}] retrying with feedback: {reason}")
        # 默认返回一个 "需要重跑" 的信号
        return AgentOutput(
            success=False,
            error="需要重跑",
            rejection=reason,
            data={"retry": True, "feedback": reason, "from": from_agent},
        )

    # ── 核心执行方法 ──────────────────────────────────────────────

    @abstractmethod
    def run(self, task: Dict, state: Any) -> AgentOutput:
        """核心执行方法 — 子类必须实现

        Args:
            task: 任务参数（来自编排器）
            state: StateStore 实例

        Returns:
            AgentOutput
        """
        pass

    # ── 工具调用 ──────────────────────────────────────────────────

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """安全调用工具"""
        for tool in self.tools:
            if hasattr(tool, 'name') and tool.name == tool_name:
                try:
                    logger.info(f"[Agent:{self.name}] calling tool: {tool_name}({kwargs})")
                    result = tool._run(**kwargs) if hasattr(tool, '_run') else tool(**kwargs)
                    return result
                except Exception as e:
                    logger.error(f"[Agent:{self.name}] tool error: {tool_name} → {e}")
                    return {"error": str(e)}
        logger.warning(f"[Agent:{self.name}] tool not found: {tool_name}")
        return {"error": f"tool not found: {tool_name}"}

    # ── 创建 CrewAI Agent ────────────────────────────────────────

    def create_crewai_agent(self, tools: Optional[List] = None, max_iter: Optional[int] = None):
        """创建 CrewAI Agent 实例（带工具）

        tools 省略时用子类的全量工具（自定义编排路径依赖那份）。CrewAI 流水线可只传
        本任务真正需要的工具：run6 实测研究员拿到全套后会逐只调 technical_analysis /
        news_sentiment，38 次调用烧光 max_iter，最后只回显框架的收尾提示语。

        max_iter 省略时用 AGENT_MAX_ITER（置 0 表示沿用 CrewAI 默认 25）。
        显式传入时按智能体单独放宽：风控/交易员/调仓要按持仓逐只调 stop_loss_advice /
        risk_reward / set_stop_loss，8 轮撑不住（9/26 实测风控撞上限后只回显框架
        收尾提示语，下游交易员同样被毒化）。这几个智能体放到 25。
        """
        try:
            from crewai import Agent
            # CrewAI 默认 25 轮。本地模型 20 token/s，且每轮都把工具结果累积进 prompt，
            # 轮数一多既拖垮耗时又会顶满上下文窗口，故默认收紧上限；置 0 表示沿用默认。
            if max_iter is None:
                max_iter = int(os.getenv("AGENT_MAX_ITER", "4") or 0)
            max_iter = int(max_iter or 0)
            llm = self.get_llm()
            if llm is None:
                # get_llm() 在 API Key 缺失/为占位符时返回 None，
                # 直接传给 Agent 会在 kickoff 阶段弹零粉错误，
                # 这里提前给出明确配置错误（9/26 本地模型审查）。
                raise ValueError(
                    f"[Agent:{self.name}] LLM 未配置：get_llm() 返回 None，"
                    f"请检查 OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME"
                )
            return Agent(
                role=self.role,
                goal=self.goal,
                backstory=self.backstory,
                llm=llm,
                tools=self.tools if tools is None else tools,
                verbose=True,
                allow_delegation=False,
                **({"max_iter": max_iter} if max_iter > 0 else {}),
            )
        except ImportError:
            logger.warning("[Agent] crewai not installed, using fallback")
            return None

    # ── 状态信息 ──────────────────────────────────────────────────

    def get_status(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "role": self.role,
            "reject_count": self.reject_count,
            "last_run_time": self.last_run_time,
            "has_tools": len(self.tools) > 0,
            "tool_names": [t.name for t in self.tools if hasattr(t, 'name')],
        }

    def __repr__(self):
        return f"<Agent:{self.name} status={self.status.value} tools={len(self.tools)}>"


# ── Agent 注册表 ──────────────────────────────────────────────────
class AgentRegistry:
    """Agent 注册表 — 管理所有 Agent 实例"""

    def __init__(self):
        self._agents: Dict[str, AgentBase] = {}

    def register(self, agent: AgentBase) -> None:
        self._agents[agent.name] = agent
        logger.info(f"[Registry] registered agent: {agent.name}")

    def get(self, name: str) -> Optional[AgentBase]:
        return self._agents.get(name)

    def list_all(self) -> Dict[str, Dict]:
        return {name: agent.get_status() for name, agent in self._agents.items()}

    def get_by_event(self, event_type: str) -> List[AgentBase]:
        """根据事件类型找到应该响应的 Agent"""
        # 默认路由表（可覆写）
        event_agent_map = {
            "market_open": ["market_watcher"],
            "market_close": ["performance_auditor"],
            "price_alert": ["risk_manager"],
            "daily_trigger": ["market_watcher"],
            "manual_trigger": ["market_watcher"],
            "agent_complete": [],   # 由编排器根据 source 动态路由
            "agent_reject": [],     # 由编排器根据 data 动态路由
        }
        agent_names = event_agent_map.get(event_type, [])
        return [self._agents[n] for n in agent_names if n in self._agents]


# ── 测试 ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    class TestAgent(AgentBase):
        name = "test_agent"
        role = "测试"
        goal = "验证基类"
        backstory = "我是个测试 Agent"

        def run(self, task, state):
            return AgentOutput(success=True, data={"msg": "hello"})

    agent = TestAgent()
    agent.on_activate({"test": True})
    output = agent.run({}, None)
    agent.on_complete(output)

    print("status:", agent.get_status())
    print("output:", output)

    # 测试 reject
    reject_out = agent.on_reject("风险太大", "risk_manager")
    print("reject:", reject_out)

    print("\n✅ AgentBase 测试通过")
