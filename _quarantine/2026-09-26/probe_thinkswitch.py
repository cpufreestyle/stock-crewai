"""在真实规模（约 6k token prompt + 工具）下，测 /v1 各字段能否真正关闭 thinking。

每轮之间记录服务端是否出现 common_reaso activated，以判断 thinking 是否真的被关掉。
"""
import subprocess
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:11434"
HEAD = {"Content-Type": "application/json", "Authorization": "Bearer ollama"}
MODEL = "qwen3.8:q2big"
SLOG = "ollama_serve_new.log"

FILLER = (
    "000001 平安银行(银行): 现价=11.75元 MA5=11.62 MA20=11.40 RSI=57(正常) ↑5日+2.8%；"
    "000063 中兴通讯(通信设备): 现价=32.17元 MA5=31.20 MA20=33.55 RSI=44(正常) ↓5日-3.1%；"
    "000333 美的集团(家电): 现价=86.26元 MA5=85.10 MA20=84.20 RSI=61(正常) ↑5日+1.4%。\n"
)
SYSTEM = "你是一名资深A股风险控制专家，必须先调用工具获取真实数据再下结论，禁止编造行情。"
USER = FILLER * 40 + (
    "\n【风控任务】请对每只股票评估：1.主要风险与下跌空间 2.建议仓位（单只不超过总资金20%）"
    "3.止损价（买入价下方8%~15%）4.止盈价（上方15%~30%）5.风险收益比 6.组合整体风险评级（低/中/高）。"
)
TOOLS = [{
    "type": "function",
    "function": {
        "name": "portfolio_risk",
        "description": "计算当前持仓组合的总敞口、VaR 与持仓数量。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]


def reasoning_lines():
    try:
        with open(SLOG, "r", encoding="utf-8", errors="replace") as f:
            return f.read().count("common_reaso: activated")
    except Exception:
        return -1


def run(tag, extra, max_tokens=1024):
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "keep_alive": "20m",
    }
    payload.update(extra)
    before = reasoning_lines()
    t0 = time.time()
    r = requests.post(f"{BASE}/v1/chat/completions", headers=HEAD, json=payload, timeout=900)
    dt = time.time() - t0
    after = reasoning_lines()
    js = r.json()
    if r.status_code != 200:
        print(f"{tag:36s} http={r.status_code} {dt:5.1f}s BODY={r.text[:120]}")
        return
    ch = js.get("choices", [{}])[0]
    msg = ch.get("message", {}) or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    tc = msg.get("tool_calls") or []
    usage = js.get("usage", {})
    ok = bool(tc) or len(content) > 10
    print(
        f"{tag:36s} {dt:6.1f}s finish={str(ch.get('finish_reason')):9s} content={len(content):4d} "
        f"reason={len(reasoning):4d} tools={len(tc)} comp_tok={usage.get('completion_tokens')} "
        f"思考激活+{after-before} -> {'OK' if ok else '*** EMPTY ***'}"
    )


print("### 基线：crew 当前配置（reasoning_effort=none, max_tokens=1024）")
run("none", {"reasoning_effort": "none"})

print("\n### 候选开关")
run("none + think:false", {"reasoning_effort": "none", "think": False})
run("none + thinking:disabled", {"reasoning_effort": "none", "thinking": {"type": "disabled"}})
run("none + max_tokens 3072", {"reasoning_effort": "none"}, max_tokens=3072)
run("none + chat_tpl_kwargs", {"reasoning_effort": "none",
                               "chat_template_kwargs": {"enable_thinking": False}})

print("\n### 原生 /api/chat + think:false（对照组，Ollama 原生支持）")
before = reasoning_lines()
t0 = time.time()
r = requests.post(f"{BASE}/api/chat", json={
    "model": MODEL,
    "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
    "stream": False, "think": False, "keep_alive": "20m",
    "options": {"num_ctx": 32768, "num_predict": 1024, "temperature": 0.3},
}, timeout=900)
js = r.json()
dt = time.time() - t0
print(f"{'native /api/chat think:false':36s} {dt:6.1f}s content={len(js.get('content') or ''):4d} "
      f"think={js.get('thinking') and len(js['thinking'])} 思考激活+{reasoning_lines()-before} "
      f"-> {'OK' if len(js.get('content') or '') > 10 else '*** EMPTY ***'}")
