"""
事件总线 - Agent 间通信的核心基础设施
基于 asyncio 的发布/订阅模式，支持事件过滤和优先级
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("orchestrator")


# ── 事件类型 ──────────────────────────────────────────────────────
class EventType(str, Enum):
    # 市场事件
    MARKET_OPEN      = "market_open"
    MARKET_CLOSE     = "market_close"
    PRICE_ALERT      = "price_alert"       # 股价异动
    SECTOR_SHIFT     = "sector_shift"       # 板块轮动信号

    # 编排事件
    DAILY_TRIGGER    = "daily_trigger"      # 定时分析触发
    MANUAL_TRIGGER   = "manual_trigger"     # Dashboard 手动触发
    WORKFLOW_START   = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"

    # Agent 事件
    AGENT_START      = "agent_start"
    AGENT_COMPLETE   = "agent_complete"
    AGENT_REJECT     = "agent_reject"       # 下游退回上游
    AGENT_HOLD       = "agent_hold"         # Trader 决定等待
    AGENT_ERROR      = "agent_error"

    # 交易事件
    TRADE_PROPOSED   = "trade_proposed"     # Trader 提出交易建议
    TRADE_APPROVED   = "trade_approved"     # 人工审批通过
    TRADE_EXECUTED   = "trade_executed"     # 交易执行完成
    TRADE_FAILED     = "trade_failed"

    # 风控事件
    CIRCUIT_BREAKER  = "circuit_breaker"    # 熔断触发
    STOP_LOSS_HIT    = "stop_loss_hit"      # 止损触发
    TAKE_PROFIT_HIT  = "take_profit_hit"    # 止盈触发

    # 系统事件
    SYSTEM_SHUTDOWN  = "system_shutdown"


# ── 事件对象 ──────────────────────────────────────────────────────
@dataclass
class Event:
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""            # 发出事件的 Agent 名称
    timestamp: float = field(default_factory=time.time)
    priority: int = 0           # 0=普通, 1=高, 2=紧急(止损等)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    @property
    def datetime_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def __repr__(self):
        return f"Event({self.type.value}, src={self.source}, data={self.data}, t={self.datetime_str})"


# ── 事件总线 ──────────────────────────────────────────────────────
class EventBus:
    """异步事件总线 — 发布/订阅模式"""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._wildcard_subscribers: List[Callable] = []
        self._history: List[Event] = []
        self._max_history = 200
        self._lock = None  # asyncio.Lock requires running loop; not needed for sync usage

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """订阅特定事件类型"""
        self._subscribers[event_type.value].append(handler)
        logger.info(f"[EventBus] {handler.__name__ if hasattr(handler, '__name__') else handler} → subscribed to {event_type.value}")

    def subscribe_all(self, handler: Callable) -> None:
        """订阅所有事件（用于日志/Dashboard 推送）"""
        self._wildcard_subscribers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """取消订阅"""
        subs = self._subscribers.get(event_type.value, [])
        if handler in subs:
            subs.remove(handler)

    async def publish(self, event: Event) -> None:
        """发布事件 → 调用所有订阅者"""
        logger.info(f"[EventBus] 📡 {event.type.value} from {event.source} | data keys: {list(event.data.keys())}")

        # 记录历史
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # 调用特定类型订阅者
        handlers = self._subscribers.get(event.type.value, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"[EventBus] handler error: {e}")

        # 调用通配订阅者
        for handler in self._wildcard_subscribers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"[EventBus] wildcard handler error: {e}")

    def publish_sync(self, event: Event) -> None:
        """同步发布（非异步上下文用）"""
        logger.info(f"[EventBus] 📡 sync {event.type.value} from {event.source}")

        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._subscribers.get(event.type.value, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"[EventBus] sync handler error: {e}")

        for handler in self._wildcard_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"[EventBus] sync wildcard handler error: {e}")

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 50) -> List[Event]:
        """获取事件历史"""
        if event_type:
            filtered = [e for e in self._history if e.type == event_type]
            return filtered[-limit:]
        return self._history[-limit:]

    def clear_history(self) -> None:
        self._history.clear()


# ── 全局实例 ──────────────────────────────────────────────────────
_global_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    """获取全局事件总线单例"""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


# ── 测试 ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    bus = EventBus()

    def on_price_alert(event: Event):
        print(f"  → 收到异动: {event.data}")

    def on_any(event: Event):
        print(f"  → [通配] {event}")

    bus.subscribe(EventType.PRICE_ALERT, on_price_alert)
    bus.subscribe_all(on_any)

    bus.publish_sync(Event(
        type=EventType.PRICE_ALERT,
        source="market_watcher",
        data={"code": "603799", "name": "华友钴业", "change": -8.2},
        priority=2,
    ))

    bus.publish_sync(Event(
        type=EventType.AGENT_COMPLETE,
        source="researcher",
        data={"picks": ["000858", "600519"]},
    ))

    print("\n=== 事件历史 ===")
    for e in bus.get_history(limit=5):
        print(f"  {e}")