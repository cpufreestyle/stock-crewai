"""
技术指标口径测试：锁定通达信公式语义，防回归。

口径依据（通达信 TCalc.dll 内置公式原文，rea 反编译提取）：
    MACD:  DIFF:=EMA(CLOSE,SHORT)-EMA(CLOSE,LONG); DEA:=EMA(DIFF,M); MACD:=2*(DIFF-DEA)
    RSI:   WRSI:=SMA(MAX(CLOSE-LC,0),N,1)/SMA(ABS(CLOSE-LC),N,1)*100
    KDJ:   RSV:=(CLOSE-LLV(LOW,N))/(HHV(HIGH,N)-LLV(LOW,N))*100;
           K:=SMA(RSV,M1,1); D:=SMA(K,M2,1); J:=3*K-2*D
    EMA:   Y=(X*2+Y'*(N-1))/(N+1)，等价 SMA(X,N+1,2)
    SMA:   Y=(X*M+Y'*(N-M))/N，前 N 项均值做种子
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import technical_indicators as ti


def _synth(n=120):
    """确定性价格序列（无随机依赖，跨运行稳定）。"""
    prices = []
    v = 10.0
    for i in range(n):
        v = v + ((7 * (i + 3)) % 17 - 8) / 100.0
        prices.append(round(v, 4))
    return prices


def _sma_series(xs, n, m):
    """通达信 SMA(X,N,M) 参考实现。"""
    prev = sum(xs[:n]) / n
    out = []
    for x in xs:
        prev = (x * m + prev * (n - m)) / n
        out.append(prev)
    return out


def _ema_series(xs, n):
    return _sma_series(xs, n + 1, 2)


class TestSMASeedSeries:
    """SMA 种子递推：前 N 项均值做种子，而非首元素。"""

    def test_length_matches_input(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert len(ti.calculate_sma_seed_series(xs, 3, 1)) == 5

    def test_seed_is_mean_of_first_n(self):
        xs = [2.0, 4.0, 6.0, 8.0]
        # n=3, m=1: 种子=4, 之后 Y=(X*1+Y'*2)/3
        out = ti.calculate_sma_seed_series(xs, 3, 1)
        assert out[0] == pytest.approx((2.0 * 1 + 4.0 * 2) / 3)
        assert out[1] == pytest.approx((4.0 * 1 + out[0] * 2) / 3)

    def test_insufficient_length_returns_empty(self):
        assert ti.calculate_sma_seed_series([1.0, 2.0], 5, 1) == []

    def test_non_positive_n_returns_empty(self):
        assert ti.calculate_sma_seed_series([1.0, 2.0, 3.0], 0, 1) == []


class TestEMASeries:
    """EMA 等价 SMA(X,N+1,2)。"""

    def test_matches_reference(self):
        xs = _synth(60)
        assert ti.calculate_ema_series(xs, 12)[-1] == pytest.approx(_ema_series(xs, 12)[-1])

    def test_ema_of_constant_is_constant(self):
        out = ti.calculate_ema_series([5.0] * 40, 10)
        assert all(v == pytest.approx(5.0) for v in out)

    def test_insufficient_length_returns_empty(self):
        assert ti.calculate_ema_series([1.0, 2.0], 10) == []


class TestMACD:
    """MACD：DEA 必须是 DIFF 序列的 EMA，不是 DIFF 的复制。"""

    def test_dea_differs_from_dif(self):
        """回归锁：旧版 dea=EMA([dif]*9,9) 使 DEA≡DIF、柱恒为 0。"""
        dif, dea, hist = ti.calculate_macd(_synth())
        assert dif != dea
        assert hist != 0

    def test_hist_is_twice_dif_minus_dea(self):
        dif, dea, hist = ti.calculate_macd(_synth())
        assert hist == pytest.approx(2 * (dif - dea), abs=1e-3)

    def test_matches_reference_formula(self):
        prices = _synth()
        ef = _ema_series(prices, 12)
        es = _ema_series(prices, 26)
        n = min(len(ef), len(es))
        dif_s = [ef[i] - es[i] for i in range(n)]
        dea_s = _ema_series(dif_s, 9)
        off = len(dif_s) - len(dea_s)
        exp = (round(dif_s[off + len(dea_s) - 1], 4),
               round(dea_s[-1], 4),
               round(2 * (dif_s[off + len(dea_s) - 1] - dea_s[-1]), 4))
        assert ti.calculate_macd(prices) == exp

    def test_insufficient_data_returns_none(self):
        assert ti.calculate_macd([1.0] * 20) == (None, None, None)

    def test_series_length_matches_input(self):
        prices = _synth()
        assert len(ti.calculate_macd_series(prices)) == len(prices)


class TestRSI:
    """RSI：Wilder 平滑（SMA(...,N,1)），不是算术平均。"""

    def test_flat_series_is_neutral(self):
        assert ti.calculate_rsi([10.0] * 40) == 50.0

    def test_monotonic_up_is_100(self):
        up = [10.0 + i * 0.1 for i in range(40)]
        assert ti.calculate_rsi(up) == 100.0

    def test_monotonic_down_is_zero(self):
        down = [50.0 - i * 0.1 for i in range(40)]
        assert ti.calculate_rsi(down) == 0.0

    def test_matches_reference_formula(self):
        prices = _synth()
        diffs = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        g = [d if d > 0 else 0.0 for d in diffs]
        l = [-d if d < 0 else 0.0 for d in diffs]
        ag = _sma_series(g, 14, 1)[-1]
        al = _sma_series(l, 14, 1)[-1]
        exp = 100.0 if al == 0 else round(100 - 100 / (1 + ag / al), 2)
        assert ti.calculate_rsi(prices) == exp

    def test_insufficient_data_returns_none(self):
        assert ti.calculate_rsi([1.0] * 10) is None

    def test_bounded_0_100(self):
        for n in (20, 40, 60, 120):
            r = ti.calculate_rsi(_synth(n), 14)
            if r is not None:
                assert 0 <= r <= 100


class TestKDJ:
    """KDJ：K/D 对全序列 SMA(...,1) 递推，不是只递推最后 3 个 RSV。"""

    def test_matches_reference_formula(self):
        prices = _synth()
        highs = [p + 0.5 for p in prices]
        lows = [p - 0.5 for p in prices]
        rsvs = []
        for i in range(8, len(prices)):
            lo = min(lows[i - 8:i + 1])
            hi = max(highs[i - 8:i + 1])
            rsvs.append(50.0 if hi == lo else (prices[i] - lo) / (hi - lo) * 100)
        ks = _sma_series(rsvs, 3, 1)
        ds = _sma_series(ks, 3, 1)
        off = len(ks) - len(ds)
        k, d = ks[off + len(ds) - 1], ds[-1]
        exp = (round(k, 2), round(d, 2), round(3 * k - 2 * d, 2))
        assert ti.calculate_kdj(highs, lows, prices) == exp

    def test_j_is_3k_minus_2d(self):
        prices = _synth()
        highs = [p + 0.5 for p in prices]
        lows = [p - 0.5 for p in prices]
        k, d, j = ti.calculate_kdj(highs, lows, prices)
        assert j == pytest.approx(3 * k - 2 * d, abs=0.02)

    def test_insufficient_data_returns_none(self):
        assert ti.calculate_kdj([11.0] * 5, [9.0] * 5, [10.0] * 5) == (None, None, None)

    def test_series_length(self):
        prices = _synth()
        highs = [p + 0.5 for p in prices]
        lows = [p - 0.5 for p in prices]
        assert len(ti.calculate_kdj_series(highs, lows, prices)) == len(prices) - 8

    def test_flat_market_rsv_is_50(self):
        n = 30
        assert ti.calculate_kdj([10.0] * n, [10.0] * n, [10.0] * n)[0] == pytest.approx(50.0)


class TestBollingerUnchanged:
    """布林带口径本就与通达信一致（MID±2*STD），锁定不回归。"""

    def test_matches_reference(self):
        prices = _synth()
        recent = prices[-20:]
        ma = sum(recent) / 20
        std = (sum((p - ma) ** 2 for p in recent) / 20) ** 0.5
        assert ti.calculate_bollinger(prices) == (
            round(ma + 2 * std, 4), round(ma, 4), round(ma - 2 * std, 4))

    def test_insufficient_data_returns_none(self):
        assert ti.calculate_bollinger([1.0] * 10) == (None, None, None)

