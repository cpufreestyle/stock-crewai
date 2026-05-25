#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标模块 - 计算MA、MACD、RSI、KDJ、布林带及信号生成
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


def get_history_kline(code: str, days: int = 60) -> List[Dict]:
    """获取历史K线（腾讯接口）"""
    if code.startswith(("6", "9")):
        ts_code = "sh" + code
    else:
        ts_code = "sz" + code
    
    end = datetime.now()
    start = end - timedelta(days=days)
    
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={ts_code},day,{start.strftime('%Y-%m-%d')},{end.strftime('%Y-%m-%d')},60,qfq"
    
    try:
        r = requests.get(url, timeout=15)
        text = r.text
        if "kline_dayqfq=" in text:
            text = text.split("kline_dayqfq=")[1]
        data = json.loads(text)
        
        qfqday = data.get("data", {}).get(ts_code, {}).get("qfqday", [])
        if not qfqday:
            qfqday = data.get("data", {}).get(ts_code, {}).get("day", [])
        
        result = []
        for item in qfqday:
            if len(item) >= 6:
                result.append({
                    "date": item[0],
                    "open": float(item[1]) if item[1] else 0,
                    "close": float(item[2]) if item[2] else 0,
                    "high": float(item[3]) if item[3] else 0,
                    "low": float(item[4]) if item[4] else 0,
                    "volume": float(item[5]) if item[5] else 0,
                })
        
        return result
    except Exception as e:
        return []


def calculate_ma(prices: List[float], period: int) -> Optional[float]:
    """计算移动平均线"""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """计算指数移动平均线"""
    if len(prices) < period:
        return None
    alpha = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = alpha * p + (1 - alpha) * ema
    return ema


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """计算MACD指标"""
    if len(prices) < slow:
        return None, None, None
    
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    
    if ema_fast is None or ema_slow is None:
        return None, None, None
    
    dif = ema_fast - ema_slow
    dea = calculate_ema([dif] * signal, signal)  # 简化估算
    macd_hist = (dif - dea) * 2 if dea else 0
    
    return round(dif, 4), round(dea, 4), round(macd_hist, 4)


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """计算RSI指标"""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return None
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def calculate_bollinger(prices: List[float], period: int = 20, std_dev: int = 2) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """计算布林带"""
    if len(prices) < period:
        return None, None, None
    
    recent = prices[-period:]
    ma = sum(recent) / period
    variance = sum((p - ma) ** 2 for p in recent) / period
    std = variance ** 0.5
    
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    
    return round(upper, 4), round(ma, 4), round(lower, 4)


def calculate_kdj(highs: List[float], lows: List[float], closes: List[float], period: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """计算KDJ指标"""
    if len(closes) < period:
        return None, None, None
    
    rsvs = []
    for i in range(period - 1, len(closes)):
        low_min = min(lows[i-period+1:i+1])
        high_max = max(highs[i-period+1:i+1])
        if high_max == low_min:
            rsvs.append(50)
        else:
            rsv = (closes[i] - low_min) / (high_max - low_min) * 100
            rsvs.append(rsv)
    
    if len(rsvs) < 3:
        k_val = d_val = 50
    else:
        k_val = 50
        d_val = 50
        for rsv in rsvs[-3:]:
            k_val = 2/3 * k_val + 1/3 * rsv
            d_val = 2/3 * d_val + 1/3 * k_val
    
    j_val = 3 * k_val - 2 * d_val
    
    return round(k_val, 2), round(d_val, 2), round(j_val, 2)


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    """计算ATR（平均真实波幅）"""
    if len(closes) < period:
        return None
    
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    
    if len(trs) < period:
        return None
    
    return round(sum(trs[-period:]) / period, 4)


def analyze_stock(code: str) -> Dict:
    """综合分析单只股票的技术指标"""
    klines = get_history_kline(code, days=60)
    
    if len(klines) < 20:
        return {"code": code, "error": "数据不足", "signal": "NEUTRAL"}
    
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    
    # 计算各项指标
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)
    
    dif, dea, macd_hist = calculate_macd(closes)
    rsi = calculate_rsi(closes)
    upper, middle, lower = calculate_bollinger(closes)
    k_val, d_val, j_val = calculate_kdj(highs, lows, closes)
    atr = calculate_atr(highs, lows, closes)
    
    current = closes[-1]
    
    # 生成信号
    score = 0
    signal_detail = []
    
    # MA趋势
    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            score += 3
            signal_detail.append("MA多头排列(+3)")
        elif ma5 < ma10 < ma20:
            score -= 3
            signal_detail.append("MA空头排列(-3)")
        elif ma5 > ma20:
            score += 1
            signal_detail.append("短期在长期线上(+1)")
    
    # MACD
    if dif and dea:
        if dif > dea and macd_hist and macd_hist > 0:
            score += 2
            signal_detail.append("MACD金叉(+2)")
        elif dif < dea:
            score -= 2
            signal_detail.append("MACD死叉(-2)")
    
    # RSI
    if rsi:
        if rsi > 70:
            score -= 1
            signal_detail.append(f"RSI超买({rsi})")
        elif rsi < 30:
            score += 2
            signal_detail.append(f"RSI超卖({rsi})")
        elif 40 <= rsi <= 60:
            score += 1
            signal_detail.append(f"RSI中性({rsi})")
    
    # 布林带
    if upper and middle and lower:
        if current < lower:
            score += 2
            signal_detail.append("价格触及布林下轨(+2)")
        elif current > upper:
            score -= 1
            signal_detail.append("价格触及布林上轨(-1)")
        elif current > middle:
            score += 1
            signal_detail.append("价格在布林中轨上方(+1)")
    
    # KDJ
    if k_val and d_val:
        if k_val > 80 and d_val > 80:
            score -= 1
            signal_detail.append("KDJ超买区域(-1)")
        elif k_val < 20 and d_val < 20:
            score += 1
            signal_detail.append("KDJ超卖区域(+1)")
        elif k_val > d_val:
            score += 1
            signal_detail.append("KDJ金叉(+1)")
    
    # 成交量确认
    recent_vol = klines[-1]["volume"] if klines else 0
    avg_vol = sum(k["volume"] for k in klines[-20:]) / 20
    if recent_vol > avg_vol * 1.5:
        score += 1
        signal_detail.append(f"放量确认(+1, 缩量{recent_vol/avg_vol:.1f}x)")
    
    # 信号判定
    if score >= 5:
        signal = "STRONG_BUY"
    elif score >= 2:
        signal = "BUY"
    elif score <= -3:
        signal = "SELL"
    elif score <= -1:
        signal = "WEAK_SELL"
    else:
        signal = "NEUTRAL"
    
    return {
        "code": code,
        "name": klines[-1].get("name", ""),
        "current": round(current, 2),
        "ma5": round(ma5, 2) if ma5 else None,
        "ma10": round(ma10, 2) if ma10 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "dif": dif,
        "dea": dea,
        "macd_hist": macd_hist,
        "rsi": rsi,
        "bollinger_upper": upper,
        "bollinger_middle": middle,
        "bollinger_lower": lower,
        "k": k_val,
        "d": d_val,
        "j": j_val,
        "atr": atr,
        "score": score,
        "signal": signal,
        "signal_detail": signal_detail,
        "volume_ratio": round(recent_vol / avg_vol, 2) if avg_vol > 0 else 0
    }


def generate_signal(analysis: Dict) -> str:
    """从分析结果生成交易信号（兼容旧接口）"""
    return analysis.get("signal", "NEUTRAL")


if __name__ == "__main__":
    # 测试
    print("=== 技术指标测试 ===")
    
    # 测试美的集团
    result = analyze_stock("000333")
    print(f"\n美的集团 000333:")
    print(f"  当前价: {result.get('current', 'N/A')}")
    print(f"  MA5/10/20: {result.get('ma5', 'N/A')}/{result.get('ma10', 'N/A')}/{result.get('ma20', 'N/A')}")
    print(f"  MACD: dif={result.get('dif')}, dea={result.get('dea')}, hist={result.get('macd_hist')}")
    print(f"  RSI: {result.get('rsi')}")
    print(f"  布林带: 上={result.get('bollinger_upper')}, 中={result.get('bollinger_middle')}, 下={result.get('bollinger_lower')}")
    print(f"  KDJ: K={result.get('k')}, D={result.get('d')}, J={result.get('j')}")
    print(f"  ATR: {result.get('atr')}")
    print(f"  综合评分: {result.get('score', 0)}")
    print(f"  信号: {result.get('signal', 'N/A')}")
    print(f"  详情: {', '.join(result.get('signal_detail', []))}")