#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock CrewAI v5.0 - 多 Agent 协作系统统一入口

用法:
  python main.py                    # 单次每日分析
  python main.py --monitor          # 单次监控
  python main.py --monitor --loop   # 循环监控（交易时段）
  python main.py --dashboard        # 启动 Dashboard 服务
  python main.py --all              # 全部启动（分析+监控+Dashboard）
"""
import sys
import os

# UTF-8 输出
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def run_analysis():
    """运行每日分析"""
    from workflows.daily_analysis import run_daily_analysis
    result = run_daily_analysis()
    return result


def run_monitor(loop: bool = False):
    """运行实时监控"""
    from workflows.realtime_monitor import run_monitor_once, run_monitor_loop
    if loop:
        run_monitor_loop()
    else:
        return run_monitor_once()


def run_dashboard():
    """启动 Dashboard 服务（集成 Agent 状态 + Scheduler）"""
    # 启动调度器
    try:
        from core.scheduler import start as start_scheduler
        start_scheduler()
        logger.info("Scheduler 已启动")
    except Exception as e:
        logger.warning(f"Scheduler 启动失败（不影响 Dashboard）: {e}")

    from web_dashboard import app
    logger.info("Starting Dashboard on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)


def main():
    parser = argparse.ArgumentParser(description="Stock CrewAI v5.0 - 多 Agent 协作系统")
    parser.add_argument("--monitor", action="store_true", help="运行实时监控（止损止盈）")
    parser.add_argument("--loop", action="store_true", help="循环运行模式")
    parser.add_argument("--dashboard", action="store_true", help="启动 Dashboard 服务")
    parser.add_argument("--all", action="store_true", help="启动全部服务")
    parser.add_argument("--test", action="store_true", help="运行框架测试")
    args = parser.parse_args()

    if args.test:
        _run_framework_test()
        return

    if args.all:
        # 启动全部（Dashboard 在主线程，监控在子线程）
        import threading

        # 监控线程
        monitor_thread = threading.Thread(
            target=run_monitor_loop if args.loop else lambda: run_monitor(),
            daemon=True,
        )
        monitor_thread.start()

        # 分析（首次启动时执行一次）
        try:
            run_analysis()
        except Exception as e:
            logger.error(f"首次分析失败: {e}")

        # Dashboard（主线程）
        run_dashboard()
        return

    if args.dashboard:
        run_dashboard()
        return

    if args.monitor:
        run_monitor(loop=args.loop)
        return

    # 默认：单次每日分析
    result = run_analysis()
    print(f"\n{'='*60}")
    print("  工作流结果")
    print(f"{'='*60}")
    if result:
        print(f"  工作流: {result.get('workflow', 'N/A')}")
        for r in result.get("results", []):
            status = "✅" if r.get("success") else "❌"
            print(f"  {status} Step {r.get('step', '?')}: {r.get('agent', '?')}")
    print(f"{'='*60}")


def _run_framework_test():
    """框架组件自检"""
    print("=" * 60)
    print("  Stock CrewAI v5.0 框架自检")
    print("=" * 60)

    # 1. EventBus
    print("\n1. EventBus...")
    from core.event_bus import EventBus, Event, EventType
    bus = EventBus()
    bus.publish_sync(Event(type=EventType.SYSTEM_SHUTDOWN, source="test", data={"ok": True}))
    print(f"   ✅ EventBus 正常 (历史事件: {len(bus.get_history())})")

    # 2. StateStore
    print("\n2. StateStore...")
    from core.state_store import StateStore
    store = StateStore(":memory:")
    store.set("test_key", {"value": 123})
    assert store.get("test_key")["value"] == 123
    print("   ✅ StateStore 正常")

    # 3. AgentBase
    print("\n3. AgentBase...")
    from core.agent_base import AgentBase, AgentOutput
    class TestAgent(AgentBase):
        name = "test"
        role = "测试"
        goal = "验证"
        backstory = "测试Agent"
        def run(self, task, state):
            return AgentOutput(success=True, data={"msg": "ok"})
    agent = TestAgent()
    output = agent.run({}, None)
    assert output.success
    print("   ✅ AgentBase 正常")

    # 4. Orchestrator
    print("\n4. Orchestrator...")
    from core.orchestrator import Orchestrator, Workflow, WorkflowStep
    orch = Orchestrator(event_bus=bus, state_store=store)
    orch.register_agent(TestAgent())
    orch.register_workflow(Workflow(
        name="test_wf",
        steps=[WorkflowStep(agent="test")],
    ))
    result = orch.execute_workflow("test_wf")
    assert result["workflow"] == "test_wf"
    print(f"   ✅ Orchestrator 正常 (工作流: {result['workflow']})")

    # 5. Tools
    print("\n5. Tools...")
    from tools.market_tools import get_market_tools
    from tools.stock_tools import get_stock_tools
    from tools.risk_tools import get_risk_tools
    from tools.trade_tools import get_trade_tools
    from tools.notify_tools import get_notify_tools
    all_tools = get_market_tools() + get_stock_tools() + get_risk_tools() + get_trade_tools() + get_notify_tools()
    print(f"   ✅ Tools 正常 (共 {len(all_tools)} 个)")

    # 6. New Agents
    print("\n6. New Agents...")
    from agents.market_watcher import MarketWatcherAgent
    from agents.researcher import ResearcherAgent
    from agents.risk_manager_agent import RiskManagerAgent
    from agents.trader import TraderAgent
    from agents.performance_auditor import PerformanceAuditorAgent
    agents = [MarketWatcherAgent(), ResearcherAgent(), RiskManagerAgent(), TraderAgent(), PerformanceAuditorAgent()]
    for a in agents:
        print(f"   ✅ {a.name}: {a.role} ({len(a.tools)} tools)")
        # 写入状态
        store.update_agent_status(a.name, "idle")

    print(f"\n{'='*60}")
    print("  ✅ 全部组件自检通过！")
    print(f"{'='*60}")

    # 清理内存数据库
    store.close()


if __name__ == "__main__":
    main()
