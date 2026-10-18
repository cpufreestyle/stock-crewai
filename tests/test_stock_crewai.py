"""
stock-crewai 测试套件
运行: pytest tests/ -v
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfig:
    """测试配置模块"""
    
    def test_config_imports(self):
        from config import (
            MAX_POSITIONS, MAX_POSITION_RATIO, SINGLE_POSITION_RATIO,
            STOP_LOSS_RATIO, TAKE_PROFIT_RATIO, MAX_CHANGE_PCT,
        )
        assert MAX_POSITIONS > 0
        assert 0 < MAX_POSITION_RATIO <= 1
        assert 0 < SINGLE_POSITION_RATIO <= 1
        assert 0 < STOP_LOSS_RATIO < 1
        assert TAKE_PROFIT_RATIO > 1
    
    def test_stop_loss_is_loss(self):
        from config import STOP_LOSS_RATIO
        assert STOP_LOSS_RATIO < 1.0  # 止损线应低于买入价
    
    def test_take_profit_is_profit(self):
        from config import TAKE_PROFIT_RATIO
        assert TAKE_PROFIT_RATIO > 1.0  # 止盈线应高于买入价
    
    def test_position_limits(self):
        from config import SINGLE_POSITION_RATIO, MAX_POSITION_RATIO
        assert SINGLE_POSITION_RATIO <= MAX_POSITION_RATIO  # 单股不超过总仓位


class TestAPICache:
    """测试 API 缓存模块"""
    
    def test_cache_set_get(self):
        from api_cache import TTLCache
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_cache_miss(self):
        from api_cache import TTLCache
        cache = TTLCache(default_ttl=60)
        assert cache.get("nonexistent") is None
    
    def test_cache_expiry(self):
        from api_cache import TTLCache
        cache = TTLCache(default_ttl=1)
        cache.set("key1", "value1", ttl=1)
        time.sleep(1.5)
        assert cache.get("key1") is None
    
    def test_cache_clear(self):
        from api_cache import TTLCache
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        cache.clear()
        assert cache.get("key1") is None
    
    def test_cache_stats(self):
        from api_cache import TTLCache
        cache = TTLCache(default_ttl=60)
        cache.set("key1", "value1")
        stats = cache.stats()
        assert stats["total"] == 1
        assert stats["valid"] == 1
    
    def test_cached_decorator(self):
        from api_cache import cached, api_cache
        
        call_count = 0
        
        @cached(ttl=60, cache_instance=api_cache)
        def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        result1 = expensive_func(5)
        result2 = expensive_func(5)
        assert result1 == 10
        assert result2 == 10
        assert call_count == 1  # 只调用一次，第二次命中缓存


class TestDataFetcher:
    """测试数据获取模块"""
    
    def test_get_sina_prefix(self):
        """测试股票代码前缀识别"""
        from data_fetcher import get_realtime_quotes
        # 基本导入测试
        assert callable(get_realtime_quotes)
    
    def test_get_simple_market_regime(self):
        """测试市场状态获取"""
        from data_fetcher import get_simple_market_regime
        result = get_simple_market_regime()
        assert isinstance(result, str)
        assert result in ["牛市", "熊市", "震荡市"]


class TestPortfolioTracker:
    """测试持仓管理模块"""
    
    def test_portfolio_load(self):
        """测试持仓文件加载"""
        import portfolio_tracker as pt
        portfolio = pt.load_portfolio()
        assert isinstance(portfolio, dict)
        assert "cash" in portfolio
        assert "positions" in portfolio
    
    def test_portfolio_summary(self):
        """测试持仓摘要"""
        import portfolio_tracker as pt
        summary = pt.get_portfolio_summary()
        assert isinstance(summary, str)

    def test_buy_and_sell_both_recorded(self):
        """买入和卖出都必须记入交易流水账（run6 回归）"""
        import shutil as _shutil
        import tempfile

        import portfolio_tracker as pt

        tmp = tempfile.mkdtemp()
        orig_file, orig_dir = pt.PORTFOLIO_FILE, pt.HISTORY_DIR
        try:
            pt.PORTFOLIO_FILE = os.path.join(tmp, "portfolio.json")
            pt.HISTORY_DIR = os.path.join(tmp, "history")
            pt.save_portfolio({"positions": {}, "cash": 100000,
                               "total_capital": 100000, "created": "2026-01-01T00:00:00"})

            r1 = pt.update_position("000001", "测试股", "buy", 10.0, 100, reason="t-buy")
            assert "error" not in r1
            r2 = pt.update_position("000001", "测试股", "sell", 12.0, 100, reason="t-sell")
            assert "error" not in r2

            trades = pt.get_trade_history()
            assert [t["action"] for t in trades] == ["buy", "sell"]
            assert trades[0]["pnl"] == 0.0
            assert round(trades[1]["pnl"], 2) == 200.0
        finally:
            pt.PORTFOLIO_FILE, pt.HISTORY_DIR = orig_file, orig_dir
            _shutil.rmtree(tmp, ignore_errors=True)

    def test_last_price_fallback_chain(self):
        """无外部报价时：current_prices > last_price > avg_cost"""
        import portfolio_tracker as pt
        assert pt._position_last_price({"avg_cost": 10.0, "last_price": 9.5}) == 9.5
        assert pt._position_last_price({"avg_cost": 10.0, "last_price": 0}) == 10.0
        assert pt._position_last_price({"avg_cost": 10.0}) == 10.0


class TestBrokerTrader:
    """测试交易接口模块"""
    
    def test_create_mock_trader(self):
        """测试 MockTrader 创建"""
        from broker_trader import create_trader
        trader = create_trader(mode="mock")
        assert trader is not None
    
    def test_mock_trader_balance(self):
        """测试 MockTrader 余额查询"""
        from broker_trader import create_trader
        trader = create_trader(mode="mock")
        balance = trader.get_balance()
        # balance 可能是 dict 或 number
        if isinstance(balance, dict):
            assert "total_asset" in balance or "available_cash" in balance
        else:
            assert isinstance(balance, (int, float))
            assert balance > 0


class TestNetValueHistory:
    """测试净值历史记录"""
    
    def test_config_has_file_path(self):
        from config import NET_VALUE_HISTORY_FILE
        assert NET_VALUE_HISTORY_FILE is not None
        assert isinstance(NET_VALUE_HISTORY_FILE, str)


class TestAgentToolWhitelist:
    """分析流水线不得携带下单类工具

    execute_buy / execute_sell / set_stop_loss 会真改 portfolio.json 与
    history/trades_YYYYMM.json。让 LLM 在"出日报"的过程中自己决定下不下单，
    等于每跑一次分析就改一次持仓（run6 实测有 4 次 execute_sell）。
    下单只应存在于 run_virtual_v4.py 那条独立的模拟盘路径。
    """

    WRITE_TOOLS = {"execute_buy", "execute_sell", "set_stop_loss"}

    @pytest.fixture(scope="class")
    def built_agents(self):
        # get_llm() 在 key 缺失时返回 None 并让 create_crewai_agent 抛错；
        # 这里只需要装配期的工具白名单，塞假值即可，不会发起任何网络请求。
        # class 级：装一次 7 个 agent 要几十秒，别每个用例重建。
        mp = pytest.MonkeyPatch()
        mp.setenv("OPENAI_API_KEY", "test-key")
        mp.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1/v1")
        mp.setenv("MODEL_NAME", "test-model")
        try:
            import crew
            return crew.build_agents()
        finally:
            mp.undo()

    def test_no_write_tools(self, built_agents):
        leaks = {
            name: self.WRITE_TOOLS & {t.name for t in agent.tools}
            for name, agent in built_agents.items()
        }
        leaks = {k: v for k, v in leaks.items() if v}
        assert not leaks, f"分析流水线携带了下单类工具: {leaks}"

    def test_all_seven_agents_built(self, built_agents):
        assert set(built_agents) == {
            "market_watcher", "researcher", "risk_mgr", "trader",
            "sentiment_analyst", "backtest_validator", "rebalancer",
        }

    def test_trader_can_size_positions(self, built_agents):
        # 交易任务提示词要求用 position_size 定股数；工具缺席时模型只能凭空编。
        names = {t.name for t in built_agents["trader"].tools}
        assert "position_size" in names
        assert "view_portfolio" in names


class TestAgentTradingGate:
    """下单类工具总开关：默认拒绝，ALLOW_AGENT_TRADING=1 才放行

    crew.py 已在工具白名单层面剔除这三个工具，但 workflows/daily_analysis.py 走
    AgentBase.run() 旧编排路径，agents/*.py 的 self.tools 仍含 get_trade_tools()。
    手动跑 main.py 或点 web_dashboard 一样会真下单，所以工具入口再兜一道。
    """

    @pytest.fixture
    def tmp_portfolio(self):
        import shutil as _shutil
        import tempfile

        import portfolio_tracker as pt

        tmp = tempfile.mkdtemp()
        orig_file, orig_dir = pt.PORTFOLIO_FILE, pt.HISTORY_DIR
        pt.PORTFOLIO_FILE = os.path.join(tmp, "portfolio.json")
        pt.HISTORY_DIR = os.path.join(tmp, "history")
        pt.save_portfolio({"positions": {}, "cash": 100000,
                           "total_capital": 100000, "created": "2026-01-01T00:00:00"})
        try:
            yield pt
        finally:
            pt.PORTFOLIO_FILE, pt.HISTORY_DIR = orig_file, orig_dir
            _shutil.rmtree(tmp, ignore_errors=True)

    def test_truthy_parsing(self, monkeypatch):
        from tools.trade_tools import trading_allowed
        for val, expected in [("1", True), ("true", True), ("YES", True), (" on ", True),
                              ("0", False), ("false", False), ("", False), ("2", False)]:
            monkeypatch.setenv("ALLOW_AGENT_TRADING", val)
            assert trading_allowed() is expected, val
        monkeypatch.delenv("ALLOW_AGENT_TRADING", raising=False)
        assert trading_allowed() is False

    def test_default_denies_all_three(self, monkeypatch, tmp_portfolio):
        monkeypatch.delenv("ALLOW_AGENT_TRADING", raising=False)
        from tools.trade_tools import ExecuteBuyTool, ExecuteSellTool, SetStopLossTool

        calls = [
            (ExecuteBuyTool(), {"code": "000001", "name": "测试股", "price": 10.0, "shares": 100}),
            (ExecuteSellTool(), {"code": "000001", "price": 10.0, "shares": 100}),
            (SetStopLossTool(), {"code": "000001", "stop_loss": 9.0, "take_profit": 12.0}),
        ]
        for tool, kwargs in calls:
            r = json.loads(tool._run(**kwargs))
            assert r["success"] is False, tool.name
            assert r["advice_only"] is True, tool.name

        # 拒绝必须是真拒绝：持仓与现金一个字都不能动
        p = tmp_portfolio.load_portfolio()
        assert p["positions"] == {}
        assert p["cash"] == 100000

    def test_gate_open_allows_buy(self, monkeypatch, tmp_portfolio):
        monkeypatch.setenv("ALLOW_AGENT_TRADING", "1")
        from tools.trade_tools import ExecuteBuyTool

        r = json.loads(ExecuteBuyTool()._run(
            code="000001", name="测试股", price=10.0, shares=100, reason="gate-test"))
        assert r["success"] is True
        p = tmp_portfolio.load_portfolio()
        assert p["positions"]["000001"]["shares"] == 100
        assert p["cash"] == 99000

    def test_descriptions_advertise_the_gate(self):
        from tools.trade_tools import ExecuteBuyTool, ExecuteSellTool, SetStopLossTool
        for tool in (ExecuteBuyTool(), ExecuteSellTool(), SetStopLossTool()):
            assert "ALLOW_AGENT_TRADING" in tool.description, tool.name

    def test_legacy_orchestrator_path_cannot_trade(self, monkeypatch, tmp_portfolio):
        """旧编排路径（AgentBase.run）整条跑一遍也不许动持仓

        crew.py 走的是 create_crewai_agent，工具白名单已经剔掉写工具；但
        workflows/daily_analysis.py + core/scheduler.py + web_dashboard.py 走的是
        agents/*.py 里 self.tools = get_trade_tools()+... 这条老路，只能靠工具入口的
        总开关拦。这里直接调 run()，覆盖 trader 的 execute_buy/set_stop_loss 与
        rebalancer 的 execute_sell。
        """
        monkeypatch.delenv("ALLOW_AGENT_TRADING", raising=False)

        tmp_portfolio.save_portfolio({
            "positions": {"000425": {"name": "测试持仓", "shares": 600, "avg_cost": 8.0,
                                     "last_price": 7.0, "stop_loss": 0, "take_profit": 0}},
            "cash": 50000, "total_capital": 100000, "created": "2026-01-01T00:00:00",
        })

        class _State:
            def get_market_state(self):
                return {"regime": "熊市", "should_trade": True, "position_pct": 50}

            def get_trade_plan(self):
                return {}

            def get_stock_picks(self):
                return []

            def get_risk_assessment(self):
                # 深度亏损的持仓 + 一个风控已通过的买入候选，两边都够到写工具的触发条件
                return {"passed_picks": [{"code": "000001", "name": "测试买入", "price": 11.0,
                                          "shares": 100, "stop_loss": 10.0, "take_profit": 13.0,
                                          "score": 80, "rationale": "t"}]}

            def set_rebalance_plan(self, data):
                self.plan = data

            def set_trade_plan(self, data):
                self.trade_plan = data

        from agents.trader import TraderAgent
        from agents.portfolio_rebalancer import PortfolioRebalancerAgent

        trader_out = TraderAgent().run({}, _State())
        assert trader_out.success is True
        rebalancer_out = PortfolioRebalancerAgent().run({}, _State())
        assert rebalancer_out.success is True

        p = tmp_portfolio.load_portfolio()
        assert p["cash"] == 50000
        assert set(p["positions"]) == {"000425"}
        assert p["positions"]["000425"]["shares"] == 600
        assert p["positions"]["000425"]["avg_cost"] == 8.0
        assert tmp_portfolio.get_trade_history() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
class TestPinReachesCandidateText:
    u"""插针必须进入给研究员的后选文本，而不是只算出来无人问。"""

    def _tech(self, pin_text):
        return {
            '收盘价': 10.5,
            'MA5': 10.4, 'MA20': 10.2, 'RSI': 55,
            '5日涨跌%': 1.2,
            '插针': pin_text,
        }

    def _lines(self, tech):
        import pandas as pd
        import crew
        pool = ['000001']
        frame = pd.DataFrame({'收盘': [10.0] * 30})
        prices = {'000001': frame}
        with patch.object(crew.df, 'calculate_technical', return_value=tech):
            return crew._candidate_lines(pool, prices, {})

    def test_pin_text_appears_in_candidate_line(self):
        lines = self._lines(self._tech('锤子线'))
        assert any('插针=' in l for l in lines), lines

    def test_absent_pin_is_spelled_out(self):
        u"""没提到插针时也要写“无”，否则模型会自己编一个。"""
        lines = self._lines({})
        assert any('插针=无' in l for l in lines), lines

    def test_calculate_technical_emits_the_field(self):
        u"""上游硬件：计算出来的结果里必须有这个键。"""
        import pandas as pd
        from data_sources.technical import calculate_technical
        n = 25
        closes = [10.0 + (i % 5) * 0.01 for i in range(n)]
        df = pd.DataFrame({
            '日期': ['2026-03-%02d' % (i + 1) for i in range(n)],
            '收盘': closes,
            '开盘': [c - 0.02 for c in closes],
            '最高': [c + 0.05 for c in closes],
            '最低': [c - 0.9 for c in closes],
        })
        assert '插针' in calculate_technical(df)
