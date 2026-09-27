# 交接文档：stock-crewai 七智能体端到端验证

> 生成时间：2026-09-19；最后更新：2026-09-26 20:10
> 背景：项目用 CrewAI 七智能体做 A 股投资分析。**模型端点由 `.env` 的 `OPENAI_BASE_URL` + `MODEL_NAME` 决定
> （`LLM_PROVIDER` 未设 → 走 `agents/llm.py` 的 OpenAI 兼容缺省分支），当前是 StepFun 云端 `step-5-preview` + `/step_plan/v1`**；
> 9/24 之前一直是本地 `qwen3.8:q2big`（Qwen3.8-27B-Q2_K 约 11GB，经 Ollama 的 `/v1`），
> 那套配置的完整取舍仍留在 `.env` 下半部注释里，回退只需解注释。
> 调用链两个时代共用：`agents/llm.py:get_llm()` → CrewAI(litellm)。
> 目标：把 `crew.py` 完整跑通端到端（行情→选股→情绪→回测→风险→交易→调仓→落盘 result_latest.md）。

---

## 当前状态（2026-09-26 20:10）

- **模型已换成本地 GSQ-RCO：`qwen3.8-gsq-rco-iq3s`（ISTA-DASLab/Qwen3.8-27B-GSQ-RCO IQ3_S）**，
  即用户 9/26 指定要下载部署的 gsq-rco。27B / 3.50bpw / task-lossless（README 口径 AIME25、
  LiveCodeBench 与 BF16 完全持平），文件 11,771,546,784 字节，`ollama show` 识别为 qwen35 架构、
  27B、原生 ctx 262144，参数层 num_ctx=32768，capabilities 含 tools。
  显存：空载常驻 14517/16380 MiB（100% GPU）。
- **下载通道**：huggingface.co 直连超时，走 `hf-mirror.com`（`curl -L -C -` 可续传；
  首次忘了加停滞检测挂死过一次，重启时须带 `--speed-limit 10240 --speed-time 60 --retry 10`）。
- **导入方式是零拷贝**：`ollama create` 会 3 倍空间峰值（源+COPY+verify），D 盘只剩 ~16G 时必败。
  实际做法：下载文件 → 算 sha256 → 移入 `blobs/sha256-<hash>` → 手写 params/config/manifest
  （params blob 内容 `{"num_ctx":32768}`）。已用 0.6B 小模型先行验证过同一流程再用于大文件。
- **端到端已跑通 3 轮，第 3 轮 7/7 任务全部真实产出**（详见第十一节）。前两轮暴露了
  "假成功"的新变种并已修复：风控/交易员逐只工具循环烧光 max_iter → 回显框架收尾提示语，
  且模型会退化成大面积 `@` 复读，把下游交易员/调仓一起毒化。
- 已修：`set_stop_loss` 永返 None 导致工具层 TypeError（实测 6 次）、`position_size`
  百分数/小数口径混用输出静默错值（`stop_loss_price=-348.35`、`position_pct=16665.1%`）。
- **9/26 深夜更新：run5 达成 7/7 全真实产出**，`trades_YYYYMM.json` 撕裂写已修（见 11.4/11.6）。
- StepFun 云端路线（`.env` 下半部注释）保留，但 `OPENAI_API_KEY` 仍是用户手动粘贴这一步，
  工具侧写密钥会被截断，别再用脚本写 key。

---

## 一、已验证可用（好消息，无需再验证）

| 能力 | 状态 | 证据 |
|---|---|---|
| `CrewAI → litellm → Ollama → qwen3.8:q2` 链路 | ✅ | smoke_test_crew.py 返回中文分析 |
| 真实行情抓取（akshare） | ✅ | 市场热度拿到涨停 40 家、板块涨跌幅真实数据 |
| 工具调用（market_heat / sector_rotation / backtest） | ✅ | 9/13 那次 run 中 4 次工具调用全部返回真实数据（平安银行 +6.15%、徐工 -13.05% 等） |
| 七智能体管线推进 | ✅ | 研究员已拿 10 只真实行情（中兴 32.17、美的 86.26…）并进入回测智能体 |
| 依赖（crewai 1.15.21 / litellm 1.100.1 / akshare / langchain_openai） | ✅ | 均已安装 |

**结论：模型能力、工具链、数据链全部打通。9/13 那次 run 跑到了回测智能体汇总阶段，只差最后落盘。**

---

## 二、原"硬阻塞"（GPU 加载 OOM）— 已由重启解除

9/19 16:59 重启后实测：模型可正常全量常驻 GPU，**不再是阻塞项**。

```
ollama ps   -> qwen3.8:q2big  size=13638177913  size_vram=13638177913  context_length=32768
nvidia-smi  -> 13461 / 16380 MiB（22.8k token prompt 下）
```

> 更正：原文"WDDM 假空闲导致分配不出 10.4GB 连续块"的判断成立，但它只是重启前的临时状态；
> 而"num_ctx 16384 会超出 16GB 显存导致卡死"的结论**是错的**——干净环境下 32768 都能全量进 GPU。

**新的运行时风险（实测）**：Ollama 服务进程会在无崩溃记录的情况下消失
（9/19 18:48:45 打完最后一次请求后进程退出，`server.log` 无异常、CrashDumps 无转储）。
长流水线开跑前务必先确认 `curl http://127.0.0.1:11434/api/version` 可通。
本次已改用干净环境手动拉起：`ollama.exe serve`（不再带失效的 `OLLAMA_GPU_LAYERS=0`），并设 `OLLAMA_KEEP_ALIVE=20m` 避免智能体之间反复重载（冷加载一次约 36s）。

---

## 三、真正的根因（已定位并修复）：不是 thinking，是上下文超限

9/13 run 在回测智能体汇总那次报：
```
ERROR:crewai.flow.runtime: Error executing listener call_llm_native_tools:
Invalid response from LLM call - None or empty.
```

**实测复现**（`probe_ctx.py`，模型 `qwen3.8:q2`，num_ctx 8192）：
```
http=400  0.5s
{"error":{"code":400,"message":"request (12081 tokens) exceeds the available context size (8192 tokens),
 try increasing it","type":"exceed_context_size_error","n_prompt_tokens":12081,"n_ctx":8192}}
```

因果链：七智能体顺序管线把「前序任务输出 + 工具结果 + 10 只股票行情」逐轮累积进 prompt，
单次请求实测 12k~15k token → 超出 `num_ctx=8192` → Ollama **直接 400 拒绝**（不是截断）→
CrewAI 把失败响应当成"空 content"抛 `ValueError` → 整条流水线中止、不落盘。

 CrewAI 默认 `max_iter=25`（`crewai/agents/agent_builder/base_agent.py:304`）会让这个累积更快发生，
且本地解码只有约 20 token/s（实测 49.9 ms/token），25 轮完全不可承受。

**已实施修复**（全部经 preflight 验证）：
| 改动 | 位置 | 依据 |
|---|---|---|
| 模型切到 `qwen3.8:q2big`（同一 GGUF，num_ctx 32768） | `.env` | 12k~23k token prompt 实测 HTTP 200、显存 13.5/16GB |
| `LLM_REASONING_EFFORT=none` | `.env` | 工具调用 1.1s vs low 3.8s，content 必非空、finish=stop |
| `LLM_MAX_TOKENS=3072` | `.env` | 实测 1024 时报告全部 `finish=length` 被截断；3072 才 `finish=stop` 自然写完 |
| `AGENT_MAX_ITER=4` | `.env` + `core/agent_base.py:create_crewai_agent` | 收敛迭代轮数，控耗时与 prompt 规模 |
| `LLM_TIMEOUT=600` | `.env` | 留足本地推理时间 |

### 3.1 第二个根因（9/24 定位）：`reasoning_effort` 被 CrewAI 静默丢弃 —— 这才是"空响应"的真凶

上面那组配置改完后，`crew_run5` **仍然**在风控任务 8/8 空响应中止，而这次 Ollama 侧**全是 HTTP 200**、
prompt 最大 5884 token（远未超限）。说明 Cause A 之外另有独立成因（Cause B）。

用探针拦截 openai SDK 的 `chat.completions.create()`，拿到 CrewAI 实际发出的请求体：

```
keys: ['extra_headers', 'max_tokens', 'messages', 'model', 'temperature']   # 没有 reasoning_effort
```

原因在这一行（`crewai/llms/providers/openai/completion.py:1930`）：

```python
# Handle o1 model specific parameters
if self.is_o1_model and self.reasoning_effort:
    params["reasoning_effort"] = self.reasoning_effort
```

CrewAI 原生 OpenAI provider 把 `reasoning_effort` 当成 **o1 专属参数**，只有模型名含 "o1" 才下发。
`qwen3.8:q2big` 不是 o1 → 参数被静默丢掉 → Ollama 按 GGUF capability 仍以 `thinking=1` 起跑 →
thinking token 正好吃满 `max_tokens` → `content=""` + `finish=length` → CrewAI 抛
`Invalid response from LLM call - None or empty.` → 流水线中止。

**为什么之前手工测 `reasoning_effort=none` 是好的**：`repro_final.py` 走裸 HTTP 自己拼 body，
参数真的发出去了；而 `LLM(reasoning_effort=...)` 构造的是 pydantic 字段，`is_o1_model`
又在 validator 里被 `"o1" in model.lower()` 覆盖（`completion.py:386`），构造时改不动。
两条路径不等价，这是当时误判"thinking 与故障无关"的来源。

**修复**（`agents/llm.py`，不动 site-packages）：把同一个值再塞进 `additional_params`，
它在 `completion.py:1908` 是**原样透传**进 `create()` 的，不受 `is_o1_model` 门控：

```python
kwargs["additional_params"] = {"reasoning_effort": reasoning_effort}
```

拦截复验：`keys` 里已含 `reasoning_effort`。真实调用链复验（`verify_crewai_path.py`，
风控那一轮的多轮 + 工具结果回填形状）：**114.8s、1748 字完整报告、自然收尾**，不再空。

> 教训：本地模型 + 第三方框架时，"配置项在 `.env` 里写了" ≠ "参数进了 HTTP 请求体"。
> 判据要落在被拦截的实际出参上。


---

## 四、两处"隐蔽改动"，接手前必须知道

1. **GGUF blob 被就地二进制打过补丁**（改默认不思考）—— 9/24 复核：**这个补丁并不解决问题，且已被真正的修复取代**
   文件：`D:\.ollama\models\blobs\sha256-29e5614f...`（`q2`/`q2big`/`latest` 共用这一份权重）
   偏移 10936727，等长替换 Jinja 片段：
   `enable_thinking is undefined or enable_thinking is true` → `enable_thinking is defined and enable_thinking is true `
   实测 `reasoning_len=0`，但**这不等于 thinking 关掉了**：Ollama 的 thinking 开关来自 GGUF capability
   （server 日志 `init: chat template, thinking = 1`、`common_reaso: activated` 仍出现），
   只是模板没把 thinking 分支渲染出来而已。真正让 content 变非空的是 3.1 节的 `additional_params`。
   副作用仍在：**blob 的 sha256 已与文件名不符**，Ollama 做完整性校验或重新拉取时会不一致。
   回滚方式：按原串反向替换（`patch_tmpl.py` 可复用）。建议接手后回滚，除非有新的保留理由。


2. **site-packages 里的 CrewAI 被改过**（`crewai/utilities/agent_utils.py`）
   加了空响应自动重试：`CREWAI_EMPTY_RETRIES`（默认 8 次，每次 sleep 3s）。
   `pip install/upgrade crewai` 会静默丢失这个补丁。
   注意：`max_iter` 耗尽后走 `handle_max_iterations_exceeded`（同文件 ~425 行）那条分支
   **不在这个重试保护范围内**，仍会直接抛 `Invalid response from LLM call - None or empty.`

---

## 五、历史遗留的无用功（避免重走）

原第五节建议的"做默认不思考模型"三条路径，实测结论：
- Ollama 确实拒绝带 `macro` 的用户自定义模板（`Modelfile.qwen38.notink` 建不出来）；
- 直接改 GGUF 模板可行（见上节），但**对空响应并无必要**，而且**没起作用**——thinking 由 GGUF capability 决定，模板改不掉；
- 9/24 更正：本节原写"空响应的真凶是 400 上下文超限，不是 thinking"，**这句话只对了一半**。
  上下文超限（Cause A）与 thinking 吃满预算（Cause B）是**两个独立成因**，
  都会以 `Invalid response from LLM call - None or empty.` 表现；当时只修了 A，所以 run5 仍中止。
  Cause B 的机制与修复见 3.1 节；
- `Modelfile.qwen38.thinkoff` / `Modelfile.qwen38.notink` 两个文件可以删。
  （9/26 处置：没删，连同其余 40 个实验产物一起进了 `_quarantine/2026-09-26/`，见 §八 第 3 项）


---

## 六、环境状态清单

**当前（9/26 起）= StepFun 云端**：`step-5-preview` @ `https://api.stepfun.com/step_plan/v1`，
无本地依赖、无显存约束；下面是切云端之前最后一次本地环境的快照，**回退 Ollama 时才用得上**。

- 模型 `qwen3.8:q2big`：✅ 当时**正在使用**，与 `q2` 同一份 GGUF，`num_ctx 32768`，22.8k token prompt 实测可用
- 模型 `qwen3.8:q2`：✅ 完好但 `num_ctx 8192` 已不够用，仅留作对照
- 模型 `qwen3.8:latest`：`TEMPLATE {{ .Prompt }}` 裸模板变体，无实际用途
- GPU：13461 / 16380 MiB（q2big + 22.8k prompt，全量在 GPU 上）
- Ollama 0.33.2：本次以干净环境手动 `ollama.exe serve` 拉起，`OLLAMA_KEEP_ALIVE=20m`
- litellm 1.100.1、crewai 1.15.21：✅ 已装；**注意 crewai 只装在 Python 3.12**
  （默认 `python` 是 3.14，直接 `python crew.py` 会 ModuleNotFoundError）
- 早前清理：已删死代码 `agents.py`、已删孤儿 blob `sha256-028a1d47`

---

## 七、本轮顺带修掉的 3 个数据正确性缺陷

都是"流水线不报错、但喂给模型的是空值/错值"的静默失效，比崩溃更危险：

| 缺陷 | 位置 | 现象 → 真因 | 验证 |
|---|---|---|---|
| 板块名与领涨股恒为空 | `data_fetcher.get_sector_performance` | `sector:""` `leading_stock:""` → 按 `"名称"` 取列，akshare 实际列名是 `板块`；且 `top_stock` 键从未被构造 | 修复后：陶瓷行业 +6.71% 领涨股 松发股份 +7.49% |
| 牛熊判断整体失效 | `get_market_regime` | `KeyError 'close'` → 主路径 `_sina_kline_direct` 返回中文列 `收盘`，代码写死取 `close` | 修复后：震荡市 / 置信度 40 |
| **牛熊判断用的是平安银行** | `_sina_kline_direct` 前缀规则 | `000001` 按个股规则拼成 `sz000001`，取到的是股价 11.7 而非上证指数 | 修复后 `sh000001` → 3911.87；个股路径回归无变化 |

第 3 条尤其要注意：修复前后都输出"震荡市"，**看起来一切正常**，但依据从"指数空头 -2.9%"被错成了"某银行股多头 +14.4%"。

---

## 八、下一步（1、2、5 已于 9/24 完成；第十节又补掉一项）

1. ✅ 定位并修复流水线中止根因（Cause A 上下文超限 + Cause B `reasoning_effort` 被静默丢弃，见 3.1）
2. ✅ 端到端重跑验证（见下节实测结果）
3. ✅ 待清理实验文件（9/26 已**改名隔离**，不是删除）：`ab_test.py`、`test_*.py`、`ctxlen_*`、
   `find_tmpl.py`、`patch_tmpl.py`、全部 `Modelfile.qwen38*`、`*_check.json`、旧 `crew_run*.log`、
   `smoke_ollama.*`、`probe_think*`、`repro_final.*` → 现在 `_quarantine/2026-09-26/`，
   分组清单和"为什么可以离开根目录"见该目录下的 `README.md`，取回就是把文件 `mv` 回去。
   **`crew_run6.log/.err` 保留在根目录**：第十节通篇按行号引用它。
   （**保留**：`verify_crewai_path.py` 端到端前 2 分钟自检、`probe_payload.py` 拦截实际请求体，
   这两个是 Cause B 这类静默失效的回归工具；另新增 `dry_run_offline.py`，
   零 LLM 调用地跑"数据层 → 任务装配 → prompt 体量"，几十秒且省 token，端到端前先跑它）
4. 建议后续优化（按收益排序）：
   - **风控/调仓任务的逐只工具循环**：情绪与回测已在 10.5 一并处理（前者禁用工具、后者改批量）。
     剩下的同形风险是 `stop_loss_advice`/`risk_reward`（按持仓逐只调用，run6 调了 10 次）
     和调仓的 5 个工具混用 —— `max_iter=4` 撑不住 5 只持仓各查一次。
     要么让这些工具支持一次多码，要么单独给这两个智能体放宽 `AGENT_MAX_ITER`
   - **调仓任务的写操作**：`execute_sell` 在分析循环里直接改 `portfolio.json`（10.4），
     是否改为"只出建议 + 人工确认后再记账"需用户拍板
   - ~~prompt 瘦身：`research_task` 同时注入市场分析与完整 `market_data`，实测单请求 5k token 里有重复~~
     **这条已过期**（9/24 19:40 复量）：`market_analysis` 现在只是 `CTX_REF_MARKET` 那句指代文案，
     不再是原始数据块。实测 7 个任务描述合计约 2633 token（`market_data` 本体 1590 字符 ≈ 800 token，
     只在任务 1 与任务 2 各出现一次），相对 `num_ctx=32768` 完全不构成压力，不值得再优化
   - 把 `CREWAI_EMPTY_RETRIES` 那份 site-packages 补丁改为本项目内的运行时 patch，避免 `pip` 升级即失效
   - 升级/重装 crewai 后**必须重跑 `verify_crewai_path.py`**：`additional_params` 这条透传路径
     是绕开 `is_o1_model` 门控的权宜之计，框架一改就可能再次静默失效
   - ~~数据工具返回空字段时应显式报错~~ ✅ 本轮已对 `fundamental_analysis` 与新闻段落实（10.3）
   - ~~回滚 3.1/GGUF 补丁~~ ✅ 已重建为内容寻址的干净 blob（第四节 1）

**耗时基线（9/24 实测）**：单次 LLM 调用 105~115s，解码稳定 20~21 token/s，
一次完整 7 任务管线约 60 分钟量级；`max_tokens=3072` 时报告才写得完（`finish=stop`）。


---

## 九、9/24 运行期事件（都不是代码 bug，但下一个坑必须知道）

### 9.1 模型库在 17:11 被外部清空（run6 中止的直接原因）

`crew_run6` 前 6 个任务全部正常产出，第 7 个任务报：

```
ValueError: Model qwen3.8:q2big not found: Error code: 404
{'error': {'message': "model 'qwen3.8:q2big' not found", 'type': 'not_found_error'}}
```

排查结论：**文件是 17:11 被直接从磁盘删掉的，不是 Ollama 干的**，依据：

| 检查 | 结果 |
|---|---|
| 服务端日志 `DELETE /api/delete` 调用 | **0 次** |
| 17:05–17:17 服务端任何 `level=` 事件 | **0 条**（只有 llama.cpp 的 slot 计时） |
| 16:59:06 启动时自检 | `total blobs: 4 / unused blobs removed: 0 / models=3` —— 当时库是好的 |
| 17:00:35 | 仍成功加载 `sha256-29e5614f`（前 6 个任务用的就是它） |
| `blobs` 目录 mtime | **2026-09-24 17:11**，11.8G 权重消失，只剩 3 个小 blob |

已排除的嫌疑：`ollama serve`（PID 30960 全程存活、日志无事件）、我这次的 `ollama create`（17:14 才启动）。
**未查明真凶**；同一分钟 `portfolio.json` 也被写过（那是 CrewAI 自己的线程，属正常）。
最可疑的方向是磁盘空间压力触发的某个清理动作——卷当时已经 98% 满。

> 这也顺手验证了第四节 1 的担忧方向，但**结论要修正**：Ollama 并没有因为
> "blob sha256 与文件名不符"去剪枝它（16:59 的自检明确 `removed: 0`，而且它照常加载了 6 个任务）。
> 那个补丁 blob 是跟着这次外部清空一起没的，现在重建出来的是内容寻址的干净 blob，隐患自然消除。

**教训（写死在流程里）**：开跑前先 `ollama list` 确认模型在，跑完再确认一次。
前 6 个任务花了约 40 分钟，如果 17:11 就检查过，不至于白烧。

### 9.2 `portfolio.json` 并发撕裂写（已修）

17:11 那次写入把 JSON 写成了 `…}.0\n}` 尾巴（`json.load` 抛 `Extra data: line 41 column 2`），
而 `load_portfolio()` 没有容错，下一次 run 会在 `[2/8] 检查止损止盈` 直接崩。

真因：`save_portfolio` 用 `open(PORTFOLIO_FILE, "w")`，而 CrewAI 内部走线程池
（traceback 里可见 `concurrent.futures.thread`）。同一进程内两个线程各持自己的文件偏移，
`"w"` 的 truncate 不会重置**别人**的偏移，交错刷新就把文件写撕裂。

修复（`portfolio_tracker.py`）：模块级 `RLock` + 先写 `portfolio.json.tmp` 再 `os.replace`，
且**读写都走同一把锁**。

> Windows 特别注意：`os.replace` 遇到"别人正用 `open()` 读着目标文件"会抛 `PermissionError`
> （Python 的开文件不带 `FILE_SHARE_DELETE`）。实测 8 写线程 × 4 直读线程 → 456 次 `PermissionError`；
> 改成读也走 `load_portfolio()` 后 → 写异常 0、读异常 0、无残留临时文件。
> **所以不要绕过 `load_portfolio` 直接 `open()` 读 `portfolio.json`。**

### 9.3 27B 模型导入的空间账

`ollama create … -f Modelfile.qwen38q2.local`（`FROM ./Qwen3.8-27B-Q2_K.gguf`）实测峰值占用：

```
源 blob sha256-028a1d47…   11.84 G   （已存在）
COPY<随机数>              11.84 G   （llama-quantize type=COPY 规范化）
verify 输出                11.84 G   （"verifying conversion" 阶段再写一份）
------------------------------------
峰值                       ≈ 35.5 G
```

D 盘 682G 用了 666G、清完残留只剩 17G，因此**失败于 `There is not enough space on the disk`**。
两次失败分别残留 `sha256-3828777537`(5.55G)、`sha256-2576215727`(5.55G)，已删除。
可回收空间里最大的一块是 `/d/Docker/wsl/disk/docker_data.vhdx`（25G，Docker Desktop 的 WSL 数据盘）：
`prune` + `wsl --shutdown` + `Optimize-VHD` 能腾出空间但会打断正在跑的容器，属高风险动作，**未执行**。

> 备选（未采用，按需评估）：`Modelfile.qwen38q2` 里那句 `FROM https://huggingface.co/bartowski/...`
> 会走网络下载，同样要落盘，省不掉空间，只是换个下载源。

---

## 十、run6 深挖：两个"假成功"任务与本轮修复（9/24 19:00–19:40）

### 10.1 研究员那一栏其实什么都没写

`crew_run6.log` 逐行核对后确认，第 2 个任务的交付物是空的：

| 证据 | 位置 | 内容 |
|---|---|---|
| 撞轮次上限 | `crew_run6.log:970` | `Maximum iterations reached. Requesting final answer.` |
| 强制收尾的输出 | `crew_run6.log:1002-1009` | Final Answer 正文 = `Now it's time you MUST give your absolute best final answer…` |
| 提示语出处 | `crewai/translations/en.json:47` → `utilities/agent_utils.py:407-410` | 框架把它作为 assistant 消息追加后再调一次 LLM |

也就是说：**27B 没有回答，而是把框架那句"你必须给出最终答案"原样复述了一遍**，
`research_task.output.raw` 因此只有这 3 行。下游全部被毒化——
`crew_run6.log:1123` 情绪分析师写"由于当前上下文中未提供具体的候选股票列表"，
**这句抱怨恰好证明 `Task.context` 注入是生效的**（它确实读到了上游输出，只是上游是空的）。

> 接线侧已复核完毕：`crew.py:219/239/245/248/249/257` 六处 `context=` 赋值正确，
> prompt 里 0 处 `{{…}}` 占位符，`Task.context=[…]` 赋值在 1.15.21 上可正常读写。
> **教训：任务链里"某个环节输出是空壳"不会报错，只会让下游开始客套。**

### 10.2 研究员为什么会烧光轮次：工具面 + 空壳数据

- `AGENT_MAX_ITER=4`（`.env:17`），而研究员在 run6 里发起了 **19 次工具调用**
  （10× `technical_analysis`、5× `fundamental_analysis`、4× `news_sentiment`）——
  它按"每只股票逐个查"的思路在跑，10 只候选必然超出 4 轮。
- 更糟的是 `fundamental_analysis` **是个空壳**：旧 `tools/stock_tools.py` 里 PE/PB/ROE/增速
  全部硬编码为 `None`，注释写着 `TODO: Implement real fundamental data fetching`，
  而它 `hasattr(df, 'get_fundamental_data')` 想调的函数**在 `data_fetcher.py` 里根本不存在**。
  所以那 5 次调用拿回来的是 5 张全 None 的空表，白烧约 4 轮 × 110s ≈ 7 分钟。
- 而任务描述要求的正是"估值/基本面/业绩超预期"——**prompt 要的数据，工具给不了**。

### 10.3 本轮改动（7 处，均已实测）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `data_fetcher.py` | 新增 `get_fundamental_batch()` / `get_fundamental_data()`：腾讯 `qt.gtimg.cn` 一次请求取全池 PE/PB/总市值；按单只 code 缓存 600s，**失败不写缓存**（否则一次网络抖动会让估值缺席 10 分钟） |
| 2 | `crew.py::prepare_market_data` | 每只候选行内联 `PE=… PB=… 总市值=…亿`；取不到写 `估值=暂缺(勿凭印象编造)` |
| 3 | `tools/stock_tools.py` | `fundamental_analysis` 接真实数据、支持逗号多码一次查、取不到返回显式 `error` 并附"勿再重复调用本工具"；删掉死代码 `_get_stock_name` |
| 4 | `core/agent_base.py` | `create_crewai_agent(tools=…)` 可覆写 CrewAI 侧工具面；省略时仍用子类全量工具（`workflows/daily_analysis.py` 的自定义编排路径依赖那份，不能动） |
| 5 | `crew.py` | 研究员 CrewAI 工具从 9 个收窄为 `[fundamental_analysis]`（数据已内联，留一个批量补充口） |
| 6 | `tasks.py::create_research_task` | 声明"数据已含 PE/PB/MA/RSI/板块，直接给 Final Answer"；确需补充**最多 1 次**工具且一次传多码；标"暂缺"的字段必须写"数据缺失"；催化剂只可引新闻，没有就写"无" |
| 7 | `crew.py` | 新闻源缺失时输出显式占位说明（原来是静默缺席） |

字段可信度：腾讯源 000001 的 `PE=5.05 / PB=0.47 / 总市值=2192.87亿` 与东财
`f115/f23/f20` 逐项一致（东财 `push2` 当时已开始间歇性拒连，故只作核对不作主源）。
实测 10/10 只全部取到，单只/多码/空码/不存在的码四条路径行为正确。

### 10.4 顺带查明：调仓任务空转的直接触发点是撕裂读

`crew_run6.log:2255-2274` 显示 `execute_sell` **真的写改了 `portfolio.json`**
（`Sold 中兴通讯(000063) 600 shares @ 33.60`），紧接着 `view_portfolio` 读到半写文件：
`{"error": "Extra data: line 41 column 2 (char 858)"}` → 重试 → `Maximum iterations reached`。
即 9.2 节的撕裂写**不只是崩数据，也是那次空转的起因**；读写同锁的修复应当同时解决两者。

> **未动但值得决策的一点**：调仓智能体在"分析"过程中直接下单改持仓（run6 有 4 次 `execute_sell`）。
> 这是纸面账户，但把不可逆的写操作放进一个 LLM 自由决定的工具循环里，风险由用户拍板：
> 要不要改成只出建议、由人工/`main.py` 确认后再生成成交记录。

### 10.5 同一形状的坑还有三处，一并修了

研究员不是孤例，"prompt 要的数据工具给不了 → 逐只调工具 → 烧光 max_iter"这个形状在别处也成立：

| 位置 | 问题 | 处理 |
|---|---|---|
| `tools/sentiment_tools.py` | 三个工具（`news_sentiment`/`social_sentiment`/`sentiment_score`）**全部落到同一条已故障的新闻接口**，`social_sentiment` 本来就是"占位实现"再转调新闻。run6 里情绪分析师交出的"分析框架模板"就是这么来的 | `create_sentiment_task` 改为用上下文里的量价字段（RSI/5日涨跌/涨跌停家数/板块涨跌）判情绪；工具本身在取不到数据时返回"接口故障、重试无用"而不是"未获取到新闻数据"。**9/26 补刀**：光改提示词不算数——离线装配实测 `sentiment tools` 仍有 3 个，现于 `crew.py` 直接 `create_crewai_agent(tools=[])`。另 `_stock_sentiment_score_tool` 在解析不到评分时**静默返回 50/100**（把"接口挂了"伪装成"情绪中性"喂给下游），这是它必须被摘掉的决定性理由 |
| `tools/stock_tools.py::BacktestTool` | 只接单只代码，3-5 只候选就要 3-5 轮 + 1 轮收尾 > `max_iter=4` | 支持逗号多码一次跑完（实测 3 只 1.4s，对应省下 2-4 轮 ≈ 4-8 分钟）；`create_backtest_task` 同步写明"一次调用传全部候选" |
| `backtest.py::multi_strategy_backtest` | 每种策略的 `最大回撤`/`胜率` **硬编码为 "N/A"**，而 `当前持仓` 写的是 `收益率>0`（把盈亏当成了持仓状态）——同 10.2 的"静默空字段" | 由各自权益曲线与成交记录算出真实回撤/胜率；无平仓交易时写"无平仓交易"而不是 N/A；持仓取循环结束时的真实仓位 |

改后实测（000333）：买入持有 回撤 9.05%、均线策略 胜率 33.3% 回撤 7.49%、RSI 策略无平仓交易。

### 10.6 已知坏数据源（不是本项目代码）

`akshare 1.18.94` 的 `stock_news_em()` 抛 `ArrowInvalid: Invalid regular expression: invalid escape sequence: \u`，
带不带 `symbol` 都一样 → `prepare_market_data` 的新闻段常年为空，情绪三工具也因此全部空转。
升级 akshare 会牵动其它接口，故未动；现在缺口会显式告知模型，避免它凭空编"政策利好"。

### 10.7 本轮改动的验证边界

已验：`py_compile` 全通过；估值抓取 10/10、基本面工具四条路径、回测批量与真实回撤/胜率、
研究员工具面（1 vs 9）、`Task.context` 赋值均实测。
**未验**：端到端真实跑。9/26 起阻塞点从"9.3 的空间"变成"`.env` 里没人能替我粘的密钥"
（见"当前状态"）。所以"研究员不再撞轮次"目前是**推断**而非**观测**——
下一次 run 第一件事就是看 `crew_run*.log` 里有没有 `Maximum iterations reached`，
以及研究员的 Final Answer 是不是还在回显那句英文。

---

## 十一、9/26 模型切换（本地 GSQ-RCO）与端到端 3 轮实测

### 11.1 换型与零拷贝导入

- 选型：`ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF` 的 `Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`
  （11,771,546,784 字节）。同仓库另有 IQ2_XS/IQ2_S/IQ3_XXS（8.4/9.3/10.1G，README 口径）可换，
  IQ3_S 是 README 标注的 task-lossless 档。基座与原 `Qwen3.8-27B-Q2_K` 相同。
- 残留：项目根目录 `Qwen3.8-27B-Q2_K.gguf`（11.84G，硬链接数 1，q2big 的最后副本）未删，
  D 盘余量因此只剩 ~4.3G。要删请用户确认——删了旧模型就再也回不去了。
- 导入命令等价物（手工版，零拷贝，已验证 3 次）：
  ```powershell
  $sha = (Get-FileHash -Algorithm SHA256 <gguf>).Hash.ToLower()
  Rename-Item <gguf> "D:\.ollama\models\blobs\sha256-$sha"
  # params blob 内容：{"num_ctx":32768}（按字节 sha256 命名后写入 blobs/）
  # config blob 内容：{"model_format":"gguf","model_family":"qwen3","model_families":["qwen3"],
  #   "model_type":"27B","file_type":"IQ3_S","architecture":"amd64","os":"linux",
  #   "rootfs":{"type":"layers","diff_ids":["sha256:<gguf-sha>"]}}
  # manifest（manifests/registry.ollama.ai/library/qwen3.8-gsq-rco-iq3s/latest）：
  # config + layers=[model, params]，digest/size 均按内容寻址
  ```
- 端点验证：`/v1/chat/completions` 冷启 57s（含 36s 加载），`reasoning_effort=none` 下
  `reasoning_len=0`、`finish=stop`；`verify_crewai_path.py` 120.0s / 3115 字 PASS
  （旧 q2big 基线 114.8s / 1748 字，质量与速度都更好）。

### 11.2 三轮端到端结果（evidence: crew_run-gsq-run{1,2,3}.log）

| 轮次 | max_iter | 结果 | 假成功 |
|---|---|---|---|
| run1 18:52–19:03 | 8（全局） | 市场/研究/情绪/回测/调仓 5 个真实 | 风控、交易员回显框架收尾提示语 |
| run2 19:12–19:32 | 25（三个智能体）+ 工具修复 | 4 个真实 | 风控仍烧光迭代 → 回显 + 大面积 `@` 复读；交易员/调仓被毒化成 `@` 复读 |
| run3 19:33–19:51 | 同上 + 任务描述纪律 | **7/7 全部真实**（风控 8600 字完整报告） | 0 |

run3 工具调用面：`stop_loss_advice×12 / risk_reward×8 / set_stop_loss×6 / view_portfolio×4 /
fundamental_analysis×4 / execute_buy×1`，无 position_size 反复微调（run2 是 ×48）。
`portfolio.json` 落盘健康（平安 +100 股、现金 17337→16235、补设五粮液/格力止损止盈，JSON 无撕裂）。

### 11.4 run4(21:42–21:57)：又抓一个撕裂写——trades_YYYYMM.json

9.2 只修了 `portfolio.json`，**交易流水 `history/trades_YYYYMM.json` 还是裸 `open("w")`**。
run4 调仓师连发 5 笔卖出后，第 6 笔起全部报
`{"success": false, "error": "'utf-8' codec can't decode byte 0xa5 in position 1249: invalid start byte"}`，
然后同一个 execute_sell 重试 20+ 次烧光 max_iter=25 → 回显框架收尾提示语（假成功）。

- 真因：`update_position` 读-改-写流水不在锁内，两个线程（CrewAI 线程池并行工具调用）
  交错刷新，文件变成"合法 JSON 数组 + 另一线程的残片"（尾部 13 字节 `\r\n\xa5标的。"`）。
- 修复：读-改-写整段进 `_PORTFOLIO_LOCK`，写用 tmp + `os.replace`。
  实测 8 线程 × 8 次并发记账：修复前 22/64 次 `WinError 5 拒绝访问`，修复后 **0 错误**，
  文件始终是合法 UTF-8 JSON。教训与 9.2 相同：**读也必须持锁**（Windows 上 replace 遇到
  别人开着的读句柄就拒绝）。
- 损坏文件已修复：`history/trades_202609.json` 用 `JSONDecoder.raw_decode` 截掉撕裂尾部，
  救回 3 条记录，原件备份为 `trades_202609.json.corrupt-bak`。
- 影响面：run4 六项真实产出(风控 3450 字、交易员 984 字都正常)，只有调仓师一个假成功。
  另注意 run4 交易员真实执行了"平安加仓 100 股 @11.30"，portfolio.json 落盘健康。

### 11.6 run5(22:00–22:16)：修复后 7/7 全真实，数据文件零损伤

撕裂写修复后的第一次完整 run：**7 个任务全部真实产出，0 个假成功标记**
（市场 1624 / 研究 2408 / 情绪 1131 / 回测 2726 / 风控 2698 / 交易 1041 / 调仓 1202 字）。
`portfolio.json`、`history/trades_202609.json`、`trade_log.json` 全部 UTF-8 合法，
无 `.tmp` 残留。交易员真实执行了加仓（平安 100 股、双汇 100 股），现金 41108 元。

至此 9/26 模型切换后的完整成绩：run1 5/7 → run2 4/7 → run3 7/7 → run4 6/7（调仓师被
撕裂写打崩）→ run5 7/7（修复后）。剩余已知瑕疵均为既有问题，与本次换型无关：
持仓"现价=成本"未刷新（`fix_last_price.py`）、akshare 新闻接口必坏（10.6）、
写入型工具在分析循环里直接落账（8.4，待用户拍板是否改"建议+人工确认"）。

### 11.5 已实测的模型能力边界（9/26 晚）

- 原生工具调用：`/v1/chat/completions` 带 `tools` 参数，5/5 次正确返回
  `tool_calls=[get_realtime_quote(code=000001)]`，`finish_reason=tool_calls`。
  出现过 1 次瞬时 HTTP 500（与 crew 管线并发加载同一模型时），随后 5/5 全成功——
  **部署时别和流水线抢同一个模型**。
- 速度：页缓存热时单次短问答 11s（冷加载约 36s）；管线全程约 15~18 分钟。
- 4050 Ti 16G 上 IQ3_S 权重 10.2GiB + 22.8k prompt KV，峰值约 14.5/16GiB，余量安全。

### 11.3 run1/run2 暴露并已修的 5 个问题

| # | 位置 | 问题 | 修法 |
|---|---|---|---|
| 1 | `core/agent_base.py` | `max_iter` 只有全局 `AGENT_MAX_ITER` | `create_crewai_agent(tools=None, max_iter=None)` 支持按智能体放宽；风控/交易员/调仓传 25 |
| 2 | `crew.py` | 风控拿到 11 个工具（含买入 sizing） | 只给 4 个评估工具（stop_loss_advice/risk_reward/portfolio_risk/circuit_breaker_check）；写操作工具不给风控 |
| 3 | `portfolio_tracker.set_stop_loss` | 任何路径都返回 None → 工具层 `"error" in result` 抛 TypeError | 显式返回 success/error 字典 |
| 4 | `tools/risk_tools.py::PositionSizeTool` | 模型按百分数传参（5.5%）被当小数用，输出 `stop_loss_price=-348.35` | >1 按百分数归一；折算后仍超范围（如 risk_per_trade=1000）显式报错 |
| 5 | `tasks.py` | 风险/交易/调仓任务没有工具使用纪律 | 三段任务描述各加"每工具每股票至多一次、接受返回值、不要微调凑数、完成后直接输出" |

> 教训：**降 max_iter 防的是"轮次爆炸",但 27B 在新量化格式下出现新的失效型——参数微调死循环**
> （risk_per_trade 0.008→0.009→0.0085）。工具面裁剪 + 任务描述里的纪律声明比单纯放大
> max_iter 有效：run2 放到 25 仍然烧光，run3 加纪律后风控 12 次 stop_loss_advice 就收尾。

---

## 11.7 run6(22:29–22:45)：修持仓现价不刷新 + 买入不记账（2/2）

### bug A：`portfolio.json` 的 `last_price` 从不刷新（已修）

现象：`result_latest.md` “当前持仓”段所有股票“现价=成本”（如平安 11.75=11.75）。
Dashboard `/api/portfolio` 自己实时抓价所以显示正常，但 `portfolio.json` 里的
`last_price` 从未被更新，风控/调仓智能体实际基于陈旧价格（成本价）做决策。

根因：`update_position` 只在传入 `current_prices` 时更新价格；crew.py [2/8] 的
`check_stop_loss()` 、`get_portfolio_summary()` 均以无参调用，回退到 `avg_cost`；`portfolio.json`
的 position 字段里根本没有 `last_price`（`fix_last_price.py` 是一次性脚本，且自己也是裸
`open("w")` 无锁写）。

修法（`portfolio_tracker.py`：新增 `refresh_position_prices()`）：
- 走 `df.get_realtime_quotes`（东财直连 + 新浪 K 线兜底，与候选池同源），
  读-改-写整段走 `load_portfolio`/`save_portfolio` 持锁原子写；
- 写入 `last_price` + `last_price_time` 并重算 `total_value`/`total_return_pct`；
- 新建 `_position_last_price(pos)` 统一取值链：`current_prices > last_price > avg_cost`，
  `check_stop_loss` / `get_portfolio_summary` / `update_position` 全部改走该链；
- buy 时给新仓位种入 `last_price = 交易价`；
- `crew.py` `prepare_market_data()` 启动时先刷新再生成摘要（日志行 `[持仓现价] 已刷新 7 只`）；
- `fix_last_price.py` 重写为该函数的薄封装（不再裸写）。

### bug B：买入从不记入 `history/trades_YYYYMM.json`（run6 发现，已修）

run6 交易流水侧 `trades_202609.json` 原本 78 条全是 sell——`update_position` 的记账块嵌在
`elif action == "sell":` 分支里，所有买入（run4/5/6 的平安加仓、双汇建仓等）在流水账里无痕。
修法：记账块移出分支，`if action in ("buy", "sell")` 时均记录（buy 的 pnl 记 0.0）。
历史上丢失的买入记录不能拼回，不做虚构补录。

### run6 结果（evidence: crew_run-gsq-run6.log）

- 7/7 任务全部真实产出，0 个“假成功”标记；管线 22:29–22:45 约 16 分钟。
- 修复生效：报告现价非成本（平安 11.30 vs 11.44，美的 82.65 vs 86.83）；
  [2/8] `check_stop_loss()` 基于现价正确触发 `万科A TAKE_PROFIT @ 3.76`，
  调仓师随后真实下单卖出 600 股 @3.76（pnl +360 / +18.99%，流水账有录）。
- `portfolio.json` / `history/trades_202609.json` / `trade_log.json` 均 UTF-8 合法，无 `.tmp` 残留。
- 单元测试 17/17 通过；新增 2 个回归测试（买入记账、last_price 回退链）后 19/19。

---

## 十二、本地模型审查与优化（9/26 23:20，local_model_review_noreason.md）

### 12.1 用本地模型自己审查代码（方法入册）

脚本：D:/temp-ollama-test/local_review2.py（把 crew.py / tasks.py / core/agent_base.py /
agents/llm.py / tools/trade_tools.py 五份核心文件合成 37.5k 字符，发给
qwen3.8-gsq-rco-iq3s 做代码审查）。

关键经验：**直接调 Ollama 时必须显式传 reasoning_effort: "none"**。第一次忘带这个参数，
4096 token 全被 thinking 吃掉、content 为空（与 .env 里 LLM_REASONING_EFFORT=none 是同一道
防线，但那是 CrewAI 通道的参数，自己发 HTTP 请求时不会自动带）。关掉后 102s 输出 6224 字
真实建议。

### 12.2 审查结论与采纳情况（10 条建议，4 采纳 / 3 驳回 / 3 已存在或不适用）

| # | 模型建议 | 核查判断 | 处理 |
|---|---|---|---|
| 1 | [8/9] 重复请求 get_market_heat/regime | 属实（heat 无缓存） | **采纳**: prepare_market_data 新增 heat/regime 入参，[1/8] 取一次全程复用 |
| 2 | A_SHARE_POOL 线性查找 | 属实但池仅 48 只，无感知 | 驳回（不添加无意义改动） |
| 3 | update_position 竞态 | **已于 9/26 修复**（锁+原子写） | 无需处理 |
| 4 | 风控任务工具指令歧义 | 现文案已写明"每只股票…各至多一次" | 驳回 |
| 5 | view_portfolio 返回 raw 整包 | 属实，本地模型 token 浪费 | **采纳**: 只返回 summary |
| 6 | get_llm() 返回 None 时 Agent 崩溃信息不明 | 属实 | **采纳**: create_crewai_agent 显式报 ValueError |
| 7 | 情绪任务需结构化上下文 | 需改研究员输出协议，影响面大 | 稍后评估，本轮不改 |
| 8 | 回测串行 | 属实（代码已导入 ThreadPoolExecutor 却未用） | **采纳**: ex.map 保序并行 |
| 9 | notify_wechat 安静失败 | 设计如此（cron delivery 管通知） | 驳回 |
| 10 | 交易任务 8 列 Markdown 表 | run4-6 实测输出并可解析，改格式带新风险 | 驳回 |

### 12.3 验证

- 单元测试 19/19；dry_run_offline 正常；
- 针对四项采纳写了专门验证（D:/temp-ollama-test/test_optimizations.py）：None-LLM 报错、
  Agent 正常建立、view_portfolio 无 raw、heat/regime 注入后零重复获取、并行回测保序且对
  无效代码容错；
- run7 端到端（23:28 启动）结果见 crew_run-gsq-run7.log。

---

## 12.4 run7（23:28–23:44）：优化无回归，但发现模型 @ 复读退化（已加防护）

run7 结果：任务 1-5（市场/研究/情绪/回测/风控）全部真实产出，但
交易员与动态调仓师两个任务整段输出是 @ 复读并被 CrewAI 视为正常完成。
数据文件均安全（无 .tmp，JSON 合法），但该输出不可用。

归因分析：
- 与本轮优化无关。用 run7 的真实上下文（market/research/risk 三段输出）单独重放交易员
  任务，输出正常（见 repro_trader.py，两次重放均真实）。
- 同样式的 @ 复读在 run2 也出现过（当时归因于上游中毒），属本地模型（IQ3_S）
  随机退化：无工具调用、直接单轮输出复读。
- **工程缺口**：系统没有对任务输出做健全性检查，垃圾输出会混入 result_latest.md。

修法（crew.py）：新增 `_looks_degenerate()` + `check_degenerate_tasks(crew)`，
kickoff 后遍历 `crew.tasks[i].output`：
- 判据：输出 <50 字；单字符整行（len>=10）占多数；同一行重复率 >60%。
  故意**不用**全文字符集大小做判据：中文唯一字符本身就少，会误伤正常报告。
- 命中时打 🚨 日志，并在报告顶部插入警告。
- 验证：对 run7 日志里 7 个真实答案框做回放测试，任务 1-5 不误伤、
  任务 6-7 均被命中；Markdown 表格/中文报告不误伤。

跑后必查（更新）：`Select-String -Path crew_run-gsq-run8.log -Pattern '@{20,}'`

### 12.5 run8（00:02–00:22）：全量优化 + 防护后的首次完整验证

- 7/7 任务全部真实产出（含 run7 退化的交易员 1098 字、调仓师 2084 字），
  0 退化标记、数据文件均安全。
- 本轮四项优化（heat/regime 复用、view_portfolio 瘦身、None-LLM 报错、
  并行回测）均随线验证，无回归。
- 统计：端到端成功率 run3 7/7 → run5 7/7 → run6 7/7 → run7 5/7（退化尚未防护）
  → run8 7/7（退化可检测）。剩余已知弊端：@ 复读只能检测不能预防；
  akshare 新闻接口必坏（10.6）；写入型工具在分析循环里直接落账（8.4，待用户拍板）。
（run7 的 @ 复读就是这种形态，旧的 Maximum iterations 排查抓不到它）。

---

## 附：关键命令速查（StepFun 云端路线，9/26 改版）

```powershell
cd D:\aishare\repo\stock-crewai-master
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"

# 0) 跑前 30 秒体检 —— 三项按顺序，第一项最容易被跳过
(Get-Content .env | Select-String '^OPENAI_API_KEY=').ToString().Split('=')[1].Length
#   ↑ 必须是 64。等于 11 或含 … 就说明 key 又被工具侧截断了（见"当前状态"），白跑的概率 100%
& $py -u dry_run_offline.py    # 零 LLM 调用、不花 token：数据层 + 任务装配 + prompt 体量，约 30s
curl.exe -sS -m 20 -o NUL -w "models_ep=%{http_code}\n" https://api.stepfun.com/step_plan/v1/models `
  -H "Authorization: Bearer $((Get-Content .env | Select-String '^OPENAI_API_KEY=').ToString().Split('=')[1])"
#   ↑ 200 才算鉴权过。401 别去查模型名，先回到上面那条量字节

# 1) 2 分钟自检：走真实 CrewAI 调用链（这条同时是 Cause B 的回归工具）
& $py verify_crewai_path.py     # PASS 标准：非空、约 1700 字、自然收尾

# 2) 跑端到端前先给持仓拍一张快照（调仓任务会真的下单改 portfolio.json，见 10.4）
Copy-Item portfolio.json ("portfolio.pre-run-" + (Get-Date -Format yyyyMMdd-HHmm) + ".json")

# 3) 跑端到端 —— 必须用 Python 3.12（crewai 只在 3.12 环境里），且必须加 -u
Start-Process -FilePath $py -ArgumentList -u, crew.py `
  -RedirectStandardOutput crew_run7.log -RedirectStandardError crew_run7.err
Get-Content crew_run7.log -Tail 30

# 4) 跑完必查"假成功"（10.1）：命中说明某个任务的输出只是框架提示语回显
Select-String -Path crew_run7.log -Pattern "Maximum iterations reached|absolute best final answer"
```

> `-u` 不是可选项：不加时 stdout 是块缓冲，日志文件会长时间停在 0 字节，
> 整个 run 期间看不到任何进度（`crew_run6` 就是这么只能靠 Ollama 侧日志反推）。
>
> 回退本地 Ollama 时才需要旧那三条体检：`curl http://127.0.0.1:11434/api/version`（服务会无崩溃记录地消失）、
> `ollama list`（17:11 那次模型被外部从磁盘删了）、`Get-PSDrive D | Select-Object Free`（见 9.3 的账），
> 外加 `ollama ps ; nvidia-smi --query-gpu=memory.used,memory.total --format=csv` 看 `size_vram == size`。

判据：`Invalid response from LLM call - None or empty.` 不是"模型抽风"，它是**三种不同故障的同一个外壳**：

1. 服务端日志里有 `exceed_context_size_error`（HTTP 400）→ 上下文超限，加大 `num_ctx`（**仅本地 Ollama 会遇到**，云端实测峰值才 5k token）；
2. 服务端**全是 200** 但 `content` 为空、`finish=length`、生成 token 数正好等于 `max_tokens`
   → thinking 没被真正关掉，预算被吃满。此时**不要**先怀疑 `.env`，
   要拦截框架实际发出的 HTTP body 确认参数有没有出去：
3. **HTTP 401 `invalid_api_key`** → 九成不是 key 错，是密钥在写入时被工具层截断（`length` 只有 11）。
   先跑上面第 0 项量字节，再怀疑服务商。

```python
import openai.resources.chat.completions as m
m.Completions.create = lambda self, *a, **kw: (CAPTURED.append(kw), (_Stop(),))[-1]
```

（`probe_payload.py` 就是这个用法；两分钟出结论，比整条流水线一小时快得多。）


## 十三、参照标杆项目落地（TradingAgents / ai-hedge-fund）+ Ollama 0.34.4 事故恢复（9/27）

### 13.1 落地清单（全部已单测/端到端验证）
- `trading_plan.py`（新）：`TradeAction`/`TradingPlan` pydantic schema + `parse_trading_plan()`（fenced ```json 块优先、逐行容错）+ `plan_to_recommendations()`（只收 buy/add）+ `render_plan_summary()`。踩坑：pydantic validator 必须 `mode="before"`，否则 float 字段先于清洗报错。
- `llm_cache.py`（新）：`make_cached_llm(**kwargs)`，PromptCache 模式（key=sha256(model+messages+tools)，目录 `cache/llm/`）。关键坑（本轮全部踩过）：
  1. `crewai.LLM` 是 `__new__` 工厂，直接子类化 LLM 会被 bypass；必须先 `LLM(**kwargs)` 造真实对象再 `type(base)` 动态子类化。
  2. 子类实例**不能**直接 `_CachedProviderLLM(**kwargs)`：工厂会把 `openai/` 前缀从 model 上剥掉并补 `provider="openai"`、`custom_openai=True`，用原始 kwargs 重建会把前缀带回去，Ollama 直接 404。也不能 `__new__` + `__dict__` 拷贝：pydantic v2 私有状态缺失，报 `no attribute '__pydantic_private__'`。正解见函数尾：从 `base.__dict__` 取公开字段值回灌子类 `__init__`。
  3. 验证方式（9/27 已过）：`LLM_CACHE_TTL=600` 下连发两次相同 prompt，第一次 9.15s，第二次 0.00s 命中 `[LLM cache] hit xxxxxxxx`。
- `agents/llm.py`：`_build_llm()` 统一出口，TTL>0 时走缓存包装；docstring 补充 LLM_CACHE_TTL 说明。
- `tasks.py`：交易任务（141 行后）与调仓任务（205 行后）的描述追加"输出格式要求"JSON 块指令。踩坑：JSON 示例行进 f-string 前必须把所有 `{`→`{{`、`}`→`}}`，否则 dry_run 直接崩溃。
- `crew.py`：[8/8] 步结构化解析优先，失败回退旧正则 `rt.parse_trading_result`（日志 `[结构化解析] N 条动作，可追踪推荐 M 只` 或"未命中 JSON 块，回退自由文本解析"）；报告尾追加 `render_plan_summary`。

### 13.2 验证结果（9/27）
- `pytest tests/ -q`：19/19 通过。
- `dry_run_offline.py`：10/10 行情、7 task 全装配，峰值 prompt ≈5579 token。
- 任务描述渲染校验（真实 agent 构造 Task）：`{{`/`}}` 无泄漏、```json 块与 "actions" 键均在。
- run9 端到端（crew_run-gsq-run9.log）：交易员执行买入 000001 平安银行 +500 股 @11.30（trades_202609.json 已记账，portfolio 2800 股 @11.39 均值）；调仓师输出 5 条动作 JSON 被结构化解析成功（hold×2 / set_stop_loss×2 / watch）；`@{20,}` 复读 0 命中；报告 `history/report_20260927_1030.md` 已存；portfolio.json / trade_log.json / trades_202609.json 全部合法 UTF-8 JSON。

### 13.3 Ollama 0.34.4 事故与恢复流程（重要，下次遇到直接照做）
- 现象：run9 首跑 10:25 左右 LLM 调用集体 502；随后发现 Ollama 自动升级到 0.34.4，`llama-server` 启动即崩（`exit status 0xc0000409 ... CUDA error: a PTX JIT compilation failed`），或 `CUDA error: out of memory` / `0xc0000005`。
- 根因链：a) 托盘应用自动更新把 0.33.2 升成 0.34.4；b) 0.34.4 带 cuda_v13 后端，driver 13.4 选中它但 PTX JIT 编译崩溃。
- 恢复步骤（已执行，当前机器处于此状态）：
  1. 下载 `https://github.com/ollama/ollama/releases/download/v0.33.2/OllamaSetup.exe`（约 1.5GB）。
  2. 杀掉所有 `ollama*` 进程（含托盘 `ollama app`），再跑安装器 `/VERYSILENT /NORESTART /LOG=...`；安装器结尾会拉起托盘，**装完立刻再杀一次托盘**，否则自动更新又升回 0.34.4。日常推理只用 `ollama serve`，不要开托盘。
  3. 把 `%LOCALAPPDATA%\Programs\Ollama\lib\ollama\cuda_v13` 改名为 `cuda_v13.disabled`，强制走 cuda_v12 后端（0.33.2 的 12 库在 driver 13.4 下正常）。
  4. 显存墙：4060 Ti 16G，当前桌面常驻约 1.9G。模型 blob 11.2G，num_ctx=32768 必 OOM；直接把参数 blob 改成 16384：文件 `D:\.ollama\models\blobs\sha256-ca776b...7157a2`（manifest 里 params 层，内容原为 `{"num_ctx":32768}`，17 字节同名替换 `{"num_ctx":16384}`），重启 serve 即可生效，无需重导模型。16384 对峰值 5.5k token 的 crew prompt 仍有 3 倍余量。
- 校验命令：`curl`/HTTP POST `/api/version` 应为 0.33.2；`ollama ps` 应显示 100% GPU、CONTEXT 16384。

## 十四、电脑重启后本地模型流程全自动（9/27 中午落地并实测）

### 14.1 启动链（唯一入口）
开机启动文件夹里只保留一个有效项：`stock-crewai-autostart.vbs`（纯 ASCII、无 BOM，
中文注释会把 VBScript 解析弄坏，报"缺少对象: 'ws'"），它无窗口调用仓库里的
`start_local_stack.ps1`。原来的 `Ollama.lnk`（托盘）已改名为 `Ollama.lnk.disabled`
——托盘是 0.34.4 自动更新的源头，必须永远不再自启。

### 14.2 守卫脚本 start_local_stack.ps1 的六步
1. 杀托盘进程 `ollama app`（双保险，防托盘被别的方式拉起）
2. 若 `lib\ollama\cuda_v13` 存在则改名 `.disabled`（强制 cuda_v12 后端）
3. 扫描参数 blob，把 num_ctx 校准回 16384（模型被重建也能兜住）
4. `ollama serve` 未起则拉起，轮询 /api/version 就绪（最长 80s）
5. 预热：跑 `warmup_llm.py` 做一次真实推理；失败则整体重启 ollama（杀 server+runner）再试一次；两轮都败就退出不跑流水线
6. 防重复：已有 `python crew.py` 在跑就直接退出；否则无窗口启动 crew.py，日志 `crew_run-autostart-<stamp>.log`

守卫自身日志在 `logs/autostart-<stamp>.log`。

### 14.3 实测结果（11:10 冷启动，杀掉全部 ollama 进程后从 vbs 触发）
11:10:31 begin → 11:10:34 serve 拉起 → 11:10:41 就绪 → 11:10:50 预热 OK → crew 启动，
全程 19 秒无人工干预。二次触发时防重复生效（日志出现 "crew.py already running ... skip launch"）。

### 14.4 已知坑
- 并发的第二个客户端撞上正在生成的 runner 可能把 llama-server 打僵（ollama ps 空但
  进程占着 12GB 显存），表现为 "model runner has unexpectedly stopped"。自愈逻辑已覆盖
  开机路径；运行中若再遇到，手动杀 llama-server 再重跑 guard 即可。
- 每次开机会自动跑一轮完整分析（~15-20 分钟，会真实下单）。只想启服务不跑分析：
  把 vbs 里的 `start_local_stack.ps1` 换成 `start_ollama_only.ps1`，或直接手动
  `ollama serve`。

### 14.5 不用时自动卸载模型（9/27 追加，已实测）
两层保障，均无需人工干预：
1. **空闲超时**：守卫脚本启动 serve 前显式设置 `OLLAMA_KEEP_ALIVE=5m`（可用环境变量覆盖），
   最后一次请求 5 分钟后 ollama 自动卸载，显存还给桌面。
2. **跑完即卸**：守卫不再直接拉 `crew.py`，而是拉 `run_crew_then_release.py` 包装器——
   crew 退出后立即执行 `ollama stop qwen3.8-gsq-rco-iq3s`（实测显存 14.3G→1.3G，ollama ps 为空）。

想改卸载时限：设环境变量 `OLLAMA_KEEP_ALIVE`（如 `30s`/`1m`/`0` 表示跑完立即卸）。
手动卸：`ollama stop qwen3.8-gsq-rco-iq3s`。

### 14.6 全流程实测与两个新坑（9/27 午后）
- **完整链路实测通过**：冷启（杀光 ollama）→ vbs 触发 22 秒到位（serve 10s + 预热 12s）→
  crew 跑约 16 分钟 → `[结构化解析] 4 条动作`、执行补仓平安银行 → 报告存档 →
  `[model-release] ollama stop rc=0` → 显存 14.3G→1.2G、ollama ps 空。全程零人工。
- **坑 1：.ps1 必须是 UTF-8 with BOM**。python 写的无 BOM UTF-8 被 Windows PowerShell 5.1
  按 GBK 误读，中文注释虽然只是注释，但字节错位会把紧随其后的可执行行啃坏
  （现象：`keep_alive = ` 赋值为空）。已用 `﻿` BOM 重写，测试脚本里
  `ka_test3.ps1`（BOM 版）打印正常可对照。以后改这个脚本注意保留 BOM。
- **坑 2：自愈重启会烫死在跑的流水线**。守卫原来“先预热失败再重启”的顺序，会在
  重复触发时把正在推理的 crew 打死（11:35 实测死亡一次）。已调整顺序：防重复检查
  前移到起服务之前，发现 crew/包装器在跑就只确认服务在线然后退出，不预热不重启。
