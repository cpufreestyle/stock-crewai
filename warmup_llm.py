# -*- coding: utf-8 -*-
"""开机/手动预热本地模型：一次真实推理，确认 0.33.2 + cuda_v12 + num_ctx 就绪。"""
import json, os, sys, urllib.request, urllib.error
sys.path.insert(0, r"D:\aishare\repo\stock-crewai-master")
from dotenv import load_dotenv
load_dotenv(r"D:\aishare\repo\stock-crewai-master\.env")

model = os.getenv("MODEL_NAME", "qwen3.8-gsq-rco-iq3s")
body = {"model": model, "messages": [{"role": "user", "content": "回复OK两个字"}],
        "stream": False, "reasoning_effort": "none"}
req = urllib.request.Request("http://127.0.0.1:11434/v1/chat/completions",
                             data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
        print("WARMUP OK:", d["choices"][0]["message"]["content"].strip()[:40])
except urllib.error.HTTPError as e:
    print("WARMUP HTTP", e.code, e.read().decode()[:200]); sys.exit(1)
except Exception as e:
    print("WARMUP ERR", type(e).__name__, e); sys.exit(1)
