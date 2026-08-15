"""
stock-crewai 测试套件 - 技术指标扩展
运行: pytest tests/test_indicators.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class TestTechnicalIndicators:
    """测试技术指标模块"""
    
    def test_calculate_rsi_overbought(self):
        """测试RSI超买"""
        from technical_indicators import calculate_rsi
        # 持续上涨的价格
        prices = [10 + i * 0.5 for i in range(20)]
        rsi = calculate_rsi(prices)
        assert rsi is not None
        assert 70 <= rsi <= 100  # 持续上涨应该超买
    
    def test_calculate_rsi_oversold(self):
        """测试RSI超卖"""
        from technical_indicators import calculate_rsi
        # 持续下跌的价格
        prices = [20 - i * 0.5 for i in range(20)]
        rsi = calculate_rsi(prices)
        assert rsi is not None
        assert 0 <= rsi <= 30  # 持续下跌应该超卖
    
    def test_calculate_rsi_insufficient_data(self):
        """测试RSI数据不足"""
        from technical_indicators import calculate_rsi
        prices = [10, 11, 12]  # 数据不足14天
        rsi = calculate_rsi(prices)
        assert rsi is None  # 应该返回None
    
    def test_calculate_bollinger(self):
        """测试布林带计算"""
        from technical_indicators import calculate_bollinger
        prices = [10 + (i % 3) * 0.5 for i in range(25)]
        upper, middle, lower = calculate_bollinger(prices)
        assert upper is not None
        assert middle is not None
        assert lower is not None
        assert upper > middle > lower  # 上轨 > 中轨 > 下轨
    
    def test_calculate_bollinger_insufficient_data(self):
        """测试布林带数据不足"""
        from technical_indicators import calculate_bollinger
        prices = [10, 11, 12]  # 数据不足20天
        result = calculate_bollinger(prices)
        assert all(v is None for v in result)
    
    def test_calculate_kdj(self):
        """测试KDJ计算"""
        from technical_indicators import calculate_kdj
        # 构造测试数据
        highs = [10 + i * 0.2 for i in range(20)]
        lows = [9 + i * 0.15 for i in range(20)]
        closes = [9.5 + i * 0.18 for i in range(20)]
        k, d, j = calculate_kdj(highs, lows, closes)
        assert k is not None
        assert d is not None
        assert j is not None
        assert 0 <= k <= 100
        assert 0 <= d <= 100
    
    def test_calculate_atr(self):
        """测试ATR计算"""
        from technical_indicators import calculate_atr
        # 构造测试数据
        highs = [10 + i * 0.2 for i in range(20)]
        lows = [9 + i * 0.15 for i in range(20)]
        closes = [9.5 + i * 0.18 for i in range(20)]
        atr = calculate_atr(highs, lows, closes)
        assert atr is not None
        assert atr > 0
    
    def test_calculate_ma(self):
        """测试移动平均线"""
        from technical_indicators import calculate_ma
        prices = [10 + i * 0.1 for i in range(25)]
        ma5 = calculate_ma(prices, 5)
        ma20 = calculate_ma(prices, 20)
        assert ma5 is not None
        assert ma20 is not None
        assert ma5 > ma20  # 短期均线 > 长期均线（上涨趋势）
    
    def test_calculate_ma_insufficient_data(self):
        """测试均线数据不足"""
        from technical_indicators import calculate_ma
        prices = [10, 11, 12]
        ma10 = calculate_ma(prices, 10)
        assert ma10 is None


class TestDataFetcherEnhancements:
    """测试 data_fetcher 增强功能"""
    
    def test_batch_prices_empty(self):
        """测试批量获取空列表"""
        from data_fetcher import get_batch_stock_prices
        result = get_batch_stock_prices([])
        assert result == {}
    
    def test_realtime_quotes_empty(self):
        """测试实时行情空列表"""
        from data_fetcher import get_realtime_quotes
        result = get_realtime_quotes([])
        assert result == []
    
    def test_sina_realtime_empty(self):
        """测试新浪实时行情空列表"""
        from data_fetcher import get_sina_realtime
        result = get_sina_realtime([])
        assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])