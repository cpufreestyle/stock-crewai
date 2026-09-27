"""探针：确认 CrewAI 的 LLM.call() 是否把 reasoning_effort 带进真实 HTTP 请求体。
拦截 openai SDK 的 chat.completions.create，打印出参后抛异常终止（不等模型跑完）。
"""
import os, sys, json, traceback
from dotenv import load_dotenv
load_dotenv()

import openai.resources.chat.completions as comp_mod

CAPTURED = []

class _Stop(Exception):
    pass

_orig_sync = comp_mod.Completions.create

def _spy_sync(self, *a, **kw):
    CAPTURED.append(kw)
    raise _Stop()

comp_mod.Completions.create = _spy_sync

try:
    import litellm
    litellm.suppress_debug_info = True
except Exception:
    pass

from agents.llm import get_llm

llm = get_llm()
print("LLM class:", type(llm).__name__)
print("reasoning_effort attr:", getattr(llm, "reasoning_effort", "<无此属性>"))
print("is_litellm:", getattr(llm, "is_litellm", "<无>"))
print("max_tokens:", getattr(llm, "max_tokens", None))

try:
    llm.call([{"role": "user", "content": "hi"}])
except _Stop:
    pass
except Exception as e:
    print("call raised:", type(e).__name__, str(e)[:200])

print("=== 拦截到 %d 次 create() ===" % len(CAPTURED))
for i, kw in enumerate(CAPTURED):
    slim = {k: v for k, v in kw.items() if k not in ("messages", "extra_headers", "timeout")}
    print(json.dumps(slim, ensure_ascii=False, default=str))
    print("  keys:", sorted(kw.keys()))
    msgs = kw.get("messages")
    if msgs:
        print("  n_messages:", len(msgs))
