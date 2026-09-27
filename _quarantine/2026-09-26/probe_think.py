"""一次性诊断探针：验证 blob 模板补丁后 q2 的加载/空响应/工具调用行为。"""
import json
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:11434"
MODEL = "qwen3.8:q2"
PROMPT = "用三句话分析今天A股是否适合加仓，并给出一句结论。"
HEAD = {"Content-Type": "application/json", "Authorization": "Bearer ollama"}


def report(tag, payload_ms, js):
    msg = js.get("choices", [{}])[0].get("message", {}) if "choices" in js else {}
    content = msg.get("content") or js.get("content") or ""
    reasoning = msg.get("reasoning_content") or js.get("thinking") or ""
    tc = msg.get("tool_calls")
    print(
        f"[{tag}] wall={payload_ms/1000:.1f}s content_len={len(content)} "
        f"reasoning_len={len(reasoning)} finish={js.get('choices',[{}])[0].get('finish_reason') or js.get('done')}"
    )
    if reasoning:
        print(f"    reasoning[:80]={reasoning[:80]!r}")
    print(f"    content[:120]={content[:120]!r}")
    if tc:
        print(f"    tool_calls={json.dumps(tc, ensure_ascii=False)[:200]}")
    return len(content), len(reasoning)


def v1(payload, tag):
    t0 = time.time()
    try:
        r = requests.post(f"{BASE}/v1/chat/completions", headers=HEAD, json=payload, timeout=600)
        js = r.json()
    except Exception as e:
        print(f"[{tag}] REQUEST FAIL {e}")
        return -1, -1
    return report(tag, (time.time() - t0) * 1000, js)


print("=== 1) 首次调用（含模型加载）：/v1 裸请求 ===")
v1({"model": MODEL, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 300, "keep_alive": "15m"}, "v1-bare")

print("\n=== 2) /v1 + reasoning_effort=low（crew 当前实际发的参数）===")
v1({"model": MODEL, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 300, "reasoning_effort": "low", "keep_alive": "15m"}, "v1-low")

print("\n=== 3) /v1 + reasoning_effort=none ===")
v1({"model": MODEL, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 300, "reasoning_effort": "none", "keep_alive": "15m"}, "v1-none")

print("\n=== 4) /v1 + chat_template_kwargs.enable_thinking=false ===")
v1({"model": MODEL, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 300,
    "chat_template_kwargs": {"enable_thinking": False}, "keep_alive": "15m"}, "v1-ctk")

print("\n=== 5) 原生 /api/chat + think:false ===")
t0 = time.time()
try:
    r = requests.post(f"{BASE}/api/chat", json={"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
                                                 "stream": False, "think": False, "keep_alive": "15m",
                                                 "options": {"num_ctx": 8192, "num_predict": 300}}, timeout=600)
    report("native-think-false", (time.time() - t0) * 1000, r.json())
except Exception as e:
    print(f"[native-think-false] REQUEST FAIL {e}")

print("\n=== 6) /v1 工具调用可用性（补丁后模板是否仍产出 tool_call）===")
tools = [{
    "type": "function",
    "function": {
        "name": "market_heat",
        "description": "查询A股市场热度：涨停家数、跌停家数、涨跌比。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]
v1({"model": MODEL, "messages": [{"role": "user", "content": "请调用 market_heat 工具查询今天市场热度。"}],
    "tools": tools, "tool_choice": "auto", "max_tokens": 300, "keep_alive": "15m"}, "v1-tools")

print("\n=== 当前 /api/ps ===")
print(requests.get(f"{BASE}/api/ps", timeout=20).text[:400])
