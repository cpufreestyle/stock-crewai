"""
数据获取模块 - 新浪财经源（稳定直连）+ 东方财富降级

新浪源 stock_zh_a_daily 直连稳定，不受代理影响
东方财富 push2 域名不稳定（push2his 已废弃，push2 间歇性 502）
"""
import os

from api_cache import (
    cached,
    realtime_cache,
    market_cache,
)

# 清除代理设置，国内财经网站直连即可
for _k in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
    os.environ.pop(_k, None)

# 强制 requests 绕过系统代理（Clash PAC 会让国内站点也走代理，导致 SSL 错误）
import requests as _req
_orig_merge = _req.Session.merge_environment_settings

def _patched_merge(self, url, proxies, stream, verify, cert):
    # 始终忽略系统代理，直接连接
    settings = _orig_merge(self, url, {}, stream, verify, cert)
    settings['proxies'] = {}
    return settings

_req.Session.merge_environment_settings = _patched_merge

# 惰性加载 akshare — 仅在使用时才导入，不阻塞模块加载
class _AkLazy:
    """akshare 惰性加载器。未安装 akshare 时不会报错，调用时才会抛 ImportError。"""
    def __getattr__(self, name):
        import akshare as _ak_module
        setattr(self, name, getattr(_ak_module, name))
        return getattr(self, name)

ak = _AkLazy()
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import time as _time
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed


# A股候选股票池（沪深300代表性股票，MVP用固定池更稳定）
A_SHARE_POOL = [
    {"code": "000001", "name": "平安银行", "sector": "银行"},
    {"code": "000002", "name": "万科A", "sector": "房地产"},
    {"code": "000063", "name": "中兴通讯", "sector": "通信设备"},
    {"code": "000100", "name": "TCL科技", "sector": "电子"},
    {"code": "000333", "name": "美的集团", "sector": "家电"},
    {"code": "000425", "name": "徐工机械", "sector": "工程机械"},
    {"code": "000651", "name": "格力电器", "sector": "家电"},
    {"code": "000858", "name": "五粮液", "sector": "白酒"},
    {"code": "000876", "name": "新希望", "sector": "农业"},
    {"code": "000895", "name": "双汇发展", "sector": "食品"},
    {"code": "000938", "name": "紫光股份", "sector": "IT"},
    {"code": "002001", "name": "新和成", "sector": "医药"},
    {"code": "002024", "name": "苏宁易购", "sector": "零售"},
    {"code": "002415", "name": "海康威视", "sector": "安防"},
    {"code": "002475", "name": "立讯精密", "sector": "电子制造"},
    {"code": "002594", "name": "比亚迪", "sector": "新能源汽车"},
    {"code": "002714", "name": "牧原股份", "sector": "养殖"},
    {"code": "600009", "name": "上海机场", "sector": "机场"},
    {"code": "600016", "name": "民生银行", "sector": "银行"},
    {"code": "600019", "name": "宝钢股份", "sector": "钢铁"},
    {"code": "600028", "name": "中国石化", "sector": "石油化工"},
    {"code": "600030", "name": "中信证券", "sector": "证券"},
    {"code": "600036", "name": "招商银行", "sector": "银行"},
    {"code": "600048", "name": "保利发展", "sector": "房地产"},
    {"code": "600050", "name": "中国联通", "sector": "通信"},
    {"code": "600104", "name": "上汽集团", "sector": "汽车"},
    {"code": "600276", "name": "恒瑞医药", "sector": "医药"},
    {"code": "600309", "name": "万华化学", "sector": "化工"},
    {"code": "600519", "name": "贵州茅台", "sector": "白酒"},
    {"code": "600887", "name": "伊利股份", "sector": "乳业"},
    {"code": "600900", "name": "长江电力", "sector": "电力"},
    {"code": "601006", "name": "大秦铁路", "sector": "铁路"},
    {"code": "601012", "name": "隆基绿能", "sector": "光伏"},
    {"code": "601088", "name": "中国神华", "sector": "煤炭"},
    {"code": "601118", "name": "海南橡胶", "sector": "农业"},
    {"code": "601166", "name": "兴业银行", "sector": "银行"},
    {"code": "601186", "name": "中国铁建", "sector": "基建"},
    {"code": "601318", "name": "中国平安", "sector": "保险"},
    {"code": "601398", "name": "工商银行", "sector": "银行"},
    {"code": "601628", "name": "中国人寿", "sector": "保险"},
    {"code": "601857", "name": "中国石油", "sector": "石油"},
    {"code": "601888", "name": "中国中免", "sector": "旅游零售"},
    {"code": "601899", "name": "紫金矿业", "sector": "有色金属"},
    {"code": "603259", "name": "药明康德", "sector": "医药"},
    {"code": "603288", "name": "海天味业", "sector": "食品调味"},
    {"code": "603501", "name": "韦尔股份", "sector": "半导体"},
    {"code": "603799", "name": "华友钴业", "sector": "有色金属"},
    {"code": "603986", "name": "兆易创新", "sector": "半导体"},
]
# Code -> name lookup built from A_SHARE_POOL
_STOCK_NAME = {
    "000001": "平安银行",
    "000002": "万科A",
    "000063": "中兴通讯",
    "000100": "TCL科技",
    "000333": "美的集团",
    "000425": "徐工机械",
    "000651": "格力电器",
    "000858": "五粮液",
    "000876": "新希望",
    "000895": "双汇发展",
    "000938": "紫光股份",
    "002001": "新和成",
    "002024": "苏宁易购",
    "002415": "海康威视",
    "002475": "立讯精密",
    "002594": "比亚迪",
    "002714": "牧原股份",
    "600009": "上海机场",
    "600016": "民生银行",
    "600019": "宝钢股份",
    "600028": "中国石化",
    "600030": "中信证券",
    "600036": "招商银行",
    "600048": "保利发展",
    "600050": "中国联通",
    "600104": "上汽集团",
    "600276": "恒瑞医药",
    "600309": "万华化学",
    "600519": "贵州茅台",
    "600887": "伊利股份",
    "600900": "长江电力",
    "601006": "大秦铁路",
    "601012": "隆基绿能",
    "601088": "中国神华",
    "601118": "海南橡胶",
    "601166": "兴业银行",
    "601186": "中国铁建",
    "601318": "中国平安",
    "601398": "工商银行",
    "601628": "中国人寿",
    "601857": "中国石油",
    "601888": "中国中免",
    "601899": "紫金矿业",
    "603259": "药明康德",
    "603288": "海天味业",
    "603501": "韦尔股份",
    "603799": "华友钴业",
    "603986": "兆易创新"
}


def _sina_kline_direct(stock_code: str, period: str = "daily",
                       start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """纯 requests 直接获取新浪 K 线数据（无需 akshare）

    使用新浪财经 CN_MarketData.getKLineData 接口
    """
    # sz/sh 前缀（已带前缀的直接透传：指数必须用 sh000001，
    # 否则 000001 会按个股规则拼成 sz000001=平安银行，牛熊判断会拿一只银行股的价格当大盘）
    if stock_code[:2] in ("sh", "sz"):
        symbol = stock_code
    elif stock_code.startswith(('6', '9')):
        symbol = f"sh{stock_code}"
    else:
        symbol = f"sz{stock_code}"

    # scale: 240=日k, 1200=周k, 7200=月k
    scale_map = {"daily": "240", "weekly": "1200", "monthly": "7200"}
    scale = scale_map.get(period, "240")
    datalen = 250  # 获取250条数据

    url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}")
    headers = {
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'utf-8'
        data = json.loads(r.text)
        if not data or not isinstance(data, list):
            return pd.DataFrame()

        rows = []
        for item in data:
            d = item.get('day', '')
            if not d:
                continue
            rows.append({
                '日期': d[:10],
                '开盘': float(item.get('open', 0)),
                '收盘': float(item.get('close', 0)),
                '最高': float(item.get('high', 0)),
                '最低': float(item.get('low', 0)),
                '成交量': float(item.get('volume', 0)),
                '成交额': 0.0,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')

        # 日期过滤
        if start_date:
            sd = start_date.replace('-', '')
            df = df[df['日期'].str.replace('-', '') >= sd]
        if end_date:
            ed = end_date.replace('-', '')
            df = df[df['日期'].str.replace('-', '') <= ed]

        df = df.sort_values('日期').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"[数据] {stock_code} 新浪直连K线失败: {e}")
        return pd.DataFrame()
