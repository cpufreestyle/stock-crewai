# -*- coding: utf-8 -*-
"""execute_buy / execute_sell 的下单路径测试

这两个函数直接调 portfolio_tracker 改动持仓，是下单路径的执行端。
用 monkeypatch 把 pt.update_position / set_stop_loss / notify 全部换成假实现，
在 tmp_path 里跑，不碰真实 portfolio.json。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import run_virtual_v4 as rv


@pytest.fixture
def fake_pt(monkeypatch):
    m = MagicMock()
    m.update_position.return_value = {"success": True}
    monkeypatch.setattr(rv, "pt", m)
    return m


@pytest.fixture
def fake_ti(monkeypatch):
    """关掉技术指标，走固定比例止损，行为确定"""
    monkeypatch.setattr(rv, "TECH_AVAILABLE", False)


def _cand(code, price, shares=100, score=5, position_value=1000.0, change_pct=2.0):
    return {"code": code, "name": "X" + code, "price": price, "shares": shares,
            "tech_score": score, "position_value": position_value,
            "change_pct": change_pct}


class TestExecuteBuy:
    def test_buys_when_cash_sufficient(self, fake_pt, fake_ti):
        cands = [_cand("000001", 10.0, shares=100, position_value=1000.0)]
        out = rv.execute_buy(cands, {}, cash=100000.0, total_capital=100000.0,
                            realtime_data={"000001": {"current": 10.0}})
        assert len(out) == 1
        assert out[0]["code"] == "000001"
        assert out[0]["shares"] == 100
        # 固定比例止损止盈：10 * 0.92 / 10 * 1.20
        assert out[0]["stop_loss"] == 9.2
        assert out[0]["take_profit"] == 12.0
        fake_pt.update_position.assert_called_once()
        fake_pt.set_stop_loss.assert_called_once()

    def test_skips_when_cash_insufficient(self, fake_pt, fake_ti):
        cands = [_cand("000001", 10.0, position_value=5000.0)]
        out = rv.execute_buy(cands, {}, cash=1000.0, total_capital=100000.0,
                            realtime_data={"000001": {"current": 10.0}})
        assert out == []
        fake_pt.update_position.assert_not_called()

    def test_respects_max_positions(self, fake_pt, fake_ti, monkeypatch):
        monkeypatch.setattr(rv, "MAX_POSITIONS", 2)
        existing = {
            "A": {"name": "a", "shares": 10, "avg_cost": 1.0},
            "B": {"name": "b", "shares": 10, "avg_cost": 1.0},
        }
        cands = [_cand("000001", 10.0, position_value=100.0)]
        out = rv.execute_buy(cands, existing, cash=100000.0, total_capital=100000.0,
                            realtime_data={})
        assert out == []

    def test_skips_zero_price(self, fake_pt, fake_ti):
        cands = [_cand("000001", 0.0)]
        out = rv.execute_buy(cands, {}, cash=100000.0, total_capital=100000.0,
                            realtime_data={"000001": {"current": 0.0}})
        assert out == []

    def test_update_error_propagates_as_no_buy(self, fake_pt, fake_ti):
        """update_position 报错时不能记入 buys"""
        fake_pt.update_position.return_value = {"error": "资金不足"}
        cands = [_cand("000001", 10.0)]
        out = rv.execute_buy(cands, {}, cash=100000.0, total_capital=100000.0,
                            realtime_data={"000001": {"current": 10.0}})
        assert out == []

    def test_overweight_holdings_block_buy(self, fake_pt, fake_ti):
        existing = {"A": {"name": "a", "shares": 9000, "avg_cost": 10.0}}
        cands = [_cand("000001", 10.0, position_value=100.0)]
        out = rv.execute_buy(cands, existing, cash=100000.0, total_capital=100000.0,
                            realtime_data={})
        assert out == []

    def test_holdings_without_live_quote_still_count(self, fake_pt, fake_ti):
        existing = {"A": {"name": "a", "shares": 8000, "avg_cost": 10.0}}
        cands = [_cand("000001", 10.0, position_value=100.0)]
        out = rv.execute_buy(cands, existing, cash=100000.0, total_capital=100000.0,
                            realtime_data={})
        assert len(out) == 1


class TestExecuteSell:
    def _alert(self, code, price, action="STOP_LOSS", reason="触发止损"):
        return {"code": code, "name": "X" + code, "action": action,
                "price": price, "reason": reason}

    def test_sells_stop_loss(self, fake_pt, monkeypatch):
        monkeypatch.setattr(rv, "NOTIFIER_AVAILABLE", False)
        pos = {"000001": {"name": "平安", "shares": 300, "avg_cost": 11.0}}
        alerts = [self._alert("000001", 10.0)]
        out = rv.execute_sell(pos, alerts, {"000001": {"current": 10.0}})
        assert len(out) == 1
        assert out[0]["code"] == "000001"
        # pnl = (10 - 11) * 300 = -300
        assert out[0]["pnl"] == -300.0
        fake_pt.update_position.assert_called_once()

    def test_ignores_warning_action(self, fake_pt, monkeypatch):
        monkeypatch.setattr(rv, "NOTIFIER_AVAILABLE", False)
        pos = {"000001": {"name": "平安", "shares": 300, "avg_cost": 11.0}}
        alerts = [self._alert("000001", 10.0, action="WARNING")]
        out = rv.execute_sell(pos, alerts, {})
        assert out == []
        fake_pt.update_position.assert_not_called()

    def test_ignores_code_not_held(self, fake_pt, monkeypatch):
        monkeypatch.setattr(rv, "NOTIFIER_AVAILABLE", False)
        alerts = [self._alert("999999", 10.0)]
        assert rv.execute_sell({}, alerts, {}) == []

    def test_skips_zero_price(self, fake_pt, monkeypatch):
        monkeypatch.setattr(rv, "NOTIFIER_AVAILABLE", False)
        pos = {"000001": {"name": "平安", "shares": 300, "avg_cost": 11.0}}
        alerts = [self._alert("000001", 0.0)]
        assert rv.execute_sell(pos, alerts, {}) == []


