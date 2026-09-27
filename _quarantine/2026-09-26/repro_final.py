"""精确复现 CrewAI 失败点：工具结果已回填、要求输出最终报告的那一次调用。

实测失败特征是 finish=length + 生成 token 正好等于 max_tokens（预算全被 thinking 吃掉）。
"""
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:11434/v1/chat/completions"
HEAD = {"Content-Type": "application/json", "Authorization": "Bearer ollama"}
MODEL = "qwen3.8:q2big"

FILLER = (
    "000001 平安银行(银行): 现价=11.75元 MA5=11.62 MA20=11.40 RSI=57(正常) ↑5日+2.8%；"
    "000063 中兴通讯(通信设备): 现价=32.17元 MA5=31.20 MA20=33.55 RSI=44(正常) ↓5日-3.1%；"
    "000333 美的集团(家电): 现价=86.26元 MA5=85.10 MA20=84.20 RSI=61(正常) ↑5日+1.4%。\n"
)
SYSTEM = (
    "你是一名独立的风险控制专家，只对下行风险负责。"
    "你必须先调用工具获取真实数据，再给出结论，禁止编造行情。"
    "回答需覆盖：主要风险、建议仓位、止损价、止盈价、风险收益比、组合整体评级。"
)
USER = FILLER * 40 + (
    "\n【风控任务】对每只股票评估：1.主要风险与下跌空间 2.建议仓位（单只不超过总资金20%）"
    "3.止损价（买入价下方8%~15%）4.止盈价（上方15%~30%）5.风险收益比 6.组合整体风险评级（低/中/高）。"
    "如果当前市场是熊市或震荡市，仓位应比牛市更低。"
)
TOOL_RESULT = (
    '{"total_exposure": 82686.0, "exposure_pct": "82.7%", "var_1day_95": 8087.03, '
    '"var_5day_95": 18083.15, "positions_count": 5, "cash": 17315.0, "total_value": 100001.0}'
)
TOOLS = [{
    "type": "function",
    "function": {
        "name": "portfolio_risk",
        "description": "计算当前持仓组合的总敞口、VaR 与持仓数量。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]

MSGS_WITH_TOOL = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": USER},
    {"role": "assistant", "content": "", "tool_calls": [{
        "id": "call_1", "type": "function",
        "function": {"name": "portfolio_risk", "arguments": "{}"},
    }]},
    {"role": "tool", "tool_call_id": "call_1", "content": TOOL_RESULT},
]


def run(tag, msgs, max_tokens, effort="none", with_tools=True):
    payload = {
        "model": MODEL, "messages": msgs, "max_tokens": max_tokens,
        "temperature": 0.3, "keep_alive": "20m",
    }
    if effort is not None:
        payload["reasoning_effort"] = effort
    if with_tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"
    t0 = time.time()
    r = requests.post(BASE, headers=HEAD, json=payload, timeout=900)
    dt = time.time() - t0
    if r.status_code != 200:
        print(f"{tag:38s} http={r.status_code} {dt:5.1f}s {r.text[:110]}")
        return
    js = r.json()
    ch = js.get("choices", [{}])[0]
    msg = ch.get("message", {}) or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    tc = msg.get("tool_calls") or []
    usage = js.get("usage", {})
    ok = bool(tc) or len(content) > 10
    print(
        f"{tag:38s} {dt:6.1f}s finish={str(ch.get('finish_reason')):9s} content={len(content):4d} "
        f"reason={len(reasoning):4d} tools={len(tc)} comp_tok={usage.get('completion_tokens')} "
        f"-> {'OK' if ok else '*** EMPTY(流水线会中止) ***'}"
    )
    if content:
        print(f"    {content[:70]!r}")


print("### A. 无工具的第二轮（CrewAI 强制作答时的形状）")
run("A1 无工具 mt=1024", MSGS_WITH_TOOL, 1024, with_tools=False)
run("A2 无工具 mt=3072", MSGS_WITH_TOOL, 3072, with_tools=False)

print("\n### B. 带工具的第二轮")
run("B1 有工具 mt=1024", MSGS_WITH_TOOL, 1024)
run("B2 有工具 mt=3072", MSGS_WITH_TOOL, 3072)

print("\n### C. 对照：reasoning_effort 档位（无工具 mt=3072）")
run("C1 effort=low", MSGS_WITH_TOOL, 3072, effort="low", with_tools=False)
run("C2 effort 不传", MSGS_WITH_TOOL, 3072, effort=None, with_tools=False)

print("\n### D. 最短路径对照（无工具历史，只要报告）")
run("D1 单轮 mt=1024", [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}], 1024, with_tools=False)
