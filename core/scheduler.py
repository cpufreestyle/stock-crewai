"""APScheduler 定时调度 — 交易日自动运行分析/监控/审计"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# 中国交易日历简化版（排除周末，节假日需手动维护）
WEEKDAYS = "mon-fri"

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _is_trading_hours():
    """检查当前是否在交易时段 (9:30-11:30, 13:00-15:00)"""
    now = datetime.now()
    h, m = now.hour, now.minute
    morning = (h == 9 and m >= 30) or (h == 10) or (h == 11 and m <= 30)
    afternoon = (h == 13) or (h == 14) or (h == 15 and m == 0)
    return morning or afternoon


def run_daily_analysis():
    """每日开盘前分析 (9:25)"""
    if not _is_trading_hours():
        # 非交易时段也允许手动触发
        pass
    try:
        from workflows.daily_analysis import create_orchestrator_with_agents
        orch = create_orchestrator_with_agents()
        result = orch.execute_workflow("daily_analysis")
        print(f"[Scheduler] 每日分析完成: {result}")
    except Exception as e:
        print(f"[Scheduler] 每日分析失败: {e}")


def run_realtime_check():
    """实时监控检查 (每10分钟，交易时段内)"""
    if not _is_trading_hours():
        return
    try:
        from workflows.realtime_monitor import RealtimeMonitorWorkflow
        wf = RealtimeMonitorWorkflow()
        result = wf.run_once()
        if result:
            print(f"[Scheduler] 实时监控完成: {result}")
    except Exception as e:
        print(f"[Scheduler] 实时监控失败: {e}")


def run_performance_audit():
    """收盘后绩效审计 (15:05)"""
    try:
        from agents.performance_auditor import PerformanceAuditorAgent
        auditor = PerformanceAuditorAgent()
        result = auditor.run_audit()
        print(f"[Scheduler] 绩效审计完成: {result}")
    except Exception as e:
        print(f"[Scheduler] 绩效审计失败: {e}")


def setup_jobs():
    """注册所有定时任务"""
    # 每日开盘前5分钟分析
    scheduler.add_job(
        run_daily_analysis,
        CronTrigger(day_of_week=WEEKDAYS, hour=9, minute=25),
        id="daily_analysis",
        name="每日开盘前分析",
        max_instances=1,
        misfire_grace_time=60,
    )

    # 交易时段内每10分钟监控
    scheduler.add_job(
        run_realtime_check,
        IntervalTrigger(minutes=10),
        id="realtime_monitor",
        name="实时监控(10min)",
        max_instances=1,
        misfire_grace_time=30,
    )

    # 收盘后绩效审计
    scheduler.add_job(
        run_performance_audit,
        CronTrigger(day_of_week=WEEKDAYS, hour=15, minute=5),
        id="performance_audit",
        name="收盘后绩效审计",
        max_instances=1,
        misfire_grace_time=60,
    )


def start():
    """启动调度器"""
    setup_jobs()
    scheduler.start()
    jobs = scheduler.get_jobs()
    print(f"[Scheduler] 已启动，{len(jobs)} 个定时任务:")
    for j in jobs:
        print(f"  {j.id}: {j.name} → next_run={j.next_run_time}")


def status():
    """获取调度器状态"""
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": j.id,
                "name": j.name,
                "next_run": str(j.next_run_time),
                "pending": j.pending,
            }
            for j in jobs
        ],
    }
