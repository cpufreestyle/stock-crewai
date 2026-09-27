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
import time

REPO = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe")
MODEL = os.getenv("MODEL_NAME", "qwen3.8-gsq-rco-iq3s")


def release_model() -> None:
    try:
        r = subprocess.run(["ollama", "stop", MODEL], capture_output=True, text=True, timeout=120)
        print(f"[model-release] ollama stop {MODEL} rc={r.returncode}")
    except Exception as e:
        print(f"[model-release] failed: {e}")


def _other_crew_running() -> bool:
    """True if another crew.py / wrapper process is already running."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*crew.py*' -or $_.CommandLine -like '*run_crew_then_release*' } | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except Exception:
        return False
    pids = [int(x) for x in out.split() if x.strip().isdigit()]
    others = [p for p in pids if p != os.getpid()]
    if others:
        print(f"[model-release] another crew run already active (pid {others}), exit")
    return bool(others)


def main() -> int:
    if _other_crew_running():
        return 0
    # 计划任务里 vbs 以隐藏窗口拉起, stdout 无处可去, 自己落盘
    os.makedirs(os.path.join(REPO, "logs"), exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    log_path = os.path.join(REPO, "logs", f"scheduled-run-{stamp}.log")
    logf = open(log_path, "a", encoding="utf-8", buffering=1)

    def say(msg: str) -> None:
        line = f"[model-release] {msg}"
        try:
            logf.write(line + "\n")
        except OSError:
            pass
        print(line)

    say(f"launching crew.py, log={log_path}")
    with open(log_path, "a", encoding="utf-8", buffering=1) as out:
        proc = subprocess.Popen([PYTHON, "-u", "crew.py"], cwd=REPO, stdout=out, stderr=subprocess.STDOUT)
        proc.wait()
    say(f"crew.py exited rc={proc.returncode}, releasing model ...")
    release_model()
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
