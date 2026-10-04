# -*- coding: utf-8 -*-
"""broker_trader.MockTrader 的只读路径测试

MockTrader 是下单路径的兜底实现，直接读写 portfolio.json。
这里只测 get_balance / get_positions 的纯读逻辑（用 tmp_path，不碰真实持仓）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from broker_trader import MockTrader


@pytest.fixture
def portfolio_file(tmp_path, monkeypatch):
    p = tmp_path / "portfolio.json"
    monkeypatch.chdir(tmp_path)
    return p


class TestGetBalance:
    def test_missing_portfolio_returns_default_cash(self, portfolio_file):
        """没有 portfolio.json 时给默认 10 万，不能崩"""
        b = MockTrader(str(portfolio_file)).get_balance()
        assert b == {"total_asset": 100000, "available_cash": 100000, "market_value": 0}

    def test_reads_cash_and_total_value(self, portfolio_file):
        portfolio_file.write_text(json.dumps(
            {"cash": 47705.0, "total_value": 52310.0, "positions": {}}),
            encoding="utf-8")
        b = MockTrader(str(portfolio_file)).get_balance()
        assert b["available_cash"] == 47705.0
        assert b["total_asset"] == 52310.0
        # 市值 = 总资产 - 现金
        assert b["market_value"] == pytest.approx(4605.0)

    def test_missing_cash_key_defaults_zero(self, portfolio_file):
        portfolio_file.write_text(json.dumps({"total_value": 100.0}), encoding="utf-8")
        b = MockTrader(str(portfolio_file)).get_balance()
        assert b["available_cash"] == 0
        assert b["market_value"] == pytest.approx(100.0)


class TestGetPositions:
    def test_missing_portfolio_returns_empty(self, portfolio_file):
        assert MockTrader(str(portfolio_file)).get_positions() == []

    def test_maps_fields_and_falls_back_to_avg_cost(self, portfolio_file):
        """缺 last_price 时用 avg_cost 兜底，不能 KeyError"""
        portfolio_file.write_text(json.dumps({
            "positions": {
                "000001": {"name": "平安银行", "shares": 3200, "avg_cost": 11.38},
                "000858": {"name": "五粮液", "shares": 300, "avg_cost": 69.67,
                           "last_price": 70.5},
            }}), encoding="utf-8")
        pos = MockTrader(str(portfolio_file)).get_positions()
        assert {p["code"]: p for p in pos}.keys() == {"000001", "000858"}
        a = next(p for p in pos if p["code"] == "000001")
        b = next(p for p in pos if p["code"] == "000858")
        assert (a["shares"], a["avg_cost"], a["current_price"]) == (3200, 11.38, 11.38)
        assert b["current_price"] == 70.5

    def test_empty_positions_dict(self, portfolio_file):
        portfolio_file.write_text(json.dumps({"positions": {}}), encoding="utf-8")
        assert MockTrader(str(portfolio_file)).get_positions() == []

