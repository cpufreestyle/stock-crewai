"""
插针（长影线）形态测试：锁定 _bar_shape / detect_pins / _score_pins 的判定边界。

口径：实体占振幅 <=1/3、长影占振幅 >=1/2、长影 >= 2*实体。
ATR 过滤只砍「影线 < 0.8*ATR」的短影噪声，不砍极端长影。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import technical_indicators as ti


class TestBarShapeLowerPin:
    """长下影（锤子线一侧，偏多）。"""

    def test_classic_hammer_is_detected(self):
        # 开10 高10.2 低9.0 收10.1：下影1.1、实体0.1、振幅1.2
        s = ti._bar_shape(10.0, 10.2, 9.0, 10.1)
        assert s is not None
        assert s["kind"] == "lower"
        assert s["body"] == pytest.approx(0.1 / 1.2, abs=1e-3)
        assert s["shadow"] == pytest.approx(1.0 / 1.2, abs=1e-3)
        assert s["wick_ratio"] == pytest.approx(10.0, abs=1e-3)

    def test_doji_with_long_lower_shadow(self):
        # 十字星 + 长下影：实体为0，倍数无意义但形态成立
        s = ti._bar_shape(10.0, 10.05, 9.0, 10.0)
        assert s is not None
        assert s["kind"] == "lower"
        assert s["wick_ratio"] is None


class TestBarShapeUpperPin:
    """长上影（射击之星一侧，偏空）。"""

    def test_classic_shooting_star_is_detected(self):
        # 开10 高11.2 低9.9 收10.0：上影1.2、实体0、振幅1.3
        s = ti._bar_shape(10.0, 11.2, 9.9, 10.0)
        assert s is not None
        assert s["kind"] == "upper"
        assert s["shadow"] == pytest.approx(1.2 / 1.3, abs=1e-3)

    def test_small_body_with_long_upper_shadow(self):
        # 开10 高11.0 低10.2 收10.15：上影0.85、实体0.15、振幅0.8
        s = ti._bar_shape(10.0, 11.0, 10.2, 10.15)
        assert s is not None
        assert s["kind"] == "upper"


class TestBarShapeRejects:
    """不该判为插针的形状。"""

    def test_plain_bullish_bar_is_not_a_pin(self):
        # 影线都短，实体占大头
        assert ti._bar_shape(10.0, 10.5, 9.8, 10.4) is None

    def test_big_body_is_not_a_pin(self):
        # 开10 高10.9 低8.9 收10.9：实体0.9、振幅2.0，实体占45%
        assert ti._bar_shape(10.0, 10.9, 8.9, 10.9) is None

    def test_flat_bar_is_not_a_pin(self):
        assert ti._bar_shape(10.0, 10.0, 10.0, 10.0) is None

    def test_shadow_shorter_than_body_is_not_a_pin(self):
        # 振幅2.0、实体1.2、下影0.8：影线 < 2*实体
        assert ti._bar_shape(10.0, 11.2, 9.2, 11.2) is None

    def test_shadow_below_half_span_is_not_a_pin(self):
        # 振幅1.0、实体0.3、下影0.4：影线占40% < 50%
        assert ti._bar_shape(10.0, 10.6, 9.6, 10.3) is None


class TestDetectPins:
    """lookback 窗口与 ATR 过滤。"""

    def _bars(self):
        highs = [10.5, 10.6, 10.2, 10.4, 10.3]
        lows = [9.8, 9.9, 9.0, 9.85, 9.9]
        opens = [10.0, 10.1, 10.0, 10.0, 10.05]
        closes = [10.4, 10.3, 10.1, 10.2, 10.1]
        return highs, lows, opens, closes

    def test_returns_newest_first(self):
        pins = ti.detect_pins(*self._bars())
        assert len(pins) == 2
        assert pins[0]["index"] == 4
        assert pins[1]["index"] == 2

    def test_lookback_limits_window(self):
        # lookback=2 只看最后两根，index 2 那根被排除
        pins = ti.detect_pins(*self._bars(), lookback=2)
        assert len(pins) == 1
        assert pins[0]["index"] == 4

    def test_atr_filter_drops_short_shadow_noise(self):
        # index 4 上影 0.2，ATR=1.0 时 0.2 < 0.8 被砍；index 2 下影1.0 保留
        pins = ti.detect_pins(*self._bars(), atr=1.0)
        assert len(pins) == 1
        assert pins[0]["kind"] == "lower"

    def test_large_atr_drops_everything(self):
        assert ti.detect_pins(*self._bars(), atr=5.0) == []

    def test_empty_input(self):
        assert ti.detect_pins([], [], [], []) == []

    def test_unequal_lengths_use_shortest(self):
        pins = ti.detect_pins([10.5, 10.6], [9.8, 9.9], [10.0], [10.4, 10.3])
        assert pins == []


class TestScorePins:
    """插针只按方向记分，同向多次不重复加分。"""

    def test_lower_pin_adds(self):
        detail = []
        score, detail = ti._score_pins([{"kind": "lower"}], 0, detail)
        assert score == 2
        assert detail == ["长下影插针(+2)"]

    def test_upper_pin_subtracts(self):
        detail = []
        score, detail = ti._score_pins([{"kind": "upper"}], 0, detail)
        assert score == -2
        assert detail == ["长上影插针(-2)"]

    def test_both_directions_cancel(self):
        detail = []
        score, detail = ti._score_pins(
            [{"kind": "upper"}, {"kind": "lower"}], 0, detail)
        assert score == 0
        assert len(detail) == 2

    def test_repeated_same_direction_counts_once(self):
        detail = []
        score, detail = ti._score_pins(
            [{"kind": "lower"}, {"kind": "lower"}], 0, detail)
        assert score == 2
        assert detail == ["长下影插针(+2)"]

    def test_no_pin_leaves_score_untouched(self):
        detail = ["MA多头排列(+3)"]
        score, detail = ti._score_pins([], 3, detail)
        assert score == 3
        assert detail == ["MA多头排列(+3)"]