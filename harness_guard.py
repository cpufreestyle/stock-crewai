#!/usr/bin/env python3
"""
Stock-CrewAI Claude Harness 健康监控

监控本地 Claude Harness (Codex) 是否运行，
并在需要时自动重启。
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
HARNESS_DIR = PROJECT_ROOT / "harness"
HEALTH_FILE = PROJECT_ROOT / "wiki" / "projects" / "claude-harness-health.md"


def check_harness_running() -> bool:
    """检查 Claude Harness (Codex) 是否在运行
    
    codex 是 .ps1 脚本，通过 PowerShell 启动 node.exe 运行。
    检查方法：是否有 powershell 进程的命令行包含 "codex"。
    """
    try:
        # 检查是否有 codex 相关的 PowerShell 进程（通过命令行匹配）
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -match 'codex' } | Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True,
            text=True,
            timeout=5
        )
        count = result.stdout.strip()
        if count and int(count) > 0:
            return True
        return False
    except Exception:
        # fallback: 检查 process list
        import subprocess
        result = subprocess.run(
            ["tasklist", "/V"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "codex" in result.stdout.lower()


def get_harness_processes() -> list:
    """获取所有相关进程"""
    processes = []
    # 查找包含 codex 的 powershell 进程
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -match 'codex' } | ForEach-Object { $_.ProcessId }"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            processes.append("codex (powershell)")
    except Exception:
        pass
    return processes


def write_health_status(status: str, message: str):
    """写入健康状态文件"""
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    content = f"""# Claude Harness 健康状态

**状态**: {'✅ 正常运行' if status == 'running' else '❌ 未运行'}

**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**消息**: {message}

**活动进程**: {', '.join(get_harness_processes()) if get_harness_processes() else '无'}

---
自动生成 by harness_guard.py
"""
    
    HEALTH_FILE.write_text(content, encoding='utf-8')
    print(f"[harness_guard] {status.upper()}: {message}")


def main():
    """主函数"""
    print("[harness_guard] Stock-CrewAI Harness 健康检查")
    print(f"[harness_guard] 项目: {PROJECT_ROOT}")
    
    is_running = check_harness_running()
    
    if is_running:
        write_health_status("running", "Claude Harness 正在运行")
        return 0
    else:
        write_health_status("stopped", "Claude Harness 未运行，需要手动启动")
        print("[harness_guard] 提示: 运行 'codex' 或 'claude' 启动 Harness")
        return 1


if __name__ == "__main__":
    sys.exit(main())
