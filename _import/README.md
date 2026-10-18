
# 从 origin/master 取出的、本地历史中没有的功能模块

## 为什么有这个目录

这个仓库有**两条无关的历史**（`git merge-base master origin/master` 为空）：

- `origin/master`：更早的原始版本，含实盘交易相关的功能模块。
- 本地 `master`：从 `70eb3ec Initial import` 开始的干净重导入，是重构后的结构。

本地重导入时**没有带上**下面这些模块，且本地代码里没有任何地方引用它们
（`git grep` 全仓零命中）。也就是说这些功能在本地版本里是彻底缺失的，
不是被改名或重构掉。

本目录把这些模块**原样**放在这里（未改一个字节），目的是让差异可审查、
不丢失。它们**不在 import 路径上**，不会被任何代码加载。

## 清单

| 文件 | 来源提交 | 作用 |
|---|---|---|
| `gm_broker.py` | `bdf0022` | 掘金量化仿真平台接入（双轨同步参与绩效排名） |
| `gm_sync_worker.py` | `bdf0022` | 掘金同步的工作线程 |
| `trade_guards.py` | `36a62aa` | 实盘交易防线（熔断接线/价格校验/确认降级） |
| `signal_dedup.py` | `1a2f50a` | 交易信号去重 |
| `alert.py` | `1a2f50a` | 监控告警（Server酱/Webhook） |
| `strategy_momentum.py` | — | 动量策略（本地已归档到 `_quarantine/2026-10-05/dead-modules/`） |
| `db.py` | `86ef338` | SQLite 迁移（本地已归档， portfolio_tracker 改为双写） |

对应的测试在 `tests/` 下。

## 待决

是否把这些功能接回主线，需要用户拍板：

1. 本地流水线已改为「只出建议、不落账」（第十六节，两道防线 +
   `ALLOW_AGENT_TRADING` 总开关默认拒绝）。接回实盘模块等于重新打开一条
   会真实下单的路径，与当前定位冲突。
2. `strategy_momentum.py` 和 `db.py` 在本地是被**主动归档**的（零引用死代码），
   接回来要先解释当初为什么归档。

在拍板之前，本目录只作为取证材料存在。
