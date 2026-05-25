"""风控熔断模块 - 连续亏损/单日回撤过大时暂停交易"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from config import (
    CIRCUIT_BREAKER_DAILY_LOSS_PCT,
    CIRCUIT_BREAKER_CONSECUTIVE_STOPS,
    CIRCUIT_BREAKER_COOLDOWN_MINUTES,
    CIRCUIT_BREAKER_FILE,
)
from safe_io import safe_load_json, safe_save_json


class CircuitBreaker:
    """风控熔断器"""

    def __init__(self):
        self._state = safe_load_json(
            CIRCUIT_BREAKER_FILE,
            default={
                "consecutive_stops": 0,
                "day_start_value": None,
                "day_start_date": None,
                "tripped": False,
                "tripped_at": None,
                "trip_reason": "",
            },
        )

    def _save(self):
        safe_save_json(CIRCUIT_BREAKER_FILE, self._state)

    def record_trade(self, pnl_pct: float, current_total_value: float):
        """记录一笔交易结果，检查是否需要熔断"""
        today = datetime.now().strftime("%Y-%m-%d")

        # 每日重置日初资产
        if self._state["day_start_date"] != today:
            self._state["day_start_date"] = today
            self._state["day_start_value"] = current_total_value

        # 统计连续止损
        if pnl_pct < 0:
            self._state["consecutive_stops"] += 1
        else:
            self._state["consecutive_stops"] = 0

        # 检查熔断条件
        # 1. 连续止损
        if self._state["consecutive_stops"] >= CIRCUIT_BREAKER_CONSECUTIVE_STOPS:
            self._trip(f"连续{self._state['consecutive_stops']}次止损")
            return

        # 2. 单日回撤
        if self._state["day_start_value"] and self._state["day_start_value"] > 0:
            daily_loss_pct = (
                (self._state["day_start_value"] - current_total_value)
                / self._state["day_start_value"]
                * 100
            )
            if daily_loss_pct >= CIRCUIT_BREAKER_DAILY_LOSS_PCT:
                self._trip(f"单日亏损{daily_loss_pct:.1f}%")
                return

        self._save()

    def _trip(self, reason: str):
        """触发熔断"""
        self._state["tripped"] = True
        self._state["tripped_at"] = datetime.now().isoformat()
        self._state["trip_reason"] = reason
        self._save()

    def is_tripped(self) -> bool:
        """检查是否处于熔断状态（含冷却期判断）"""
        if not self._state.get("tripped"):
            return False

        tripped_at = self._state.get("tripped_at")
        if not tripped_at:
            return True

        tripped_time = datetime.fromisoformat(tripped_at)
        cooldown = timedelta(minutes=CIRCUIT_BREAKER_COOLDOWN_MINUTES)

        if datetime.now() - tripped_time >= cooldown:
            # 冷却期结束，自动解除
            self._state["tripped"] = False
            self._state["consecutive_stops"] = 0
            self._state["tripped_at"] = None
            self._state["trip_reason"] = ""
            self._save()
            return False

        return True

    def get_status(self) -> dict:
        """获取熔断器状态"""
        tripped = self.is_tripped()
        remaining = None
        if tripped and self._state.get("tripped_at"):
            tripped_time = datetime.fromisoformat(self._state["tripped_at"])
            cooldown = timedelta(minutes=CIRCUIT_BREAKER_COOLDOWN_MINUTES)
            remaining_sec = max(0, (cooldown - (datetime.now() - tripped_time)).total_seconds())
            remaining = int(remaining_sec // 60)

        return {
            "tripped": tripped,
            "reason": self._state.get("trip_reason", ""),
            "consecutive_stops": self._state.get("consecutive_stops", 0),
            "remaining_minutes": remaining,
        }

    def reset(self):
        """手动解除熔断"""
        self._state["tripped"] = False
        self._state["consecutive_stops"] = 0
        self._state["tripped_at"] = None
        self._state["trip_reason"] = ""
        self._save()


# 全局单例
circuit_breaker = CircuitBreaker()
