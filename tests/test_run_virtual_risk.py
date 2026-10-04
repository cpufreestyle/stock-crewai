# -*- coding: utf-8 -*-
"""run_virtual_v4 下单路径的撤单价计算测试

覆盖 check_portfolio_risk 的固定止损 / 止盈 / 预警三条分支与边界。
ATR 动态止损分支需要真实 K 线与网络，用 monkeypatch 关掉 TECH_AVAILABLE 走纯计算路径。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import run_virtual_v4 as rv


def _pos(avg_cost, stop_loss=0.0, name="平安银行", last_price=None, buy_date="2020-01-01"):
    p = {"name": name, "avg_cost": avg_cost, "stop_loss": stop_loss, "buy_date": buy_date}
    if last_price is not None:
        p["last_price"] = last_price
    return p


@pytest.fixture
def no_tech():
    """关掉 ATR 动态止损，只测固定止损线逻辑"""
    with patch.object(rv, "TECH_AVAILABLE", False):
        yield


class TestStopLoss:
    def test_triggers_at_exact_stop_line(self, no_tech):
        pos = {"000001": _pos(10.0, stop_loss=9.0)}
        rt = {"000001": {"current": 9.0}}
        alerts = rv.check_portfolio_risk(pos, rt)
        assert len(alerts) == 1
        assert alerts[0]["action"] == "STOP_LOSS"
        assert alerts[0]["price"] == 9.0

    def test_no_trigger_above_stop_line(self, no_tech):
        pos = {"000001": _pos(10.0, stop_loss=9.0)}
        rt = {"000001": {"current": 9.01}}
        assert rv.check_portfolio_risk(pos, rt) == []

    def test_zero_stop_line_never_triggers(self, no_tech):
        """stop_loss 未设置时必须永不触发（不能拿 0 当止损线）"""
        pos = {"000001": _pos(10.0, stop_loss=0.0)}
        rt = {"000001": {"current": 1.0}}
        assert rv.check_portfolio_risk(pos, rt) == []

    def test_falls_back_to_last_price_when_missing_in_quote(self, no_tech):
        """行情缺失时用持仓里的 last_price，不能 KeyError"""
        pos = {"000001": _pos(10.0, stop_loss=9.0, last_price=8.5)}
        alerts = rv.check_portfolio_risk(pos, {})
        assert len(alerts) == 1 and alerts[0]["action"] == "STOP_LOSS"
        assert alerts[0]["price"] == 8.5

    def test_falls_back_to_avg_cost_when_no_last_price(self, no_tech):
        pos = {"000001": _pos(10.0, stop_loss=9.0)}
        alerts = rv.check_portfolio_risk(pos, {})
        # current = avg_cost = 10 > stop 9 -> 不停损
        assert alerts == []

    def test_zero_price_skipped(self, no_tech):
        """停牌/价格为 0 的标的要跳过，不能除零"""
        pos = {"000001": _pos(10.0, stop_loss=9.0, last_price=0.0)}
        assert rv.check_portfolio_risk(pos, {}) == []


class TestTakeProfitAndWarning:
    def test_take_profit_at_20pct(self, no_tech):
        pos = {"000001": _pos(10.0)}
        rt = {"000001": {"current": 12.0}}
        alerts = rv.check_portfolio_risk(pos, rt)
        assert len(alerts) == 1
        assert alerts[0]["action"] == "TAKE_PROFIT"
        assert alerts[0]["pnl_pct"] == pytest.approx(20.0)

    def test_warning_band_between_15_and_20(self, no_tech):
        pos = {"000001": _pos(10.0)}
        rt = {"000001": {"current": 11.6}}
        alerts = rv.check_portfolio_risk(pos, rt)
        assert len(alerts) == 1
        assert alerts[0]["action"] == "WARNING"

    def test_no_alert_in_quiet_zone(self, no_tech):
        pos = {"000001": _pos(10.0)}
        rt = {"000001": {"current": 10.5}}
        assert rv.check_portfolio_risk(pos, rt) == []

    def test_stop_loss_takes_priority_over_profit(self, no_tech):
        """同时满足止损与止盈条件时只出一条（elif 链）"""
        # 止损线设得比现价高（11.5 > 11.0）才会同时命中两条分支；
        # 现价 11.0 相对成本 10.0 也是 +10%，本身不构成止盈，
        # 所以这里验证的是“止损线异常高时由止损分支先命中”。
        pos = {"000001": _pos(10.0, stop_loss=11.5)}
        rt = {"000001": {"current": 11.0}}
        alerts = rv.check_portfolio_risk(pos, rt)
        assert len(alerts) == 1 and alerts[0]["action"] == "STOP_LOSS"


class TestMultiPosition:
    def test_mixed_positions_independent(self, no_tech):
        pos = {
            "000001": _pos(10.0, stop_loss=9.0, name="A"),
            "000002": _pos(10.0, name="B"),
        }
        rt = {
            "000001": {"current": 8.5},   # 止损
            "000002": {"current": 12.0},  # 止盈
        }
        alerts = rv.check_portfolio_risk(pos, rt)
        actions = sorted(a["action"] for a in alerts)
        assert actions == ["STOP_LOSS", "TAKE_PROFIT"]

    def test_empty_portfolio(self, no_tech):
        assert rv.check_portfolio_risk({}, {}) == []

    def test_position_not_in_quote_data(self, no_tech):
        """行情里没有该标的 -> 用持仓兜底价，不崩"""
        pos = {"000001": _pos(10.0, stop_loss=9.0, last_price=11.0)}
        assert rv.check_portfolio_risk(pos, {"000002": {"current": 5.0}}) == []

