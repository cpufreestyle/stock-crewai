#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标模块 - 计算MA、MACD、RSI、KDJ、布林带及信号生成
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
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
    """计算指数移动平均线（通达信口径，取最后一个值）"""
    series = calculate_ema_series(prices, period)
    return series[-1] if series else None


def calculate_sma_seed_series(values: List[float], n: int, m: int) -> List[float]:
    """通达信 SMA(X,N,M) 口径：Y=(X*M+Y'*(N-M))/N，前 N 项均值做种子。

    返回与输入等长的序列；长度不足 N 时返回空列表。
    """
    if len(values) < n or n <= 0:
        return []
    out: List[float] = []
    prev = sum(values[:n]) / n
    for x in values:
        prev = (x * m + prev * (n - m)) / n
        out.append(prev)
    return out


def calculate_ema_series(values: List[float], period: int) -> List[float]:
    """通达信 EMA(X,N) 口径，等价于 SMA(X, N+1, 2)：Y=(X*2+Y'*(N-1))/(N+1)。

    与前版差异：种子取前 N 项均值（而非首元素），使前 period-1 个值也有定义。
    """
    if period <= 0 or len(values) < period:
        return []
    return calculate_sma_seed_series(values, period + 1, 2)


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """计算MACD指标（通达信口径，取最后一个交易日）"""
    series = calculate_macd_series(prices, fast, slow, signal)
    if not series:
        return None, None, None
    dif, dea, hist = series[-1]
    return round(dif, 4), round(dea, 4), round(hist, 4)


def calculate_macd_series(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> List[Tuple[float, float, float]]:
    """通达信 MACD 口径，逐日返回 (DIFF, DEA, MACD柱)。

    公式原文：DIFF:=EMA(CLOSE,SHORT)-EMA(CLOSE,LONG); DEA:=EMA(DIFF,M); MACD:=2*(DIFF-DEA)
    """
    ema_fast = calculate_ema_series(prices, fast)
    ema_slow = calculate_ema_series(prices, slow)
    if not ema_fast or not ema_slow:
        return []
    n = min(len(ema_fast), len(ema_slow))
    dif = [ema_fast[i] - ema_slow[i] for i in range(n)]
    dea = calculate_ema_series(dif, signal)
    if not dea:
        return []
    offset = len(dif) - len(dea)
    out: List[Tuple[float, float, float]] = []
    for i, d in enumerate(dea):
        dif_v = dif[offset + i]
        out.append((dif_v, d, 2 * (dif_v - d)))
    return out


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """计算RSI指标（通达信 Wilder 平滑口径）"""
    return calculate_rsi_wilder(prices, period)


def calculate_rsi_wilder(prices: List[float], period: int = 14) -> Optional[float]:
    """通达信 RSI 口径（Wilder 平滑）。

    公式原文：LC:=REF(CLOSE,1);
               WRSI:=SMA(MAX(CLOSE-LC,0),N,1)/SMA(ABS(CLOSE-LC),N,1)*100
    与旧版差异：增益/损失用 SMA(N,1) 递推平滑，不是最后 N 项的算术平均。
    """
    if len(prices) < period + 1:
        return None
    diffs = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0.0 for d in diffs]
    losses = [-d if d < 0 else 0.0 for d in diffs]
    avg_gain_s = calculate_sma_seed_series(gains, period, 1)
    avg_loss_s = calculate_sma_seed_series(losses, period, 1)
    if not avg_gain_s or not avg_loss_s:
        return None
    avg_gain = avg_gain_s[-1]
    avg_loss = avg_loss_s[-1]
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
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


def calculate_kdj_series(highs: List[float], lows: List[float], closes: List[float],
                         period: int = 9, k_period: int = 3, d_period: int = 3
                         ) -> List[Tuple[float, float, float]]:
    """通达信 KDJ 口径，逐日返回 (K, D, J)。

    公式原文：RSV:=(CLOSE-LLV(LOW,N))/(HHV(HIGH,N)-LLV(LOW,N))*100;
               K:=SMA(RSV,M1,1); D:=SMA(K,M2,1); J:=3*K-2*D
    与旧版差异：K/D 对全序列做 SMA(...,1) 递推，旧版只递推最后 3 个 RSV。
    """
    if len(closes) < period:
        return []
    rsvs: List[float] = []
    for i in range(period - 1, len(closes)):
        window_low = min(lows[i - period + 1:i + 1])
        window_high = max(highs[i - period + 1:i + 1])
        if window_high == window_low:
            rsvs.append(50.0)
        else:
            rsvs.append((closes[i] - window_low) / (window_high - window_low) * 100)
    k_series = calculate_sma_seed_series(rsvs, k_period, 1)
    d_series = calculate_sma_seed_series(k_series, d_period, 1)
    if not k_series or not d_series:
        return []
    offset = len(k_series) - len(d_series)
    out: List[Tuple[float, float, float]] = []
    for i, d_val in enumerate(d_series):
        k_val = k_series[offset + i]
        out.append((k_val, d_val, 3 * k_val - 2 * d_val))
    return out


def calculate_kdj(highs: List[float], lows: List[float], closes: List[float], period: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """计算KDJ指标（通达信口径，取最后一个交易日）"""
    series = calculate_kdj_series(highs, lows, closes, period)
    if not series:
        return None, None, None
    k_val, d_val, j_val = series[-1]
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


def _score_ma_trend(ma5, ma10, ma20, score, detail):
    """MA 趋势信号：多头排列 +3 / 空头排列 -3 / 短期在长期线上 +1"""
    if not (ma5 and ma10 and ma20):
        return score, detail
    if ma5 > ma10 > ma20:
        detail.append("MA多头排列(+3)")
        return score + 3, detail
    if ma5 < ma10 < ma20:
        detail.append("MA空头排列(-3)")
        return score - 3, detail
    if ma5 > ma20:
        detail.append("短期在长期线上(+1)")
        return score + 1, detail
    return score, detail


def _score_macd(dif, dea, macd_hist, score, detail):
    """MACD 信号：金叉 +2 / 死叉 -2"""
    if not (dif and dea):
        return score, detail
    if dif > dea and macd_hist and macd_hist > 0:
        detail.append("MACD金叉(+2)")
        return score + 2, detail
    if dif < dea:
        detail.append("MACD死叉(-2)")
        return score - 2, detail
    return score, detail


def _score_rsi(rsi, score, detail):
    """RSI 信号：超买 -1 / 超卖 +2 / 中性 +1"""
    if not rsi:
        return score, detail
    if rsi > 70:
        detail.append(f"RSI超买({rsi})")
        return score - 1, detail
    if rsi < 30:
        detail.append(f"RSI超卖({rsi})")
        return score + 2, detail
    if 40 <= rsi <= 60:
        detail.append(f"RSI中性({rsi})")
        return score + 1, detail
    return score, detail


def _score_bollinger(current, upper, middle, lower, score, detail):
    """布林带信号：触下轨 +2 / 触上轨 -1 / 中轨上方 +1"""
    if not (upper and middle and lower):
        return score, detail
    if current < lower:
        detail.append("价格触及布林下轨(+2)")
        return score + 2, detail
    if current > upper:
        detail.append("价格触及布林上轨(-1)")
        return score - 1, detail
    if current > middle:
        detail.append("价格在布林中轨上方(+1)")
        return score + 1, detail
    return score, detail


def _score_kdj(k_val, d_val, score, detail):
    """KDJ 信号：超买区 -1 / 超卖区 +1 / 金叉 +1"""
    if not (k_val and d_val):
        return score, detail
    if k_val > 80 and d_val > 80:
        detail.append("KDJ超买区域(-1)")
        return score - 1, detail
    if k_val < 20 and d_val < 20:
        detail.append("KDJ超卖区域(+1)")
        return score + 1, detail
    if k_val > d_val:
        detail.append("KDJ金叉(+1)")
        return score + 1, detail
    return score, detail


def _bar_shape(o: float, h: float, l: float, c: float) -> Optional[Dict]:
    """单根K线的插针形态判定：长影线 + 短实体。

    插针（锤子线 / 射击之星一类）的信息量在「影线远长于实体」：盘中价格被
    快速推到一端又被压回，说明另一侧有明确的力量在反向承接。判定全部用占
    振幅的比例，不用绝对价位——否则 3 元的股票和 300 元的股票会被同一套
    像素阈值判成两种结果。

    返回 None 表示不是插针；否则返回：
      kind: "lower"（长下影，锤子线一侧，偏多）或 "upper"（长上影，偏空）
      body: 实体占振幅比例
      shadow: 长影占振幅比例
      wick_ratio: 长影 / 实体
    实体不足振幅 1/3、长影占振幅过半、长影>=实体2倍才算插针。
    """
    span = h - l
    if span <= 0:
        return None
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    if upper >= lower:
        kind, shadow = "upper", upper
    else:
        kind, shadow = "lower", lower
    body_ratio = body / span
    shadow_ratio = shadow / span
    if body_ratio > 1.0 / 3.0:
        return None
    if shadow_ratio < 0.5:
        return None
    if body <= 0:
        wick_ratio = None
    elif shadow < body * 2:
        return None
    else:
        wick_ratio = shadow / body
    return {
        "kind": kind,
        "body": round(body_ratio, 4),
        "shadow": round(shadow_ratio, 4),
        "wick_ratio": round(wick_ratio, 4) if wick_ratio is not None else None,
    }


def detect_pins(highs, lows, opens, closes, atr=None, lookback=20):
    """在最近 lookback 根K线里找插针，按时间倒序返回（最新在前）。

    atr 传入时只保留「影线长度 >= 0.8*ATR」的那些——小波动里的长影只是
    噪声，大波动里的长影才是真正的力量反转信号。

    lookback 默认 20（约一个月交易日）而不是 5：真实行情上插针
    平均约 34 根才出现一次（8 只股票 480 根日K得 14 个），5 根窗
    口的命中率只有 14%，8 只全部落空。窗口太窄的话这个功能
    等于永远不触发。
    """
    pins = []
    n = min(len(highs), len(lows), len(opens), len(closes))
    start = max(0, n - lookback)
    for i in range(n - 1, start - 1, -1):
        shape = _bar_shape(opens[i], highs[i], lows[i], closes[i])
        if shape is None:
            continue
        if atr and atr > 0:
            shadow_len = (highs[i] - max(opens[i], closes[i])
                          if shape["kind"] == "upper"
                          else min(opens[i], closes[i]) - lows[i])
            if shadow_len < 0.8 * atr:
                continue
        shape["index"] = i
        pins.append(shape)
    return pins


def _score_pins(pins, score, detail):
    """插针信号：长下影 +2 / 长上影 -2，同一方向只记一次。"""
    if not pins:
        return score, detail
    kinds = {p["kind"] for p in pins}
    if "lower" in kinds:
        detail.append("长下影插针(+2)")
        score += 2
    if "upper" in kinds:
        detail.append("长上影插针(-2)")
        score -= 2
    return score, detail


def _score_volume(klines, score, detail):
    """成交量确认：最新量 > 20 日均量 1.5 倍时 +1"""
    recent_vol = klines[-1]["volume"] if klines else 0
    avg_vol = sum(k["volume"] for k in klines[-20:]) / 20
    if recent_vol > avg_vol * 1.5:
        detail.append(f"放量确认(+1, 缩量{recent_vol/avg_vol:.1f}x)")
        return score + 1, detail, recent_vol, avg_vol
    return score, detail, recent_vol, avg_vol


def _judge_signal(score):
    """按总分映射交易信号"""
    if score >= 5:
        return "STRONG_BUY"
    if score >= 2:
        return "BUY"
    if score <= -3:
        return "SELL"
    if score <= -1:
        return "WEAK_SELL"
    return "NEUTRAL"


def analyze_stock(code: str) -> Dict:
    """综合分析单只股票的技术指标"""
    klines = get_history_kline(code, days=60)

    if len(klines) < 20:
        return {"code": code, "error": "数据不足", "signal": "NEUTRAL"}

    closes = [k["close"] for k in klines]
    opens = [k["open"] for k in klines]
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

    score, signal_detail = _score_ma_trend(ma5, ma10, ma20, score, signal_detail)
    score, signal_detail = _score_macd(dif, dea, macd_hist, score, signal_detail)
    score, signal_detail = _score_rsi(rsi, score, signal_detail)
    score, signal_detail = _score_bollinger(current, upper, middle, lower, score, signal_detail)
    score, signal_detail = _score_kdj(k_val, d_val, score, signal_detail)
    score, signal_detail, recent_vol, avg_vol = _score_volume(klines, score, signal_detail)
    pins = detect_pins(highs, lows, opens, closes, atr=atr)
    score, signal_detail = _score_pins(pins, score, signal_detail)

    signal = _judge_signal(score)

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
        "volume_ratio": round(recent_vol / avg_vol, 2) if avg_vol > 0 else 0,
        "pins": pins,
    }


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
