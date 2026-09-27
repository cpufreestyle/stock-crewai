# -*- coding: utf-8 -*-
"""跑完 crew.py 后自动卸载模型，把 12G+ 显存还给桌面。

两层保障：
1. 模型 keep_alive（服务端默认 5 分钟，守卫脚本里显式设 OLLAMA_KEEP_ALIVE=5m），
   空闲超时后 ollama 自己卸载；
2. 本包装器在 crew.py 退出后立即 ollama stop，不干等 5 分钟。

被 start_local_stack.ps1 调用；也可手动 python run_crew_then_release.py 使用。
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe")
MODEL = os.getenv("MODEL_NAME", "qwen3.8-gsq-rco-iq3s")


def release_model() -> None:
    try:
        r = subprocess.run(["ollama", "stop", MODEL], capture_output=True, text=True, timeout=120)
        print(f"[model-release] ollama stop {MODEL} rc={r.returncode}")
    except Exception as e:
        print(f"[model-release] failed: {e}")


def main() -> int:
    print(f"[model-release] launching crew.py ...")
    proc = subprocess.run([PYTHON, "-u", "crew.py"], cwd=REPO)
    print(f"[model-release] crew.py exited rc={proc.returncode}, releasing model ...")
    release_model()
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
