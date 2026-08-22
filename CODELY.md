

## Codely Structured Memories

### User

### Feedback
- [2026-08-15 23:18:53] 在 Windows PowerShell 5.1 下编辑 UTF-8 文件必须用 [System.IO.File]::ReadAllText/WriteAllText 显式 UTF8（或 Get-Content -Raw -Encoding UTF8），直接 Get-Content/Set-Content 会按 ANSI 读写导致中文乱码（2026-08-15 曾把 README_VIRTUAL.md 写坏，靠 git checkout 恢复）。**Why:** PS5.1 默认编码不是 UTF-8。**How to apply:** 本机所有 PowerShell 文本替换操作。

### Project
- [2026-08-16 00:12:45] [2026-08-16 00:15] stock-crewai 活跃入口：main.py（统一入口 --test/--dashboard）、run_virtual_v4.py（虚拟盘，run_loop.bat/docker-compose 调度）、crew.py（LLM 分析写 result_latest.md）、web_dashboard.py；agents/ 为唯一 Agent 包（根 agents.py/tasks.py/agents_pkg 已于 2026-08-15 清理）。state.db/stock_crewai.db/trade_log.json 等为运行时数据，已脱离 git 跟踪。**Why:** 多入口并存曾导致误判与遗留代码堆积。**How to apply:** 改动入口/调度前先核对此清单；勿再引入版本化副本（如 run_virtual_v5）。掘金仿真对接（2026-08-16 bdf0022）：gm_broker.py 队列入队+派发、gm_sync_worker.py 跑在 .gmenv（Python 3.10 + gmtrade，因 gmtrade 无 cp311+ wheel）；挂钩在 portfolio_tracker.update_position。

### Reference

