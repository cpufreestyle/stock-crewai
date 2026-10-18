"""
交易防护模块（trade_guards）测试套件
运行: pytest tests/test_trade_guards.py -v
"""
import sys
from pathlib import Path

import pytest

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

import trade_guards as tg


class TestLimitPct:
    def test_main_board_10pct(self):
        assert tg._limit_pct("600519") == 0.10
        assert tg._limit_pct("000001") == 0.10

    def test_chi_next_star_20pct(self):
        assert tg._limit_pct("300750") == 0.20   # 创业板
        assert tg._limit_pct("301236") == 0.20   # 创业板注册制
        assert tg._limit_pct("688981") == 0.20   # 科创板


class TestValidatePrice:
    def test_invalid_price(self):
        ok, _ = tg.validate_price("600519", 0)
        assert not ok
        ok, _ = tg.validate_price("600519", -1)
        assert not ok

    def test_within_limit_passes(self):
        ok, reason = tg.validate_price("600519", 1760.0, prev_close=1600.0)
        assert ok, reason  # 涨停价 1760，未超

    def test_above_limit_rejected(self):
        # 主板涨停 1760，委托 1800 应拒绝
        ok, reason = tg.validate_price("600519", 1800.0, prev_close=1600.0)
        assert not ok
        assert "涨停" in reason

    def test_below_limit_rejected(self):
        # 跌停 1440，委托 1400 应拒绝
        ok, reason = tg.validate_price("600519", 1400.0, prev_close=1600.0)
        assert not ok
        assert "跌停" in reason

    def test_star_board_uses_20pct(self):
        # 科创板 ±20%：昨收 100 → 涨停 120，委托 119.9 合法（主板限价 110 会被拒）
        ok, _ = tg.validate_price("688981", 119.9, prev_close=100.0)
        assert ok
        ok2, reason2 = tg.validate_price("688981", 121.0, prev_close=100.0)
        assert not ok2 and "涨停" in reason2  # 超过 120 涨停价

    def test_stale_quote_detected(self):
        # 参考价 100，委托 106 偏离 6% > 5% → 拒绝
        ok, reason = tg.validate_price("000001", 106.0, reference_price=100.0)
        assert not ok
        assert "偏离" in reason

    def test_small_deviation_passes(self):
        ok, _ = tg.validate_price("000001", 103.0, reference_price=100.0)
        assert ok

    def test_no_reference_passes(self):
        # 无昨收无参考价时只做基本校验
        ok, _ = tg.validate_price("000001", 50.0)
        assert ok


class TestGetPrevClose:
    def test_from_realtime_data_last_close(self):
        data = {"600519": {"last_close": 1600.0}}
        assert tg.get_prev_close("600519", data) == 1600.0

    def test_from_realtime_data_prev_close(self):
        data = {"600519": {"prev_close": 1600.0}}
        assert tg.get_prev_close("600519", data) == 1600.0

    def test_missing_code(self):
        assert tg.get_prev_close("600519", {"000001": {}}) is None
        assert tg.get_prev_close("600519", None) is None


class TestCircuitBreakerIntegration:
    def test_allowed_when_clear(self, tmp_path, monkeypatch):
        import circuit_breaker as cb
        state_file = tmp_path / "cb.json"
        monkeypatch.setattr(cb, "CIRCUIT_BREAKER_FILE", str(state_file))
        monkeypatch.setattr("config.CIRCUIT_BREAKER_FILE", str(state_file))
        ok, reason = tg.check_circuit_breaker()
        assert ok

    def test_blocked_when_tripped(self, tmp_path, monkeypatch):
        import circuit_breaker as cb
        state_file = tmp_path / "cb.json"
        monkeypatch.setattr(cb, "CIRCUIT_BREAKER_FILE", str(state_file))
        monkeypatch.setattr("config.CIRCUIT_BREAKER_FILE", str(state_file))
        b = cb.CircuitBreaker()
        b._trip("测试熔断")
        ok, reason = tg.check_circuit_breaker()
        assert not ok
        assert "熔断" in reason
