"""
风控/熔断/回测模块测试套件
运行: pytest tests/test_risk_modules.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

import risk_manager as rm
from backtest import calculate_max_drawdown, calculate_sharpe


# ============ risk_manager ============

class TestKellyCriterion:
    def test_positive_edge(self):
        # 胜率60%，盈亏比1.5 → kelly = (1.5*0.6 - 0.4)/1.5 = 0.333 → 截断到 0.25
        assert rm.kelly_criterion(0.6, 0.15, 0.10) == 0.25

    def test_partial_position(self):
        # 胜率55%，盈亏比1.0 → kelly = (1.0*0.55 - 0.45)/1.0 = 0.10
        assert rm.kelly_criterion(0.55, 0.10, 0.10) == pytest.approx(0.10)

    def test_no_edge_zero_position(self):
        # 胜率40%，盈亏比1.0 → kelly = (0.4-0.6)/1 < 0 → 0
        assert rm.kelly_criterion(0.4, 0.10, 0.10) == 0

    def test_zero_avg_loss(self):
        assert rm.kelly_criterion(0.6, 0.15, 0.0) == 0


class TestPositionSize:
    def test_basic_sizing(self):
        # 10万资金，2%风险=2000元；股价12.5、止损10% → 每股风险1.25 → 1600股
        r = rm.position_size(100000, 12.5, stop_loss_pct=0.10, risk_per_trade=0.02)
        assert r["shares"] == 1600
        assert r["shares"] % 100 == 0
        assert r["risk_amount"] == 2000
        assert r["stop_loss_price"] == pytest.approx(11.25)
        assert r["position_pct"] == pytest.approx(20.0)

    def test_high_volatility_reduces_position(self):
        low_vol = rm.position_size(100000, 12.5, 0.10, 0.02, volatility=0.02)
        high_vol = rm.position_size(100000, 12.5, 0.10, 0.02, volatility=0.06)
        assert high_vol["shares"] < low_vol["shares"]

    def test_min_lot_floor(self):
        # 极小资金 → 不足一手 → 0股
        r = rm.position_size(1000, 500.0, 0.10, 0.02)
        assert r["shares"] == 0


class TestPortfolioRisk:
    def test_empty_portfolio(self):
        r = rm.calculate_portfolio_risk([], 100000)
        assert r["total_risk_pct"] == 0
        assert r["var_95"] == 0

    def test_with_positions(self):
        positions = [
            {"code": "000001", "shares": 1000, "avg_cost": 12.5, "stop_loss": 11.25},
            {"code": "600519", "shares": 100, "avg_cost": 1700.0, "stop_loss": 1564.0},
        ]
        r = rm.calculate_portfolio_risk(positions, 300000)
        assert r["positions_count"] == 2
        assert r["total_exposure"] == pytest.approx(1000 * 12.5 + 100 * 1700)
        assert r["estimated_var_1day"] > 0


class TestRiskRewardRatio:
    def test_valid_rr(self):
        r = rm.risk_reward_ratio(entry=12.5, target=15.0, stop=11.5)
        assert r["risk"] == 1.0
        assert r["reward"] == 2.5
        assert r["risk_reward_ratio"] == 2.5
        assert r["is_valid"] is True

    def test_invalid_rr(self):
        r = rm.risk_reward_ratio(entry=12.5, target=13.0, stop=11.5)
        assert r["risk_reward_ratio"] == 0.5
        assert r["is_valid"] is False

    def test_zero_risk(self):
        r = rm.risk_reward_ratio(entry=12.5, target=15.0, stop=12.5)
        assert r["risk_reward_ratio"] == 0
        assert r["is_valid"] is False


class TestRecommendedStopLoss:
    def test_strategies_ordered(self):
        cons = rm.recommended_stop_loss(100, "conservative")
        mod = rm.recommended_stop_loss(100, "moderate")
        aggr = rm.recommended_stop_loss(100, "aggressive")
        assert cons["stop_loss_pct"] < mod["stop_loss_pct"] < aggr["stop_loss_pct"]

    def test_volatility_raises_stop(self):
        base = rm.recommended_stop_loss(100, "conservative")
        with_vol = rm.recommended_stop_loss(100, "conservative", recent_volatility=0.05)
        assert with_vol["stop_loss_pct"] > base["stop_loss_pct"]


# ============ backtest 指标 ============

class TestMaxDrawdown:
    def test_no_drawdown_monotonic_up(self):
        assert calculate_max_drawdown([100, 110, 120, 130]) == 0.0

    def test_simple_drawdown(self):
        # 100→200 跌到 150 → 回撤 25%
        assert calculate_max_drawdown([100, 200, 150]) == pytest.approx(25.0)

    def test_known_sequence(self):
        # 峰值120，谷值90 → (120-90)/120 = 25%
        assert calculate_max_drawdown([100, 120, 90, 110]) == pytest.approx(25.0)

    def test_empty_or_short(self):
        assert calculate_max_drawdown([]) == 0.0
        assert calculate_max_drawdown([100]) == 0.0


class TestSharpe:
    def test_positive_sharpe(self):
        # 均值1.0、标准差>0 的正收益序列
        s = calculate_sharpe([0.5, 1.0, 1.5, 1.0])
        assert s > 0

    def test_zero_std(self):
        assert calculate_sharpe([1.0, 1.0, 1.0]) == 0.0

    def test_negative_returns_negative_sharpe(self):
        assert calculate_sharpe([-1.0, -2.0, -1.5, -2.5]) < 0

    def test_short_series(self):
        assert calculate_sharpe([]) == 0.0
        assert calculate_sharpe([1.0]) == 0.0


# ============ circuit_breaker 状态机 ============

@pytest.fixture
def breaker(tmp_path, monkeypatch):
    """每个测试用独立的熔断状态文件"""
    import circuit_breaker as cb
    state_file = tmp_path / "cb_state.json"
    monkeypatch.setattr(cb, "CIRCUIT_BREAKER_FILE", str(state_file))
    # CircuitBreaker.__init__ 引用的是模块内导入的常量，需 patch 到 config 源头
    monkeypatch.setattr("config.CIRCUIT_BREAKER_FILE", str(state_file))
    return cb.CircuitBreaker()


class TestCircuitBreaker:
    def test_starts_clear(self, breaker):
        assert not breaker.is_tripped()
        assert breaker.can_trade()

    def test_consecutive_stops_trip(self, breaker):
        breaker.record_trade(-8.0, 100000)
        breaker.record_trade(-9.0, 99000)
        assert not breaker.is_tripped()  # 2次未达阈值
        breaker.record_trade(-7.0, 98000)  # 第3次连续止损
        assert breaker.is_tripped()
        status = breaker.get_status()
        assert status["tripped"]
        assert status["consecutive_stops"] == 3
        assert "连续" in status["reason"]

    def test_win_resets_streak(self, breaker):
        breaker.record_trade(-8.0, 100000)
        breaker.record_trade(-8.0, 99000)
        breaker.record_trade(2.0, 98500)  # 盈利重置
        breaker.record_trade(-8.0, 98000)
        assert not breaker.is_tripped()  # 只有连续1次

    def test_daily_loss_trip(self, breaker):
        # 日初 10万，亏 6% > 5% 阈值
        breaker.record_trade(-3.0, 100000)  # 记录日初=100000
        breaker.record_trade(-3.5, 94000)   # 单日回撤 6%
        assert breaker.is_tripped()
        assert "单日" in breaker.get_status()["reason"]

    def test_daily_reset_new_day(self, breaker):
        from datetime import datetime, timedelta
        breaker.record_trade(-3.0, 100000)
        # 模拟昨天的日初记录
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        breaker._state["day_start_date"] = yesterday
        breaker._state["day_start_value"] = 200000
        # 新的一天：日初重置为当前值，无回撤
        breaker.record_trade(1.0, 100000)
        assert breaker._state["day_start_date"] == datetime.now().strftime("%Y-%m-%d")
        assert breaker._state["day_start_value"] == 100000
        assert not breaker.is_tripped()

    def test_cooldown_auto_release(self, breaker):
        from datetime import datetime, timedelta
        breaker._trip("测试")
        # 模拟熔断发生在冷却期之前
        breaker._state["tripped_at"] = (
            datetime.now() - timedelta(minutes=121)
        ).isoformat()
        breaker._save()
        assert not breaker.is_tripped()  # 冷却期已过自动解除
        assert breaker._state["consecutive_stops"] == 0

    def test_manual_reset(self, breaker):
        breaker._trip("测试")
        assert breaker.is_tripped()
        breaker.reset()
        assert not breaker.is_tripped()
        assert breaker.can_trade()

    def test_state_persisted_to_file(self, breaker):
        breaker.record_trade(-8.0, 100000)
        import circuit_breaker as cb
        assert Path(cb.CIRCUIT_BREAKER_FILE).exists()
