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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
