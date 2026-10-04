#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据获取模块 - 门面（facade）

实现按职责拆到 data_sources/ 包，本文件只做再导出，
保持 `from data_fetcher import X` / `import data_fetcher as df` 全部调用点不变。

拆分映射：
    data_sources/_common.py      代理绕过、akshare 懒加载、股票池、_sina_kline_direct
    data_sources/kline_prices.py get_index_components, get_stock_price, get_batch_stock_prices
    data_sources/fundamentals.py get_fundamental_batch, get_fundamental_data, get_news_sentiment
    data_sources/market.py       get_market_heat, get_market_regime, get_sector_performance
    data_sources/technical.py    calculate_technical
    data_sources/quotes.py       get_realtime_quotes, get_sina_realtime, get_simple_market_regime
"""
from data_sources._common import (
    A_SHARE_POOL,
    _STOCK_NAME,
    _sina_kline_direct,
    ak,
    # 代理补丁在导入 _common 时即生效
)
from data_sources.kline_prices import (
    get_index_components,
    get_stock_price,
    get_batch_stock_prices,
)
from data_sources.fundamentals import (
    get_fundamental_batch,
    get_fundamental_data,
    get_news_sentiment,
)
from data_sources.market import (
    get_market_heat,
    get_market_regime,
    get_sector_performance,
)
from data_sources.technical import calculate_technical
from data_sources.quotes import (
    get_realtime_quotes,
    get_sina_realtime,
    get_simple_market_regime,
)

__all__ = [
    'A_SHARE_POOL', '_STOCK_NAME', '_sina_kline_direct', 'ak',
    'get_index_components', 'get_stock_price', 'get_batch_stock_prices',
    'get_fundamental_batch', 'get_fundamental_data', 'get_news_sentiment',
    'get_market_heat', 'get_market_regime', 'get_sector_performance',
    'calculate_technical',
    'get_realtime_quotes', 'get_sina_realtime', 'get_simple_market_regime',
]

if __name__ == '__main__':
    print('=== 测试数据获取 ===')
    try:
        heat = get_market_heat()
        print(f"市场温度: {heat}")
    except Exception as e:
        print(f"get_market_heat 失败: {e}")
    try:
        k = get_stock_price('000333')
        print(f"000333 K线行数: {len(k)}")
    except Exception as e:
        print(f"get_stock_price 失败: {e}")

