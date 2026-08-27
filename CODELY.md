

## Codely Structured Memories

### User

### Feedback
- [2026-08-15 23:18:53] 在 Windows PowerShell 5.1 下编辑 UTF-8 文件必须用 [System.IO.File]::ReadAllText/WriteAllText 显式 UTF8（或 Get-Content -Raw -Encoding UTF8），直接 Get-Content/Set-Content 会按 ANSI 读写导致中文乱码（2026-08-15 曾把 README_VIRTUAL.md 写坏，靠 git checkout 恢复）。**Why:** PS5.1 默认编码不是 UTF-8。**How to apply:** 本机所有 PowerShell 文本替换操作。

### Project
- [2026-08-27 23:54:43] [2026-08-27 23:55] stock-crewai 活跃入口：main.py（--test/--dashboard）、run_virtual_v4.py（虚拟盘，run_loop.bat/docker-compose 调度）、crew.py（LLM 分析）、web_dashboard.py。已清理的死代码：agents.py、tasks.py、agents_pkg/、crew_simple.py、virtual_trader.py、run_virtual v1-v3。agents/ 为唯一 Agent 包。state.db/stock_crewai.db/trade_log.json 已脱离 git 跟踪。掘金仿真对接：gm_broker.py（队列）+ gm_sync_worker.py（.gmenv/Python 3.10+gmtrade，因无 cp311+ wheel）；挂钩在 portfolio_tracker.update_position。**Why:** 多入口/遗留副本曾导致误判与代码堆积。**How to apply:** 改动入口前核对此清单；勿再引入版本化副本。


### Reference

