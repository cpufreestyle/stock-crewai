"""
数据获取模块 - 新浪财经源（稳定直连）+ 东方财富降级

新浪源 stock_zh_a_daily 直连稳定，不受代理影响
东方财富 push2 域名不稳定（push2his 已废弃，push2 间歇性 502）
"""
import os

from api_cache import (
    TTLCache,
    cached,
    realtime_cache,
    market_cache,
    kline_cache,
    clear_all_caches,
    get_all_cache_stats
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

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import time as _time
import requests
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


def get_index_components(symbol: str = "000300") -> pd.DataFrame:
    """获取指数成分股（默认沪深300），MVP用固定股票池"""
    return pd.DataFrame(A_SHARE_POOL)


def get_stock_price(stock_code: str, period: str = "daily",
                    start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """获取股票行情（新浪财经优先，东方财富降级）"""
    import time as _time

    # 日期格式
    if end_date is None:
        em_end = datetime.now().strftime("%Y%m%d")
    else:
        em_end = end_date.replace("-", "")
    if start_date is None:
        em_start = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
    else:
        em_start = start_date.replace("-", "")

    # --- 数据源1: AkShare 新浪财经源（稳定直连，不受代理影响） ---
    period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
    # 新浪源需要 sz/sh 前缀
    if stock_code.startswith(('6', '9')):
        sina_code = f"sh{stock_code}"
    else:
        sina_code = f"sz{stock_code}"
    for attempt in range(2):
        try:
            df = ak.stock_zh_a_daily(symbol=sina_code, start_date=em_start, end_date=em_end, adjust="qfq")
            if df is not None and not df.empty:
                df = df.rename(columns={
                    "date": "日期", "open": "开盘", "close": "收盘",
                    "high": "最高", "low": "最低", "volume": "成交量", "amount": "成交额"
                })
                if "日期" in df.columns:
                    df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
                df = df.sort_values("日期").reset_index(drop=True)
                print(f"[数据] {stock_code} 新浪获取{len(df)}条")
                return df
        except Exception as e:
            print(f"[数据] {stock_code} 新浪 attempt={attempt} 失败: {e}")
            if attempt < 1:
                _time.sleep(2)

    # --- 数据源2: AkShare 东方财富源（降级备用） ---
    for attempt in range(2):
        try:
            df = ak.stock_zh_a_hist(symbol=stock_code, period=period,
                                     start_date=em_start, end_date=em_end, adjust="qfq")
            if df is not None and not df.empty:
                df = df.rename(columns={
                    "日期": "日期", "开盘": "开盘", "收盘": "收盘",
                    "最高": "最高", "最低": "最低", "成交量": "成交量", "成交额": "成交额"
                })
                if "日期" in df.columns:
                    df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
                df = df.sort_values("日期").reset_index(drop=True)
                print(f"[数据] {stock_code} 东方财富获取{len(df)}条")
                return df
        except Exception as e:
            print(f"[数据] {stock_code} 东方财富 attempt={attempt} 失败: {e}")
            if attempt < 1:
                _time.sleep(2)

    print(f"[数据] 获取行情失败 {stock_code}")
    return pd.DataFrame()


def get_batch_stock_prices(codes: List[str], max_workers: int = 5) -> Dict[str, pd.DataFrame]:
    """并行获取多只股票行情（提速 3-5 倍）"""
    results = {}
    
    def fetch_one(code: str) -> Tuple[str, pd.DataFrame]:
        df = get_stock_price(code)
        return code, df
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, code): code for code in codes}
        for future in as_completed(futures):
            try:
                code, df = future.result()
                if not df.empty:
                    results[code] = df
            except Exception as e:
                code = futures[future]
                print(f"[并行] {code} 获取失败: {e}")
    
    print(f"[并行] 成功获取 {len(results)}/{len(codes)} 只股票行情")
    return results


def get_stock_info(stock_code: str) -> Dict:
    """获取股票基本信息"""
    try:
        df = ak.stock_individual_info_em(symbol=stock_code)
        info = dict(zip(df["item"].tolist(), df["value"].tolist()))
        return info
    except Exception as e:
        print(f"[数据] 获取基本信息失败 {stock_code}: {e}")
        return {}


def get_financials(stock_code: str) -> Dict:
    """获取财务数据"""
    try:
        df = ak.stock_financial_analysis_indicator(symbol=stock_code)
        latest = df.iloc[0].to_dict() if not df.empty else {}
        return latest
    except Exception as e:
        return {}


def get_news_sentiment(keyword: str = "A股", days: int = 3) -> List[Dict]:
    """获取财经新闻（模拟情感分析数据源）"""
    try:
        df = ak.stock_news_em()
        recent = df[df["发布时间"] >= (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")]
        return recent.head(10).to_dict("records")
    except Exception as e:
        print(f"[数据] 获取新闻失败: {e}")
        return []


def get_market_heat() -> Dict:
    """获取市场情绪指标（涨跌家数、市场状态）"""
    try:
        # 使用涨跌停板数据评估市场情绪
        df = ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
        rising = len(df[df['涨跌幅'] > 9])
        falling = len(df[df['涨跌幅'] < -9])
        return {
            "涨停家数": rising,
            "跌停家数": falling,
            "市场状态": "火热" if rising > 30 else ("低迷" if rising < 10 else "正常"),
            "日期": datetime.now().strftime("%Y-%m-%d")
        }
    except Exception as e:
        # 备用：返回模拟数据
        return {
            "涨停家数": "N/A",
            "跌停家数": "N/A",
            "市场状态": "未知",
            "日期": datetime.now().strftime("%Y-%m-%d")
        }


@cached(ttl=300, cache_instance=market_cache)
def get_market_regime(index_code: str = "000001", days: int = 120) -> Dict:
    """
    判断市场状态（牛熊市）
    使用上证指数判断整体市场环境
    
    返回：
    - regime: "牛市" / "熊市" / "震荡市"
    - confidence: 0-100 的置信度
    - signals: 各指标信号列表
    """
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        idx_df = ak.stock_zh_index_daily(symbol=f"sh{index_code}")
        
        # 取最近的数据
        idx_df = idx_df.tail(days)
        if idx_df.empty or len(idx_df) < 60:
            return {"regime": "未知", "confidence": 0, "signals": ["数据不足"]}
        
        closes = idx_df["close"]
        
        # 计算均线
        ma20 = closes.rolling(20).mean()
        ma60 = closes.rolling(60).mean()
        ma120 = closes.rolling(120).mean() if len(closes) >= 120 else None
        
        # 计算动量
        ret_5d = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) >= 6 else 0
        ret_20d = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100 if len(closes) >= 21 else 0
        ret_60d = (closes.iloc[-1] / closes.iloc[-61] - 1) * 100 if len(closes) >= 61 else 0
        
        # 计算波动率
        volatility = closes.pct_change().rolling(20).std().iloc[-1] * 100 if len(closes) >= 20 else 0
        
        # 信号打分
        signals = []
        score = 0
        
        # MA 趋势信号
        if closes.iloc[-1] > ma20.iloc[-1]:
            signals.append("价格>MA20 ✓")
            score += 1
        else:
            signals.append("价格<MA20 ✗")
            score -= 1
        
        if ma20.iloc[-1] > ma60.iloc[-1]:
            signals.append("MA20>MA60(多头) ✓")
            score += 1
        else:
            signals.append("MA20<MA60(空头) ✗")
            score -= 1
        
        if ma120 is not None:
            if ma60.iloc[-1] > ma120.iloc[-1]:
                signals.append("MA60>MA120(长期多头) ✓")
                score += 1
            else:
                signals.append("MA60<MA120(长期空头) ✗")
                score -= 1
        
        # 动量信号
        if ret_20d > 0:
            signals.append(f"20日收益+{ret_20d:.1f}% ✓")
            score += 1
        else:
            signals.append(f"20日收益{ret_20d:.1f}% ✗")
            score -= 1
        
        if ret_60d > 0:
            signals.append(f"60日收益+{ret_60d:.1f}% ✓")
            score += 1
        else:
            signals.append(f"60日收益{ret_60d:.1f}% ✗")
            score -= 1
        
        # 判断市场状态
        if score >= 3:
            regime = "牛市"
            confidence = min(100, 50 + score * 10)
        elif score <= -3:
            regime = "熊市"
            confidence = min(100, 50 + abs(score) * 10)
        else:
            regime = "震荡市"
            confidence = 50 - abs(score) * 5
        
        return {
            "regime": regime,
            "confidence": round(confidence, 1),
            "signals": signals,
            "score": score,
            "index_code": index_code,
            "current_price": round(closes.iloc[-1], 2),
            "ma20": round(ma20.iloc[-1], 2),
            "ma60": round(ma60.iloc[-1], 2),
            "ret_5d": round(ret_5d, 2),
            "ret_20d": round(ret_20d, 2),
            "ret_60d": round(ret_60d, 2),
            "volatility_20d": round(volatility, 2),
            "日期": datetime.now().strftime("%Y-%m-%d")
        }
    except Exception as e:
        return {"regime": "未知", "confidence": 0, "signals": [f"获取失败: {e}"]}


def get_sector_performance() -> List[Dict]:
    """
    获取行业板块表现
    返回近期表现最好的板块
    """
    try:
        df = ak.stock_sector_spot()
        # 按涨跌幅排序
        df_sorted = df.sort_values(by="涨跌幅", ascending=False)
        
        top_sectors = []
        for _, row in df_sorted.head(10).iterrows():
            top_sectors.append({
                "name": str(row.get("名称", "")),
                "change_pct": round(float(row.get("涨跌幅", 0)), 2),
                "volume": str(row.get("成交额", "")),
                "turnover": str(row.get("换手率", ""))
            })
        
        return top_sectors
    except Exception as e:
        print(f"[数据] 获取板块表现失败: {e}")
        return []


def calculate_technical(df: pd.DataFrame) -> Dict:
    """计算技术指标（MA/RSI/MACD/布林带）"""
    if df.empty or len(df) < 20:
        return {}
    
    closes = df["收盘"]
    
    # 简单均线
    ma5 = closes.rolling(5).mean().iloc[-1]
    ma20 = closes.rolling(20).mean().iloc[-1]
    ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else None
    
    # RSI(14)
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean().iloc[-1]
    loss = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
    rs = gain / loss if loss != 0 else 100
    rsi = 100 - (100 / (1 + rs))
    
    # MACD(12,26,9)
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd = (dif - dea) * 2
    
    macd_hist = macd.iloc[-1]
    macd_dif = dif.iloc[-1]
    macd_dea = dea.iloc[-1]
    macd_signal = "金叉" if macd_hist > 0 else "死叉"
    
    # 布林带(20,2)
    bb_middle = closes.rolling(20).mean()
    bb_std = closes.rolling(20).std()
    bb_upper = bb_middle + 2 * bb_std
    bb_lower = bb_middle - 2 * bb_std
    
    bb_pos = (closes.iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]) * 100 if bb_upper.iloc[-1] != bb_lower.iloc[-1] else 50
    bb_signal = "超买" if bb_pos > 80 else ("超卖" if bb_pos < 20 else "正常")
    
    # 近期涨跌
    recent_return = (closes.iloc[-1] / closes.iloc[-5] - 1) * 100 if len(closes) >= 5 else 0
    
    return {
        "收盘价": closes.iloc[-1],
        "MA5": round(ma5, 2),
        "MA20": round(ma20, 2),
        "MA60": round(ma60, 2) if ma60 else None,
        "RSI": round(rsi, 1),
        "MACD直方图": round(macd_hist, 4),
        "MACD_DIF": round(macd_dif, 4),
        "MACD_DEA": round(macd_dea, 4),
        "MACD信号": macd_signal,
        "布林带位置%": round(bb_pos, 1),
        "布林带信号": bb_signal,
        "5日涨跌%": round(recent_return, 2),
        "最新日期": df["日期"].iloc[-1] if "日期" in df.columns else None
    }


@cached(ttl=10, cache_instance=realtime_cache)
def get_realtime_quotes(stock_codes: List[str]) -> List[Dict]:
    """获取实时行情（新浪接口）
    
    Args:
        stock_codes: 股票代码列表，如 ['000001', '600519']
    
    Returns:
        [{code, name, price, change, change_pct, volume, amount, high, low, open, prev_close}, ...]
    """
    if not stock_codes:
        return []
    
    # 添加 sh/sz 前缀（沪市6开头，深市0/3开头）
    sina_codes = []
    for c in stock_codes:
        if c.startswith(("6", "9")):
            sina_codes.append("sh" + c)
        else:
            sina_codes.append("sz" + c)
    
    # 新浪实时行情 API
    codes_str = ','.join(sina_codes)
    url = f"https://hq.sinajs.cn/list={codes_str}"
    
    headers = {
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'gbk'
        
        results = []
        for line in r.text.strip().split('\n'):
            if not line or '=' not in line:
                continue
            
            # 解析: var hq_str_sz000333="美的集团,12.34,..."
            parts = line.split('="')
            if len(parts) != 2:
                continue
            
            # 提取原始代码（去掉 sh/sz 前缀）
            raw = parts[0]  # e.g. hq_str_sz000333
            code_part = raw.split('_')[-1]  # e.g. sz000333
            if code_part.startswith(('sh', 'sz')):
                code = code_part[2:]  # 去掉 sh/sz，得到 000333
            else:
                continue
            
            data = parts[1].rstrip('";').split(',')
            
            if len(data) < 32:
                continue
            
            name = data[0]
            open_price = float(data[1]) if data[1] else 0
            prev_close = float(data[2]) if data[2] else 0
            price = float(data[3]) if data[3] else 0
            high = float(data[4]) if data[4] else 0
            low = float(data[5]) if data[5] else 0
            volume = int(float(data[8])) if data[8] else 0
            amount = float(data[9]) if data[9] else 0
            
            change = price - prev_close if prev_close > 0 else 0
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0
            
            results.append({
                'code': code,
                'name': name,
                'price': round(price, 2),
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'prev_close': round(prev_close, 2),
                'change': round(change, 2),
                'change_pct': round(change_pct, 2),
                'volume': volume,
                'amount': round(amount, 2)
            })
        
        return results
        
    except Exception as e:
        print(f"获取实时行情失败: {e}")
        return []


@cached(ttl=10, cache_instance=realtime_cache)
def get_sina_realtime(codes: List[str]) -> Dict[str, Dict]:
    """获取实时行情（兼容 run_virtual_v4.py 格式）
    
    Returns:
        {code: {name, open, last_close, current, high, low, volume, amount, change_pct}, ...}
    """
    if not codes:
        return {}
    
    quotes = get_realtime_quotes(codes)
    result = {}
    for q in quotes:
        result[q['code']] = {
            'name': q['name'],
            'open': q['open'],
            'last_close': q['prev_close'],
            'current': q['price'],
            'high': q['high'],
            'low': q['low'],
            'volume': q['volume'],
            'amount': q['amount'],
            'change_pct': q['change_pct']
        }
    return result


@cached(ttl=300, cache_instance=market_cache)
def get_simple_market_regime() -> str:
    """简单市场状态判断（兼容 run_virtual_v4.py 格式）
    
    Returns:
        "牛市" | "熊市" | "震荡市"
    """
    try:
        r = requests.get(
            "https://hq.sinajs.cn/list=sh000300",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=10
        )
        fields = r.text.split('"')[1].split(",")
        if len(fields) >= 4:
            current = float(fields[3])
            last_close = float(fields[2])
            change_pct = (current / last_close - 1) * 100 if last_close > 0 else 0
            
            if change_pct > 1:
                return "牛市"
            elif change_pct < -1:
                return "熊市"
            else:
                return "震荡市"
    except:
        pass
    return "震荡市"


if __name__ == "__main__":
    # 测试
    print("=== 测试数据获取 ===")
    heat = get_market_heat()
    print(f"市场热度: {heat}")
    
    # 测试 get_sina_realtime
    print("\n=== 测试 get_sina_realtime ===")
    data = get_sina_realtime(['000333', '600519'])
    for code, d in data.items():
        print(f"{code}: {d['name']} 現价={d['current']} ({d['change_pct']:+.2f}%)")
    
    # 测试 get_simple_market_regime
    print(f"\n市场状态: {get_simple_market_regime()}")
