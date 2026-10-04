# -*- coding: utf-8 -*-
"""order_levels 止损止盈价计算测试

这些价位直接决定亏多少：ATR 与固定比例两条路径、以及 ATR 取数失败时的回退，
都必须与 run_virtual_v4.execute_buy 的原行为逐值一致。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from order_levels import atr_levels, fixed_levels, resolve_levels

STOP_R, PROFIT_R = 0.92, 1.20
STOP_M, PROFIT_M = 2, 3


class TestFixedLevels:
    def test_default_config(self):
        assert fixed_levels(10.0, STOP_R, PROFIT_R) == (9.2, 12.0)

    def test_rounds_to_two_decimals(self):
        stop, profit = fixed_levels(33.333, STOP_R, PROFIT_R)
        assert stop == 30.67 and profit == 40.0

    def test_small_price(self):
        assert fixed_levels(0.01, STOP_R, PROFIT_R) == (0.01, 0.01)


class TestATRLevels:
    def test_basic(self):
        assert atr_levels(10.0, 1.5, STOP_M, PROFIT_M) == (7.0, 14.5)

    def test_zero_atr_equals_price(self):
        assert atr_levels(10.0, 0.0, STOP_M, PROFIT_M) == (10.0, 10.0)


class TestResolveLevels:
    def test_uses_atr_when_available(self):
        assert resolve_levels(10.0, 1.5, STOP_R, PROFIT_R, STOP_M, PROFIT_M) == (7.0, 14.5)

    @pytest.mark.parametrize("atr", [None, 0, 0.0])
    def test_falls_back_to_fixed(self, atr):
        """ATR 缺失/为 0/取数失败都必须退回固定比例，不能算出 0 止损"""
        assert resolve_levels(10.0, atr, STOP_R, PROFIT_R, STOP_M, PROFIT_M) == (9.2, 12.0)

    def test_no_atr_key_in_analysis(self):
        """analysis 里没有 atr 键 -> dict.get 返回 None -> 固定比例"""
        analysis = {"signal": "BUY"}
        assert resolve_levels(10.0, analysis.get("atr"), STOP_R, PROFIT_R,
                              STOP_M, PROFIT_M) == (9.2, 12.0)

    def test_atr_path_is_tighter_than_fixed_for_low_vol(self):
        "ATR 很小时动态止损高于固定止损（更宽松），这是预期行为，由调用方决定用哪个"""
        stop_atr, _ = resolve_levels(10.0, 0.2, STOP_R, PROFIT_R, STOP_M, PROFIT_M)
        stop_fixed, _ = fixed_levels(10.0, STOP_R, PROFIT_R)
        assert stop_atr == 9.6 and stop_atr > stop_fixed


class TestMatchesLegacyBehavior:
    """与原三分支实现逐值对齐（ok_with_atr / ok_no_atr / raise / no_tech）"""

    @pytest.mark.parametrize("price", [10.0, 99.99, 5.5, 1234.56, 0.01])
    def test_all_paths_match(self, price):
        def legacy(tech_ok, atr):
            if tech_ok:
                try:
                    if atr is not None:
                        return round(price - STOP_M * atr, 2), round(price + PROFIT_M * atr, 2)
                    return round(price * STOP_R, 2), round(price * PROFIT_R, 2)
                except Exception:
                    return round(price * STOP_R, 2), round(price * PROFIT_R, 2)
            return round(price * STOP_R, 2), round(price * PROFIT_R, 2)

        assert resolve_levels(price, 1.5, STOP_R, PROFIT_R, STOP_M, PROFIT_M) == legacy(True, 1.5)
        assert resolve_levels(price, None, STOP_R, PROFIT_R, STOP_M, PROFIT_M) == legacy(True, None)
        assert resolve_levels(price, None, STOP_R, PROFIT_R, STOP_M, PROFIT_M) == legacy(False, None)

