"""确认超上下文请求的真实错误，并实测 num_ctx 32768 的显存可行性。"""
import json
import subprocess
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:11434"
HEAD = {"Content-Type": "application/json", "Authorization": "Bearer ollama"}
FILLER = (
    "000001 平安银行(银行): 现价=11.75元 MA5=11.62 MA20=11.40 RSI=57；"
    "中兴通讯 000063(通信设备): 现价=32.17元 MA5=31.20 MA20=33.55 RSI=44；"
    "美的集团 000333(家电): 现价=86.26元 MA5=85.10 MA20=84.20 RSI=61。\n"
)
LONG = FILLER * 90 + "\n只用一句话结论：现在适合加仓吗？"


def vram():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    return out


def probe(model, repeat, max_tokens, tag, keep="20m"):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": FILLER * repeat + "\n只用一句话结论：现在适合加仓吗？"}],
        "max_tokens": max_tokens,
        "reasoning_effort": "none",
        "keep_alive": keep,
    }
    t0 = time.time()
    r = requests.post(f"{BASE}/v1/chat/completions", headers=HEAD, json=payload, timeout=900)
    dt = time.time() - t0
    print(f"[{tag}] http={r.status_code} {dt:.1f}s vram={vram()}")
    if r.status_code != 200:
        print("   BODY:", r.text[:400])
        return
    js = r.json()
    ch = js.get("choices", [{}])[0]
    print(f"   finish={ch.get('finish_reason')} usage={js.get('usage')} "
          f"content={repr((ch.get('message', {}) or {}).get('content', '')[:90])}")


print("### 1) q2 (num_ctx 8192) 收到 ~15k token prompt：看真实错误")
probe("qwen3.8:q2", 90, 128, "q2-15k")

print("\n### 2) 卸载 q2")
requests.post(f"{BASE}/api/chat", json={"model": "qwen3.8:q2", "keep_alive": 0}, timeout=120)
time.sleep(3)
print("ps:", requests.get(f"{BASE}/api/ps", timeout=20).text[:120], "vram:", vram())

print("\n### 3) q2big (num_ctx 32768) 加载 + 短请求")
probe("qwen3.8:q2big", 1, 128, "q2big-load-short")

print("\n### 4) q2big 收到 ~15k token prompt")
probe("qwen3.8:q2big", 90, 128, "q2big-15k")

print("\n### 5) q2big 收到 ~28k token prompt（逼近上限）")
probe("qwen3.8:q2big", 170, 128, "q2big-28k")

print("\nps:", requests.get(f"{BASE}/api/ps", timeout=20).text[:400])
print("vram:", vram())
