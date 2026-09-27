"""端到端前的最后一道验证：走 CrewAI 真实调用链（get_llm().call），
确认 reasoning_effort 经 additional_params 生效后，风控那一轮能拿到非空最终答案。
"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

from agents.llm import get_llm

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
MSGS_WITH_TOOL = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": USER},
    {"role": "assistant", "content": "", "tool_calls": [{
        "id": "call_1", "type": "function",
        "function": {"name": "portfolio_risk", "arguments": "{}"},
    }]},
    {"role": "tool", "tool_call_id": "call_1", "content": TOOL_RESULT},
]

llm = get_llm()
t0 = time.time()
ans = llm.call(MSGS_WITH_TOOL)
dt = time.time() - t0
text = ans if isinstance(ans, str) else getattr(ans, "content", str(ans))
print(f"\n耗时 {dt:.1f}s  返回类型={type(ans).__name__}  长度={len(text)}")
print("首 200 字:", text[:200].replace("\n", " "))
print("尾 120 字:", text[-120:].replace("\n", " "))
print("\n结论:", "PASS 非空" if len(text) > 200 else "*** FAIL 仍为空/过短 ***")
