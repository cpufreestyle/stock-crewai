#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kronos_predictor.py
Kronos 金融时序预测模块 —— 接入 stock-crewai

依赖: pip install transformers torch
用法:
    from kronos_predictor import predict_kronos
    signal = predict_kronos("000001", price=15.5)
    # -> {"action": "BUY", "confidence": 0.73, "predicted_return": 0.021, "reason": "...", "source": "kronos/mock"}
"""

import os
import sys
import json
import re
import math
from datetime import datetime

import numpy as np

# ── 全局状态 ─────────────────────────────────────────────
_KRONOS_CACHE = {}          # code -> (timestamp, signal_dict)
_KRONOS_LOADED = False
_kronos_model = None
_kronos_tokenizer = None
_DEVICE = "cpu"

# 导出标志（供外部检查）
KRONOS_AVAILABLE = False  # 将在 _load_kronos() 中设为 True


def _load_kronos():
    """延迟加载 Kronos 模型（仅首次调用）"""
    global _KRONOS_LOADED, _kronos_model, _kronos_tokenizer, _DEVICE
    if _KRONOS_LOADED:
        return
    _KRONOS_LOADED = True

    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
        global KRONOS_AVAILABLE
        _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Kronos] Loading NeoQuasar/Kronos-mini on {_DEVICE} ...")
        _kronos_tokenizer = AutoTokenizer.from_pretrained("NeoQuasar/Kronos-mini")
        _kronos_model = AutoModelForCausalLM.from_pretrained(
            "NeoQuasar/Kronos-mini",
            torch_dtype=torch.float16 if _DEVICE == "cuda" else torch.float32,
        ).to(_DEVICE)
        print("[Kronos] Model loaded.")
        KRONOS_AVAILABLE = True
    except ImportError:
        print("[Kronos] WARNING: transformers not installed. Run: pip install transformers torch")
    except Exception as e:
        print(f"[Kronos] WARNING: model load failed: {e}")


def _build_prompt(bars, code, price):
    """构造时序分析 prompt"""
    if not bars:
        return None
    recent = bars[-30:] if len(bars) >= 30 else bars
    closes = [b.get("close") or b.get("price") for b in recent]
    if not closes:
        return None

    ma5  = round(float(np.mean(closes[-5:])), 2)  if len(closes) >= 5  else None
    ma10 = round(float(np.mean(closes[-10:])), 2) if len(closes) >= 10 else None
    ma20 = round(float(np.mean(closes[-20:])), 2) if len(closes) >= 20 else None

    slope = 0.0
    if len(closes) >= 5 and closes[-5] != 0:
        slope = (closes[-1] - closes[-5]) / closes[-5] * 100
    if slope > 3:
        trend = "上升趋势"
    elif slope < -3:
        trend = "下降趋势"
    else:
        trend = "震荡整理"

    return (
        f"[INST] You are a financial time-series analyst. "
        f"Stock={code} CurrentPrice={price:.2f} "
        f"Trend={trend} MA5={ma5} MA10={ma10} MA20={ma20} "
        f"Last 5 closes: {[round(c,2) for c in closes[-5:]]} "
        f"Volumes(10k): {[round(v/10000,0) for v in [b.get('volume',0) for b in recent[-5:]]]} [/INST] "
        f"Predict next trading day. Format: ACTION=(BUY|SELL|HOLD) "
        f"CONFIDENCE=0.00-1.00 RETURN%%=e.g. +2.5 or -1.2 : "
    )


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
    confidence = float(m_conf.group()[m_conf.group().find('=')+1:].strip()) if m_conf else 0.5

    m_ret = re.search(r'RETURN%s?\s*=\s*([-+]?\d+\.?\d*)', text)
    if not m_ret:
        m_ret = re.search(r'[-+]?\d+\.?\d*\s*%', text)
    predicted_return = float(m_ret.group(1)) / 100 if m_ret and m_ret.group(1) else 0.0

    return action, min(float(confidence), 0.95), predicted_return


def _mock_signal(code, price):
    """无模型时的 Mock 预测（降级方案）"""
    import random
    r = random.random()
    if r > 0.70:
        action = "BUY"
        conf = 0.50 + r * 0.40
        ret = 0.005 + r * 0.020
    elif r < 0.15:
        action = "SELL"
        conf = 0.50 + (1 - r) * 0.40
        ret = -0.005 - (1 - r) * 0.015
    else:
        action = "HOLD"
        conf = 0.40 + r * 0.30
        ret = (r - 0.5) * 0.010
    return {
        "action": action,
        "confidence": round(min(conf, 0.95), 3),
        "predicted_return": round(ret, 5),
        "reason": f"[Mock] price={price:.2f}",
        "source": "mock",
    }


class KronosPredictor:
    """
    Kronos 预测器（支持缓存，TTL=600s）

    用法:
        predictor = KronosPredictor()
        signal = predictor.predict("000001", price=15.2)
    """

    def __init__(self, model_name="NeoQuasar/Kronos-mini", cache_ttl=600):
        self.model_name = model_name
        self.cache_ttl = cache_ttl

    def predict(self, code, price=None, bars=None):
        """
        预测股票下一交易日走势。

        Args:
            code:   股票代码，如 "000001"
            price:  当前价格（float）。可从 bars 推断
            bars:   K 线数据，List[Dict]，每项含 close/volume/date

        Returns:
            dict: {"action", "confidence", "predicted_return", "reason", "source"}
        """
        now_ts = datetime.now().timestamp()

        # 缓存命中
        if code in _KRONOS_CACHE:
            cached_ts, cached_sig = _KRONOS_CACHE[code]
            if now_ts - cached_ts < self.cache_ttl:
                return cached_sig

        # 确定当前价
        if price is None and bars:
            price = bars[-1].get("close") or bars[-1].get("price")
        if not price:
            return {"action": "HOLD", "confidence": 0, "predicted_return": 0,
                    "reason": "no price data", "source": "error"}

        # 尝试真实 Kronos 推理（仅当模型可用时）
        _load_kronos()
        signal = {}

        if _kronos_model is not None:
            try:
                prompt = _build_prompt(bars or [], code, price)
                if prompt:
                    import torch
                    inputs = _kronos_tokenizer(prompt, return_tensors="pt").to(_DEVICE)
                    with torch.no_grad():
                        outputs = _kronos_model.generate(
                            **inputs,
                            max_new_tokens=80,
                            temperature=0.3,
                            do_sample=True,
                            pad_token_id=_kronos_tokenizer.eos_token_id,
                        )
                    raw = _kronos_tokenizer.decode(outputs[0], skip_special_tokens=True)
                    action, conf, ret = _parse_output(raw)
                    signal = {
                        "action": action,
                        "confidence": conf,
                        "predicted_return": ret,
                        "reason": "[Kronos-mini]",
                        "source": "kronos",
                    }
            except Exception as e:
                print(f"[Kronos] Inference error: {e}")
                signal = {"action": "HOLD", "confidence": 0.5, "predicted_return": 0,
                          "reason": f"Kronos error: {e}", "source": "kronos-error"}

        if not signal:
            signal = _mock_signal(code, price)

        # 缓存
        _KRONOS_CACHE[code] = (now_ts, signal)
        return signal


# ── 全局快捷函数 ────────────────────────────────────────
_predictor = None


def predict_kronos(code, price=None, bars=None):
    """全局单次调用（自动复用 KronosPredictor 实例）"""
    global _predictor
    if _predictor is None:
        _predictor = KronosPredictor()
    return _predictor.predict(code, price, bars)


# ── CLI 测试入口 ────────────────────────────────────────
if __name__ == "__main__":
    # 模拟 K 线数据
    test_bars = [
        {"date": f"2026-05-{d:02d}", "close": 15.0 + (d % 7) * 0.1,
         "volume": 5000000, "price": 15.0 + (d % 7) * 0.1}
        for d in range(1, 31)
    ]
    result = predict_kronos("000001", price=15.5, bars=test_bars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
