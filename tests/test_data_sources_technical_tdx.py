"""
data_sources/technical.py 指标口径测试：对齐通达信，并与 technical_indicators 交叉一致。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest

from data_sources.technical import calculate_technical, _tdx_ema, _wilder_series
import technical_indicators as ti


def _df(n=120):
    prices = []
    v = 10.0
    for i in range(n):
        v = v + ((7 * (i + 3)) % 17 - 8) / 100.0
        prices.append(round(v, 4))
    return pd.DataFrame({
        "日期": [f"2026-01-{i + 1:02d}" for i in range(n)],
        "收盘": prices,
    })


class TestTdxEma:
    """EMA 以前 N 项均值做种子，而非 pandas 首元素种子。"""

    def test_differs_from_pandas_ewm_on_short_series(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        assert _tdx_ema(s, 3).iloc[-1] != s.ewm(span=3, adjust=False).mean().iloc[-1]

    def test_converges_on_long_series(self):
        s = pd.Series([10.0 + i * 0.01 for i in range(300)])
        assert _tdx_ema(s, 12).iloc[-1] == pytest.approx(
            s.ewm(span=12, adjust=False).mean().iloc[-1], rel=1e-6)

    def test_constant_series_is_constant(self):
        s = pd.Series([5.0] * 40)
        assert _tdx_ema(s, 12).iloc[-1] == pytest.approx(5.0)

    def test_insufficient_length_is_nan(self):
        s = pd.Series([1.0, 2.0])
        assert pd.isna(_tdx_ema(s, 12).iloc[-1])

    def test_index_preserved(self):
        s = pd.Series([1.0, 2.0, 3.0], index=["a", "b", "c"])
        assert list(_tdx_ema(s, 2).index) == ["a", "b", "c"]


class TestWilderSeries:
    """Wilder 平滑等价 SMA(X,N,1)。"""

    def test_constant_series_is_constant(self):
        s = pd.Series([3.0] * 40)
        assert _wilder_series(s, 14).iloc[-1] == pytest.approx(3.0)

    def test_insufficient_length_is_nan(self):
        assert pd.isna(_wilder_series(pd.Series([1.0, 2.0]), 14).iloc[-1])

    def test_matches_scalar_impl(self):
        values = [10.0 + i * 0.05 for i in range(40)]
        got = _wilder_series(pd.Series(values), 14).iloc[-1]
        exp = ti.calculate_sma_seed_series(values, 14, 1)[-1]
        assert got == pytest.approx(exp)


class TestCalculateTechnical:
    """端到端：口径正确，且与 technical_indicators 一致。"""

    def test_empty_df_returns_empty(self):
        assert calculate_technical(pd.DataFrame()) == {}

    def test_short_df_returns_empty(self):
        assert calculate_technical(_df(10)) == {}

    def test_macd_hist_not_always_zero(self):
        """回归锁：旧实现若把 DEA 当成常量，柱会恒为 0。"""
        out = calculate_technical(_df())
        assert out["MACD直方图"] != 0

    def test_macd_hist_is_twice_dif_minus_dea(self):
        out = calculate_technical(_df())
        assert out["MACD直方图"] == pytest.approx(
            2 * (out["MACD_DIF"] - out["MACD_DEA"]), abs=1e-3)

    def test_macd_matches_technical_indicators(self):
        prices = [10.0]
        v = 10.0
        for i in range(120):
            v = v + ((7 * (i + 3)) % 17 - 8) / 100.0
            prices.append(round(v, 4))
        prices = prices[1:]
        out = calculate_technical(_df())
        dif, dea, hist = ti.calculate_macd(prices)
        assert out["MACD_DIF"] == pytest.approx(dif, abs=1e-4)
        assert out["MACD_DEA"] == pytest.approx(dea, abs=1e-4)
        assert out["MACD直方图"] == pytest.approx(hist, abs=1e-4)

    def test_rsi_matches_technical_indicators(self):
        prices = []
        v = 10.0
        for i in range(120):
            v = v + ((7 * (i + 3)) % 17 - 8) / 100.0
            prices.append(round(v, 4))
        out = calculate_technical(_df())
        assert out["RSI"] == pytest.approx(ti.calculate_rsi(prices), abs=0.1)

    def test_rsi_bounded(self):
        out = calculate_technical(_df())
        assert 0 <= out["RSI"] <= 100

    def test_flat_market_rsi_is_neutral(self):
        n = 40
        df = pd.DataFrame({"日期": [f"d{i}" for i in range(n)], "收盘": [10.0] * n})
        assert calculate_technical(df)["RSI"] == 50.0

    def test_monotonic_up_rsi_is_100(self):
        n = 40
        df = pd.DataFrame({"日期": [f"d{i}" for i in range(n)],
                           "收盘": [10.0 + i * 0.1 for i in range(n)]})
        assert calculate_technical(df)["RSI"] == 100.0

    def test_monotonic_down_rsi_is_0(self):
        n = 40
        df = pd.DataFrame({"日期": [f"d{i}" for i in range(n)],
                           "收盘": [50.0 - i * 0.1 for i in range(n)]})
        assert calculate_technical(df)["RSI"] == 0.0

    # 键集合见文末 TestOutputKeysIncludePin（插针字段新增后统一维护在那里）

    def test_ma_values_unchanged(self):
        """MA 与布林带本就是通达信口径，锁定不回归。"""
        prices = []
        v = 10.0
        for i in range(120):
            v = v + ((7 * (i + 3)) % 17 - 8) / 100.0
            prices.append(round(v, 4))
        out = calculate_technical(_df())
        assert out["MA5"] == round(sum(prices[-5:]) / 5, 2)
        assert out["MA20"] == round(sum(prices[-20:]) / 20, 2)

    def test_macd_signal_label(self):
        out = calculate_technical(_df())
        assert out["MACD信号"] in ("金叉", "死叉")
        assert out["MACD信号"] == ("金叉" if out["MACD直方图"] > 0 else "死叉")



class TestPinAlignmentWithTechnicalIndicators:
    """插针判定必须与 technical_indicators 给出一致结论（52.7 的横切教训）。

    两处实现各写一份形状判定，若口径漂移，同一根K线在日报和技术分析里会
    出现两种说法。这里用同一组K线交叉比对。
    """

    def _bars(self):
        # 末尾三根：普通阳线 / 长下影锤子 / 长上影射击之星
        opens = [10.0, 10.0, 10.0]
        highs = [10.5, 10.2, 11.2]
        lows = [9.8, 9.0, 9.9]
        closes = [10.4, 10.1, 10.0]
        n = len(opens)
        return pd.DataFrame({
            "日期": [f"2026-03-{i + 1:02d}" for i in range(n)],
            "开盘": opens, "最高": highs, "最低": lows, "收盘": closes,
        })

    def test_same_pins_as_reference_implementation(self):
        from data_sources.technical import detect_pins
        df = self._bars()
        got = detect_pins(df)
        expected = [ti._bar_shape(df["开盘"].iloc[i], df["最高"].iloc[i],
                                   df["最低"].iloc[i], df["收盘"].iloc[i])
                    for i in range(len(df) - 1, -1, -1)]
        expected = [e["kind"] for e in expected if e]
        assert got == expected

    def test_both_pins_present_in_window(self):
        from data_sources.technical import detect_pins
        pins = detect_pins(self._bars())
        assert "lower" in pins
        assert "upper" in pins

    def test_result_carries_pin_text(self):
        # calculate_technical 要求 >=20 行，否则整体返回 {}；把三根K线拼在普通数据后面
        base = _df(20)
        pins_df = pd.concat([base, self._bars()], ignore_index=True)
        out = calculate_technical(pins_df)
        assert "插针" in out
        assert "长下影" in out["插针"]
        assert "长上影" in out["插针"]

    def test_no_pin_reports_none(self):
        from data_sources.technical import detect_pins
        flat = pd.DataFrame({
            "日期": ["2026-03-01"],
            "开盘": [10.0], "最高": [10.4], "最低": [9.9], "收盘": [10.3],
        })
        assert detect_pins(flat) == []
        assert calculate_technical(flat) == {}   # 长度不足20，整体短路

    def test_missing_columns_returns_empty(self):
        from data_sources.technical import detect_pins
        assert detect_pins(pd.DataFrame({"收盘": [1.0, 2.0]})) == []

    def test_lookback_zero_scans_everything(self):
        from data_sources.technical import detect_pins
        pins = detect_pins(self._bars(), lookback=0)
        assert len(pins) == 2


class TestOutputKeysIncludePin:
    """输出键集合锁定：插针是新增字段，别把旧键挤掉。"""

    def test_key_set(self):
        out = calculate_technical(_df())
        expected = {
            "收盘价", "MA5", "MA20", "MA60", "RSI",
            "MACD直方图", "MACD_DIF", "MACD_DEA", "MACD信号",
            "布林带位置%", "布林带信号", "5日涨跌%", "最新日期", "插针",
        }
        assert set(out.keys()) == expected