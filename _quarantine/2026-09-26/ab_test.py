"""A/B 验证：reasoning_effort 档位 与 长 prompt 截断 对空响应/耗时的影响。

用法: python ab_test.py
判据: crewai 要求 content>10 字符，否则抛 "Invalid response from LLM call - None or empty." 并中止流水线。
"""
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:11434/v1/chat/completions"
PS = "http://127.0.0.1:11434/api/ps"
HEAD = {"Content-Type": "application/json", "Authorization": "Bearer ollama"}
MODEL = "qwen3.8:q2"

SYSTEM = "你是一名资深A股风险控制专家，必须先调用工具获取真实数据再下结论，禁止编造行情。"
USER = (
    "【候选股票】000001 平安银行 现价11.75元；000063 中兴通讯 现价32.17元；000333 美的集团 现价86.26元。\n"
    "【市场状态】震荡市，涨停40家/跌停6家，建议仓位5成。\n"
    "请对每只股票输出：1.主要风险与下跌空间 2.建议仓位（单只不超过总资金20%）"
    "3.止损价（买入价下方8%~15%）4.止盈价（上方15%~30%）5.风险收益比 6.组合整体风险评级。"
)
TOOLS = [{
    "type": "function",
    "function": {
        "name": "portfolio_risk",
        "description": "计算当前持仓组合的总敞口、VaR 与持仓数量。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]

# 构造 ~6000 token 的长 prompt，模拟 CrewAI 把前序任务输出全部塞进 context 的真实规模
FILLER = (
    "000001 平安银行(银行): 现价=11.75元 MA5=11.62 MA20=11.40 RSI=57(正常) ↑5日+2.8%；"
    "中兴通讯 000063(通信设备): 现价=32.17元 MA5=31.20 MA20=33.55 RSI=44(正常) ↓5日-3.1%；"
    "美的集团 000333(家电): 现价=86.26元 MA5=85.10 MA20=84.20 RSI=61(正常) ↑5日+1.4%。\n"
)
LONG_USER = FILLER * 90 + "\n" + USER


def call(tag, effort, user, max_tokens=1024):
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "keep_alive": "20m",
    }
    if effort:
        payload["reasoning_effort"] = effort
    t0 = time.time()
    try:
        r = requests.post(BASE, headers=HEAD, json=payload, timeout=900)
        ch = r.json().get("choices", [{}])[0]
        msg = ch.get("message", {}) or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        tc = msg.get("tool_calls") or []
    except Exception as e:
        print(f"{tag:34s} REQUEST FAIL {str(e)[:80]}")
        return None
    dt = time.time() - t0
    ok = bool(tc) or len(content) > 10
    print(
        f"{tag:34s} {dt:6.1f}s finish={str(ch.get('finish_reason')):9s} content={len(content):4d} "
        f"reason={len(reasoning):4d} tools={len(tc)} usage={r.json().get('usage')} -> {'OK' if ok else '*** EMPTY ***'}"
    )
    return ok


print("### 预热 + 加载")
call("warmup", "low", USER, max_tokens=64)
print("ps:", requests.get(PS, timeout=20).text[:220].replace("\n", ""))

for effort in ("low", "none", None):
    tag = effort or "default(不传)"
    res = [call(f"[{tag}] short #{i+1}", effort, USER) for i in range(4)]
    good = sum(1 for x in res if x)
    print(f"  -> [{tag}] 短 prompt 通过率 {good}/{len(res)}\n")

print("### 长 prompt（约 6k token，逼近 num_ctx=8192）")
for effort in ("low", "none"):
    call(f"[{effort}] long", effort, LONG_USER, max_tokens=512)

print("\nps:", requests.get(PS, timeout=20).text[:220].replace("\n", ""))
