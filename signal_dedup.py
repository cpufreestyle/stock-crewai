"""交易信号去重 - 同一股票在冷却窗口内只执行一次交易"""
import time
from typing import Dict, Optional

from config import SCAN_INTERVAL_MINUTES


class SignalDeduplicator:
    """信号去重器"""

    def __init__(self, cooldown_seconds: int = None):
        # 默认冷却时间 = 2个扫描周期，避免重复信号
        self.cooldown = cooldown_seconds or (SCAN_INTERVAL_MINUTES * 60 * 2)
        self._signals: Dict[str, float] = {}  # code -> last_signal_time

    def can_trade(self, code: str) -> bool:
        """检查该股票是否可以交易（冷却期内不重复）"""
        last = self._signals.get(code)
        if last is None:
            return True
        return (time.time() - last) >= self.cooldown

    def record_signal(self, code: str):
        """记录已发出信号"""
        self._signals[code] = time.time()

    def filter_duplicate(self, signals: list, code_key: str = "code") -> list:
        """过滤重复信号，返回可执行的信号列表"""
        result = []
        for sig in signals:
            code = sig.get(code_key) or sig.get("stock_code", "")
            if self.can_trade(code):
                result.append(sig)
                self.record_signal(code)
        return result

    def cleanup(self):
        """清理过期记录"""
        now = time.time()
        expired = [k for k, v in self._signals.items() if (now - v) >= self.cooldown]
        for k in expired:
            del self._signals[k]

    def status(self) -> dict:
        """查看当前去重状态"""
        self.cleanup()
        return {
            "active_codes": len(self._signals),
            "cooldown_seconds": self.cooldown,
            "blocked": list(self._signals.keys()),
        }


# 全局单例
signal_dedup = SignalDeduplicator()
