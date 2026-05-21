"""
数据获取模块 - 基于 akshare
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional


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
    """获取股票行情（带自动重试，多数据源切换）"""
    import time as _time
    
    # 构建腾讯代码格式
    if stock_code.startswith(('6', '9')):
        tx_code = f"sh{stock_code}"
    else:
        tx_code = f"sz{stock_code}"
    
    # 优先尝试腾讯源（更稳定）
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_hist_tx(symbol=tx_code, adjust="qfq")
            if df.empty:
                raise Exception("空数据")
            
            # 统一列名
            df = df.rename(columns={
                "date": "日期",
                "open": "开盘",
                "close": "收盘",
                "high": "最高",
                "low": "最低",
                "amount": "成交量"
            })
            
            # 过滤日期范围
            if start_date:
                df = df[df["日期"] >= start_date]
            if end_date:
                df = df[df["日期"] <= end_date]
            else:
                # 默认最近90天
                cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
                df = df[df["日期"] >= cutoff]
            
            df = df.reset_index(drop=True)
            return df
        except Exception as e:
            if attempt < 2:
                wait = (attempt + 1) * 5
                print(f"[数据] {stock_code}(腾讯) 第{attempt+1}次失败，{wait}s后重试")
                _time.sleep(wait)
            else:
                pass  # 尝试备用源
    
    # 备用：东方财富源
    for attempt in range(2):
        try:
            if end_date is None:
                end_date = datetime.now().strftime("%Y%m%d")
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

            df = ak.stock_zh_a_hist(symbol=stock_code, period=period,
                                     start_date=start_date, end_date=end_date, adjust="qfq")
            return df
        except Exception as e:
            if attempt < 1:
                _time.sleep(5)
            else:
                print(f"[数据] 获取行情失败 {stock_code}: {e}")
                return pd.DataFrame()


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


if __name__ == "__main__":
    # 测试
    print("=== 测试数据获取 ===")
    heat = get_market_heat()
    print(f"市场热度: {heat}")
