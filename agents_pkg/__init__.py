"""
agents 包初始化 - 新版多 Agent 系统
"""
from agents.market_watcher import MarketWatcherAgent
from agents.researcher import ResearcherAgent
from agents.risk_manager_agent import RiskManagerAgent
from agents.trader import TraderAgent
from agents.performance_auditor import PerformanceAuditorAgent

__all__ = [
    "MarketWatcherAgent",
    "ResearcherAgent",
    "RiskManagerAgent",
    "TraderAgent",
    "PerformanceAuditorAgent",
]
