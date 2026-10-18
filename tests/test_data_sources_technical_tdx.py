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

    def test_output_keys_unchanged(self):
        """锁 键名与条数，避免下游取值漂移。"""
        out = calculate_technical(_df())
        expected = {
            "收盘价", "MA5", "MA20", "MA60", "RSI",
            "MACD直方图", "MACD_DIF", "MACD_DEA", "MACD信号",
            "布林带位置%", "布林带信号", "5日涨跌%", "最新日期",
        }
        assert set(out.keys()) == expected

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

