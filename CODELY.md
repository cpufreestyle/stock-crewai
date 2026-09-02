

## Codely Structured Memories

### User

### Feedback
- [2026-08-15 23:18:53] 在 Windows PowerShell 5.1 下编辑 UTF-8 文件必须用 [System.IO.File]::ReadAllText/WriteAllText 显式 UTF8（或 Get-Content -Raw -Encoding UTF8），直接 Get-Content/Set-Content 会按 ANSI 读写导致中文乱码（2026-08-15 曾把 README_VIRTUAL.md 写坏，靠 git checkout 恢复）。**Why:** PS5.1 默认编码不是 UTF-8。**How to apply:** 本机所有 PowerShell 文本替换操作。
- [2026-08-28 00:12:34] PowerShell 中 git commit -m 的 here-string（@'...'@）内含英文双引号时参数解析会碎裂（2026-08-28 曾致 commit 静默失败，仅 add 未 commit）。**Why:** 经工具传递的 PS 命令对 here-string + 引号组合解析不稳定。**How to apply:** 复杂/多行提交信息先写入 UTF-8 临时文件再 `git commit -F file`；提交后必须 git log 确认成功。

### Project
- [2026-08-27 23:54:43] [2026-08-27 23:55] stock-crewai 活跃入口：main.py（--test/--dashboard）、run_virtual_v4.py（虚拟盘，run_loop.bat/docker-compose 调度）、crew.py（LLM 分析）、web_dashboard.py。已清理的死代码：agents.py、tasks.py、agents_pkg/、crew_simple.py、virtual_trader.py、run_virtual v1-v3。agents/ 为唯一 Agent 包。state.db/stock_crewai.db/trade_log.json 已脱离 git 跟踪。掘金仿真对接：gm_broker.py（队列）+ gm_sync_worker.py（.gmenv/Python 3.10+gmtrade，因无 cp311+ wheel）；挂钩在 portfolio_tracker.update_position。**Why:** 多入口/遗留副本曾导致误判与代码堆积。**How to apply:** 改动入口前核对此清单；勿再引入版本化副本。
- [2026-09-02 15:16:33] [2026-09-02 15:20] 本机默认 python 已漂移到 3.13（项目依赖在 3.11 用户目录），stock-crewai 所有命令必须用 `py -3.11` 显式指定；run_loop.bat 已修复为 `D:\Program Files\Python311\python.exe`（原 C 盘路径不存在，循环模式曾静默损坏）。实盘防线（2026-09-02 36a62aa）：trade_guards.py 统一熔断+价格校验（涨跌停±10/20%、stale quote 偏离>5% 拒绝），接入 run_virtual_v4 与 trade_tools；RealTrader._confirm 非交互模式拒绝下单+微信告警。**Why:** PATH 漂移曾致生产入口损坏；实盘前防线缺失。**How to apply:** 会话中跑测试/脚本一律 py -3.11；改动交易路径须过 trade_guards。

### Reference

