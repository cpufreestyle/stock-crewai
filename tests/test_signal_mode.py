"""
信号推送模式测试套件（format_signals_message 纯函数）
运行: pytest tests/test_signal_mode.py -v
"""
import sys
from pathlib import Path

import pytest

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from run_virtual_v4 import format_signals_message


def make_alert(action="STOP_LOSS", code="000001", name="平安银行", price=11.0, reason="触发止损线"):
    return {"action": action, "code": code, "name": name, "price": price, "reason": reason}


def make_candidate(code="600519", name="贵州茅台", price=1700.0, shares=100, tech_score=5):
    return {"code": code, "name": name, "price": price, "shares": shares,
            "tech_score": tech_score, "change_pct": 2.0, "volume": 500000,
            "position_value": price * shares}


class TestFormatSignalsMessage:
    def test_empty_returns_none(self):
        msg, count = format_signals_message([], [])
        assert msg is None
        assert count == 0

    def test_warning_only_not_pushed(self):
        # WARNING 不是可执行信号，不应触发推送
        msg, count = format_signals_message([make_alert(action="WARNING")], [])
        assert msg is None
        assert count == 0

    def test_stop_loss_signal(self):
        msg, count = format_signals_message([make_alert()], [])
        assert msg is not None
        assert count == 1
        assert "止损卖出" in msg
        assert "平安银行(000001)" in msg
        assert "11.00元" in msg

    def test_take_profit_signal(self):
        msg, count = format_signals_message([make_alert(action="TAKE_PROFIT", price=13.0, reason="触发止盈线")], [])
        assert "止盈卖出" in msg
        assert count == 1

    def test_buy_signal_with_stop_and_target(self):
        msg, count = format_signals_message([], [make_candidate()])
        assert msg is not None
        assert count == 1
        assert "建议买入" in msg
        assert "贵州茅台(600519)" in msg
        assert "100股 @ 1700.00元" in msg
        # STOP_LOSS_RATIO=0.92 → 1564.0；TAKE_PROFIT_RATIO=1.20 → 2040.0
        assert "止损1564.0" in msg
        assert "目标2040.0" in msg

    def test_buy_candidates_capped_at_3(self):
        cands = [make_candidate(code=f"60000{i}", name=f"股{i}") for i in range(5)]
        msg, count = format_signals_message([], cands)
        assert count == 3  # 只取前3

    def test_mixed_signals_count(self):
        alerts = [make_alert(), make_alert(action="TAKE_PROFIT", code="600519", name="贵州茅台")]
        cands = [make_candidate(), make_candidate(code="000333", name="美的集团")]
        msg, count = format_signals_message(alerts, cands)
        assert count == 4  # 2卖出 + 2买入

    def test_message_has_timestamp_footer(self):
        from datetime import datetime
        msg, _ = format_signals_message([make_alert()], [])
        assert "推送，请人工确认后执行" in msg
        assert datetime.now().strftime("%H:%M") in msg
