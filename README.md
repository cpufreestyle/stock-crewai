# Stock CrewAI - 多智能体量化交易系统（本地 LLM 版）

基于 CrewAI 框架的 A股智能交易系统，8 个专业 Agent 协同完成
市场分析 → 选股 → 风控 → 交易 → 审核全流程，默认跑在**本地 Ollama 模型**
（qwen3.8-gsq-rco-iq3s，27B / IQ3_S 量化，约 11.8GB）上，零 API 费用、数据不出本机。

## ✨ 核心特性

- **8 智能体协同**：MarketWatcher / Sentiment / Researcher / Risk / Rebalancer /
  Trader / Backtest / Review，顺序流水线，任务间共享市场状态与持仓上下文
- **本地推理**：Ollama OpenAI 兼容端点（`http://127.0.0.1:11434/v1`），
  `LLM_REASONING_EFFORT=none` 关闭 thinking token，单轮约 60 分钟（20 token/s 量级）
- **结构化交易计划**：交易/再平衡任务输出机器可读 JSON（`trading_plan.py`），
  解析失败自动回退旧版自由文本正则，不丢单
- **LLM 响应缓存**：`llm_cache.py` 磁盘缓存，设 `LLM_CACHE_TTL=<秒>` 启用，
  key 覆盖全量 messages，debug 重跑零成本
- **全自动运维**：开机自启链 + 工作日 15:35 计划任务，**跑完自动 `ollama stop` 卸载模型**，
  把 12G+ 显存还给桌面

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置 `.env`（本地 Ollama 路线，默认值即可直接用）
```env
OPENAI_API_KEY=ollama            # 本地模型不校验，占位即可
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
MODEL_NAME=qwen3.8-gsq-rco-iq3s
LLM_REASONING_EFFORT=none        # 必填：不关 thinking 会吃光 token
LLM_MAX_TOKENS=3072
AGENT_MAX_ITER=8
LLM_TIMEOUT=600
LLM_CACHE_TTL=3600               # 可选：>0 启用响应缓存
```
云端备选（StepFun / OpenRouter / DashScope）：改 `OPENAI_BASE_URL` + `MODEL_NAME` +
自己的 key 即可，代码零改动。

### 3. 运行
```bash
# 单次手动运行（跑完自动 ollama stop 卸载模型）
python run_crew_then_release.py

# 预热模型（验证本地推理链路）
python warmup_llm.py

# Web 看板（默认 5000 端口，见 web_dashboard.py）
python web_dashboard.py
```

**预期执行时间**：8 Agent 顺序执行约 60 分钟；崩溃排查优先看 `logs/scheduled-run-*.log`。

## 🔄 开机自启与定时运行

开机后由 `stock-crewai-autostart.vbs`（无窗口）拉起 `start_local_stack.ps1`，依次完成：

1. 杀掉 Ollama 托盘（防止自动升级到会崩 GPU 的 0.34.x，锁定 0.33.2 + cuda_v12）
2. 校准模型参数 `num_ctx=16384`（32768 在 16G 显存上必 OOM）
3. 启动 `ollama serve` 并预热模型（`warmup_llm.py`，失败自愈重试）
4. 注册计划任务 `stock-crewai-daily-run`：工作日 15:35（`AUTORUN_HHMM` 可覆盖）

到点由 `run_crew_scheduled.vbs` → `run_crew_then_release.py` 执行一轮分析，
带防重入检查，结束后自动 `ollama stop` 卸载模型。
手动补跑/改时间：`powershell -File ensure_run_schedule.ps1`。

运维细节、故障案例（GPU 崩溃、模型导入等）记录在 [HANDOVER.md](HANDOVER.md)。

## 📁 项目结构

```
stock-crewai/
├── crew.py                    # 主编排（8 Agent 工作流 + 结构化解析）
├── agents/                    # Agent 定义（agents/__init__.py 汇总导出）
├── tasks.py                   # 任务定义（含 JSON 输出指令）
├── trading_plan.py            # 结构化交易计划 schema/解析/渲染
├── llm_cache.py               # LLM 磁盘响应缓存（LLM_CACHE_TTL 控制）
├── config.py                  # 交易/风控/缓存参数
├── data_fetcher.py            # 行情数据（新浪+腾讯，akshare 新闻接口已坏）
├── portfolio_tracker.py       # 持仓管理
├── recommendation_tracker.py  # 推荐追踪
├── risk_manager.py            # 风险管理
├── backtest.py                # 回测框架
├── run_crew_then_release.py   # 计划任务包装：防重入 + 自记日志 + 跑完卸模型
├── start_local_stack.ps1      # 开机自启守卫（锁版本/校准参数/注册计划任务）
├── ensure_run_schedule.ps1    # 单独刷新 15:35 计划任务
├── warmup_llm.py              # 模型预热
├── web_dashboard.py           # Web 看板
├── core/  workflows/  tools/  # 事件总线/编排/工具集
├── data_sources/             # 数据获取实现（下方门面再导出）
└── tests/                     # pytest 测试套件（56 个用例）
```

## ⚙️ 配置说明

交易参数集中在 `config.py`：`MAX_POSITIONS=5`、`SINGLE_POSITION_RATIO=0.20`、
`STOP_LOSS_RATIO=0.92`（-8%）、`TAKE_PROFIT_RATIO=1.20`（+20%）、
`MIN_TECH_SCORE=60`、ATR 动态止损止盈等，改动前先跑测试。

LLM 相关环境变量见上文 `.env`；改模型只动 `MODEL_NAME` 与 `OPENAI_BASE_URL`。

## 🧪 测试

```bash
pytest tests/ -q        # 56 个用例：config/api_cache/交易计划/LLM 缓存/熔断开关等
```

CI（`.github/workflows/ci.yml`）在 push/PR 时自动运行同一套测试。

## 📝 更新日志

### v4.4.0 (2026-10-04) - 代码精简与模块化
- `data_fetcher.py`（716 行）拆分为 `data_sources/` 包，`data_fetcher.py` 变为再导出门面，调用方不变
- 回撤/夏普计算合并到 `quant_metrics.py`，顺带修掉 peak=0 时的 `ZeroDivisionError`
- 删除全仓零调用点的死代码与未使用导入（见 HANDOVER 第十八节）
- 补齐 `circuit_breaker.py` 缺失的 `CIRCUIT_BREAKER_*` 配置项（该模块此前无法 import）

### v4.3.0 (2026-09-27) - 本地 Ollama 化 + 可维护性整改
- 切换本地推理：Ollama + qwen3.8-gsq-rco-iq3s，`reasoning_effort=none`
- 新增 `trading_plan.py` 结构化计划（解析失败回退旧正则）与 `llm_cache.py` 缓存
- 开机自启链重写：工作日 15:35 计划任务 + 跑完自动卸载模型
- 仓库同步：清理运行时产物与死代码，`tests/` 纳入 git，48 个测试

### v4.2.0 (2026-06-10) - Complete Quantitative Trading System
- 5 Agent → 8 Agent，新增情绪/组合/回测/审核 Agent

### v4.1.1 (2026-06-09) - 之前的 LM Studio 直连版本（已归档）

## 🤝 贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. `pytest tests/ -q` 通过后提交 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支并开启 Pull Request

## 📄 License

MIT License

## 🙏 致谢

- [CrewAI](https://github.com/crewAIInc/crewAI) - 多智能体框架
- [Ollama](https://ollama.com/) - 本地 LLM 推理
- [ISTA-DASLab GSQ-RCO](https://huggingface.co/ISTA-DASLab) - 量化模型
- 新浪财经 / 腾讯财经 API - 行情数据

---

## ⚠️ 风险警告

- 本项目为 **研究与学习目的**，不构成投资建议
- 股市有风险，投资需谨慎
- 实际交易前请充分验证策略有效性
- 使用者需自行承担所有风险
