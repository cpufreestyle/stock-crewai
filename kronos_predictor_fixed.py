#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kronos_predictor.py - 修复版
方案：移除 HuggingFace 依赖，改用本地技术指标 + 可选本地 LLM（Ollama）
用法不变：from kronos_predictor import predict_kronos
"""

import os
import json
import re
import math
from datetime import datetime
import numpy as np

# ── 全局状态 ──────────────────────────────────────────
_KRONOS_CACHE = {}          # code -> (timestamp, signal_dict)
_KRONOS_LOADED = False
_LOCAL_LLM_AVAILABLE = False
_ollma_host = "http://localhost:11434"  # Ollama 默认端口


def _load_local_llm():
    """检测本地是否有 Ollama 或其他 LLM 可用"""
    global _KRONOS_LOADED, _LOCAL_LLM_AVAILABLE
    if _KRONOS_LOADED:
        return
    _KRONOS_LOADED = True

    # 尝试连接 Ollama
    try:
        import urllib.request
        req = urllib.request.Request(f"{_ollma_host}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            if data.get("models"):
                _LOCAL_LLM_AVAILABLE = True
                print(f"[Kronos] Ollama detected: {[m['name'] for m in data['models'][:3]]}")
    except Exception as e:
        print(f"[Kronos] No local LLM detected (Ollama not running): {e}")


def _call_ollama(prompt, model="qwen2:1.5b"):
    """调用本地 Ollama API"""
    try:
        import urllib.request
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 80}
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{_ollma_host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("response", "")
    except Exception as e:
        print(f"[Kronos] Ollama call failed: {e}")
        return ""


def _build_prompt(bars, code, price):
    """构造时序分析 prompt（兼容本地 LLM）"""
    if not bars:
        return None
    recent = bars[-30:] if len(bars) >= 30 else bars
    closes = [float(b.get("close") or b.get("price", 0)) for b in recent]
    volumes = [float(b.get("volume", 0)) for b in recent]
    if not closes or all(c == 0 for c in closes):
        return None

    ma5 = round(np.mean(closes[-5:]), 2) if len(closes) >= 5 else None
    ma10 = round(np.mean(closes[-10:]), 2) if len(closes) >= 10 else None
    ma20 = round(np.mean(closes[-20:]), 2) if len(closes) >= 20 else None

    slope = 0.0
    if len(closes) >= 5 and closes[-6] != 0:
        slope = (closes[-1] - closes[-6]) / closes[-6] * 100
    
    if slope > 3:
        trend = "上升趋势"
    elif slope < -3:
        trend = "下降趋势"
    else:
        trend = "震荡整理"

    # 成交量变化
    vol_ma5 = np.mean(volumes[-5:]) if len(volumes) >= 5 else 0
    vol_ratio = volumes[-1] / vol_ma5 if vol_ma5 > 0 else 1.0

    prompt = f"""你是一个金融时间序列分析师。
股票代码：{code}
当前价格：{price:.2f}
趋势：{trend}
MA5={ma5} MA10={ma10} MA20={ma20}
最近5日收盘价：{[round(c, 2) for c in closes[-5:]]}
成交量比：{vol_ratio:.2f}x（相对5日均量）

请预测下一交易日走势。
输出格式（严格按此格式）：
ACTION=BUY 或 SELL 或 HOLD
CONFIDENCE=0.00-1.00
RETURN%=预测收益率（如 +2.5 或 -1.2）
REASON=简要理由（20字内）
"""
    return prompt


def _parse_output(text):
    """解析 LLM 输出"""
    text = text.upper()
    action = "HOLD"
    for kw in ["BUY", "SELL", "HOLD"]:
        if kw in text:
            action = kw
            break

    m_conf = re.search(r'CONFIDENCE\s*=\s*0?\.\d+', text)
    if not m_conf:
        m_conf = re.search(r'0\.\d+', text)
    confidence = 0.5
    if m_conf:
        conf_str = m_conf.group()
        num_str = re.search(r'0?\.\d+', conf_str)
        if num_str:
            confidence = min(float(num_str.group()), 0.95)

    m_ret = re.search(r'RETURN\s*%\s*=\s*([-+]?\d+\.?\d*)', text)
    if not m_ret:
        m_ret = re.search(r'([-+]?\d+\.?\d*)\s*%', text)
    predicted_return = 0.0
    if m_ret:
        try:
            predicted_return = float(m_ret.group(1)) / 100
        except:
            predicted_return = 0.0

    return action, confidence, predicted_return


def _technical_signal(bars, price):
    """纯技术指标信号（无 LLM 降级方案）"""
    if not bars or len(bars) < 10:
        return {
            "action": "HOLD",
            "confidence": 0.3,
            "predicted_return": 0.0,
            "reason": "数据不足",
            "source": "technical_fallback"
        }
    
    closes = np.array([float(b.get("close") or b.get("price", 0)) for b in bars])
    volumes = np.array([float(b.get("volume", 0)) for b in bars])
    
    # MA 计算
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else ma10
    
    # 动量
    slope = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
    
    # 成交量确认
    vol_ma5 = np.mean(volumes[-5:]) if len(volumes) >= 5 else 1
    vol_ratio = volumes[-1] / vol_ma5 if vol_ma5 > 0 else 1
    
    # RSI 简化版
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else 0
    avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else 0
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - (100 / (1 + rs))
    
    # 评分逻辑
    score = 0
    reason_parts = []
    
    # 1. 均线多头（30分）
    if ma5 > ma10 > ma20:
        score += 30
        reason_parts.append("均线多头")
    elif ma5 < ma10 < ma20:
        score -= 30
        reason_parts.append("均线空头")
    
    # 2. 价格在 MA5 上方（20分）
    if price > ma5:
        score += 20
        reason_parts.append("站上MA5")
    else:
        score -= 20
        reason_parts.append("跌破MA5")
    
    # 3. 动量（20分）
    if slope > 2:
        score += 20
        reason_parts.append("上涨动能")
    elif slope < -2:
        score -= 20
        reason_parts.append("下跌动能")
    
    # 4. RSI（15分）
    if rsi < 30:
        score += 15
        reason_parts.append("RSI超卖")
    elif rsi > 70:
        score -= 15
        reason_parts.append("RSI超买")
    
    # 5. 成交量（15分）
    if vol_ratio > 1.5:
        if score > 0:
            score += 15
            reason_parts.append("放量上涨")
        else:
            score -= 15
            reason_parts.append("放量下跌")
    
    # 决策
    if score >= 40:
        action = "BUY"
        confidence = min(0.5 + score / 200, 0.9)
        predicted_return = slope / 100 * 2  # 简单预测
    elif score <= -40:
        action = "SELL"
        confidence = min(0.5 + abs(score) / 200, 0.9)
        predicted_return = slope / 100 * 2
    else:
        action = "HOLD"
        confidence = 0.4
        predicted_return = 0.0
    
    return {
        "action": action,
        "confidence": round(confidence, 3),
        "predicted_return": round(predicted_return, 5),
        "reason": " | ".join(reason_parts[:3]) or "技术面中性",
        "source": "technical_indicators"
    }


def _mock_signal(code, price):
    """随机 Mock（最后降级）"""
    import random
    r = random.random()
    if r > 0.7:
        action = "BUY"
        conf = 0.50 + r * 0.40
        ret = 0.005 + r * 0.020
        reason = "Mock买入信号"
    elif r < 0.15:
        action = "SELL"
        conf = 0.50 + (1 - r) * 0.40
        ret = -0.005 - (1 - r) * 0.015
        reason = "Mock卖出信号"
    else:
        action = "HOLD"
        conf = 0.40 + r * 0.30
        ret = (r - 0.5) * 0.010
        reason = "Mock观望"
    return {
        "action": action,
        "confidence": round(min(conf, 0.95), 3),
        "predicted_return": round(ret, 5),
        "reason": reason,
        "source": "mock"
    }


class KronosPredictor:
    """
    Kronos 预测器（支持缓存，TTL=600s）
    优先级：本地 LLM (Ollama) > 技术指标 > Mock
    """
    
    def __init__(self, model_name="qwen2:1.5b", cache_ttl=600):
        self.model_name = model_name
        self.cache_ttl = cache_ttl
        self.use_llm = False
        _load_local_llm()
        if _LOCAL_LLM_AVAILABLE:
            self.use_llm = True
            print(f"[Kronos] Using local LLM: {model_name}")
        else:
            print("[Kronos] Local LLM not available, using technical indicators")
    
    def predict(self, code, price=None, bars=None):
        """
        预测股票下一交易日走势
        返回: {"action", "confidence", "predicted_return", "reason", "source"}
        """
        now_ts = datetime.now().timestamp()
        
        # 缓存命中
        if code in _KRONOS_CACHE:
            cached_ts, cached_sig = _KRONOS_CACHE[code]
            if now_ts - cached_ts < self.cache_ttl:
                return cached_sig
        
        # 确定当前价
        if price is None and bars:
            price = float(bars[-1].get("close") or bars[-1].get("price", 0))
        if not price:
            return {
                "action": "HOLD",
                "confidence": 0,
                "predicted_return": 0,
                "reason": "无价格数据",
                "source": "error"
            }
        
        # 尝试本地 LLM
        signal = {}
        if self.use_llm:
            try:
                prompt = _build_prompt(bars or [], code, price)
                if prompt:
                    raw = _call_ollama(prompt, self.model_name)
                    if raw:
                        action, conf, ret = _parse_output(raw)
                        signal = {
                            "action": action,
                            "confidence": conf,
                            "predicted_return": ret,
                            "reason": f"[Ollama-{self.model_name}]",
                            "source": "local_llm"
                        }
            except Exception as e:
                print(f"[Kronos] LLM inference error: {e}")
        
        # 降级：技术指标
        if not signal:
            signal = _technical_signal(bars or [], price)
        
        # 最后降级：Mock
        if not signal or signal.get("source") == "error":
            signal = _mock_signal(code, price)
        
        # 缓存
        _KRONOS_CACHE[code] = (now_ts, signal)
        return signal


# ── 全局快捷函数 ───────────────────────────────────────
_predictor = None


def predict_kronos(code, price=None, bars=None):
    """全局单次调用（自动复用 KronosPredictor 实例）"""
    global _predictor
    if _predictor is None:
        _predictor = KronosPredictor()
    return _predictor.predict(code, price, bars)


# ── CLI 测试入口 ───────────────────────────────────────
if __name__ == "__main__":
    # 模拟 K 线数据
    test_bars = [
        {"date": f"2026-05-{d:02d}", "close": 15.0 + (d % 7) * 0.1,
         "volume": 5000000 + (d % 3) * 1000000, "price": 15.0 + (d % 7) * 0.1}
        for d in range(1, 31)
    ]
    result = predict_kronos("000001", price=15.5, bars=test_bars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
