# 交接文档：stock-crewai 七智能体端到端验证

> 生成时间：2026-09-19；最后更新：2026-10-03 23:15
> 背景：项目用 CrewAI 七智能体做 A 股投资分析。**模型端点由 `.env` 的 `OPENAI_BASE_URL` + `MODEL_NAME` 决定
> （`LLM_PROVIDER` 未设 → 走 `agents/llm.py` 的 OpenAI 兼容缺省分支），当前是本地 Ollama
> `qwen3.8-gsq-rco-iq3s`（27B IQ3_S，`http://127.0.0.1:11434/v1`）**；
> 9/26 白天曾短暂切到 StepFun 云端 `step-5-preview`，当晚换回本地 GSQ-RCO，
> 那套云端配置以注释形式留在 `.env` 下半部，回退只需解注释（key 须用户本人粘贴）。
> 调用链两个时代共用：`agents/llm.py:get_llm()` → CrewAI(litellm)。
> 目标：把 `crew.py` 完整跑通端到端（行情→选股→情绪→回测→风险→交易→调仓→落盘 result_latest.md）。
> **该目标已达成**：run5 起 7/7 任务全真实输出，`result_latest.md` 每交易日 15:35 由计划任务自动刷新。

---

## 当前状态（2026-10-03 23:15）

- **分析流水线已彻底改为"只出建议、不持仓落账"**（第十六节，两道防线）：
  ① `crew.py:build_agents()` 的工具白名单不含任何下单类工具；
  ② `tools/trade_tools.py` 三个写工具入口有总开关 `trading_allowed()`，
  读环境变量 `ALLOW_AGENT_TRADING`（`1/true/yes/on` 才放行，**默认拒绝**）。
  第 ② 道是给旧编排路径（`workflows/daily_analysis.py` / `main.py --scheduler` /
  `web_dashboard.py`）兜底的，那条路的 `agents/*.py` 仍挂着 `get_trade_tools()`。
  `.env` 现在**没有**这个键 → 当前就是只出建议模式。要恢复自动下单须显式设
  `ALLOW_AGENT_TRADING=1`，且这是行为变更、动之前先问用户。
- 端到端早已不是问题：`result_latest.md` 由计划任务 `stock-crewai-daily-run`
  每周一至周五 15:35 自动刷新（最近一份 2026-10-03 23:02，是本次改动后的手动实跑；
  下一份自动日报是 10-05 周一 15:35）。
- **改动后的链路已实跑验证过**（16.5 第 3 层）：10/3 22:47–23:02 手动跑 `crew.py`
  → 7/7 任务真实完成、0 个假成功标记、日报里 0 处"已执行"表述、日志中连一次下单尝试都没有
  （`advice_only` 命中 0，因为工具不在集合里），`portfolio.json` 的现金与四只持仓
  逐字段跑前跑后一致。所以周一 15:35 那次无人值守运行**不是**首跑。
- **测试 56 个用例全绿**（`pytest tests/ -q`，约 30s）。其中
  `TestAgentToolWhitelist`（3 例）锁 ①、`TestAgentTradingGate`（5 例）锁 ②。
- **零 token 自检 `dry_run_offline.py` 已改为调 `crew.build_agents()`**：
  它此前自己按默认全量工具重建一份 agent，与 `crew.py` 实际传参是两份代码，
  所以验不出工具集回归（9/26 情绪工具"文档说禁用、代码还挂着 3 个"就是这么漏的）。
  现在会逐条打印七个 agent 的工具并对写操作工具做断言。
- 遗留未决三项，都需要用户拍板，未擅自动手：
  1. **旧路径调仓永远报"无持仓"**（16.7）：`PortfolioRebalancerAgent.run()` 把
     `view_portfolio` 当字典读 `holdings`，而该工具返回的是 `{"summary": <字符串>}`。
     只影响旧编排路径。修它等于让一条一直空转的路径第一次真产出动作，属行为变更。
  2. **微信推送仍开着**：`crew.py:notify_wechat()` 走 `openclaw`（本机在 PATH 上），
     交易员/调仓师也仍带着 `wechat_notify`/`dashboard_notify` 两个通知工具。
     本次只动了"写持仓"这一类副作用，通知类刻意原样保留。
  3. **开机脚本的 num_ctx 校准作用域过大**（6.1）：`start_local_stack.ps1` 会改写
     本机**所有**模型的参数 blob，10/2 已实测顺带把无关模型 `q38-lite` 的配置改掉了。

### 2026-09-26 那次换型与当时的状态（历史记录，仍然有效）

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

**当前 = 本地 Ollama `qwen3.8-gsq-rco-iq3s`**（`http://127.0.0.1:11434/v1`，num_ctx 参数层锁 16384）。
10/3 实测：`/api/version` 回 **0.33.2**、`ollama ps` 空（模型已按设计释放）、
`ollama list` 有两个 11G 模型：`qwen3.8-gsq-rco-iq3s:latest`（在用）与
`q38-lite:latest`（**仓库内零引用**，不是本流水线用的，别改 `.env` 指向它）。
计划任务 `stock-crewai-daily-run` 下次运行 2026-10-05(周一) 15:35；10/3、10/4 是周末不跑属正常。

> 下面这段是**切云端之前最后一次本地环境的快照**（模型名与显存数字属于 9/26 之前的 q2big 时代），
> 保留只为查历史故障用，不代表现状。

- 模型 `qwen3.8:q2big`：✅ 当时**正在使用**，与 `q2` 同一份 GGUF，`num_ctx 32768`，22.8k token prompt 实测可用
- 模型 `qwen3.8:q2`：✅ 完好但 `num_ctx 8192` 已不够用，仅留作对照
- 模型 `qwen3.8:latest`：`TEMPLATE {{ .Prompt }}` 裸模板变体，无实际用途
- GPU：13461 / 16380 MiB（q2big + 22.8k prompt，全量在 GPU 上）
- Ollama 0.33.2：本次以干净环境手动 `ollama.exe serve` 拉起，`OLLAMA_KEEP_ALIVE=20m`
- litellm 1.100.1、crewai 1.15.21：✅ 已装；**注意 crewai 只装在 Python 3.12**
  （默认 `python` 是 3.14，直接 `python crew.py` 会 ModuleNotFoundError）
- 早前清理：已删死代码 `agents.py`、已删孤儿 blob `sha256-028a1d47`

### 6.1 `start_local_stack.ps1` 会改写**所有**模型的 num_ctx（10/3 发现，未修）

`logs/autostart-20261002-233727.log` 里有一行：

```
num_ctx fixed in sha256-9e0cb792...: {"num_ctx":8192,"num_gpu":56} -> {"num_ctx":16384}
```

`sha256-9e0cb792...` 不是 gsq-rco 的参数 blob。10/3 逐个 manifest 核实过（Ollama 按内容寻址，
params 层就是那两个 sha256 文件）：

```
manifests/…/q38-lite/latest                → params sha256:9e0cb792…  model sha256:64b53b64…
manifests/…/qwen3.8-gsq-rco-iq3s/latest    → params sha256:ca776b6b…  model sha256:64b53b64…
```

也就是说 `sha256-9e0cb792…` 属于 `q38-lite`。它和 gsq-rco **共用同一份权重层**
（`64b53b64…`），只是 params 层不同，所以不额外占 11G 磁盘；差异在推理配置上
（被改前是 `num_ctx 8192 + num_gpu 56`，即只把 56 个张量放 GPU 的"半 CPU 档"）。
结论：开机脚本为了兜住"模型被重建"，扫描并改写了**每一个**参数 blob 的 num_ctx，
顺带把一个无关模型的配置静默改成 `{"num_ctx":16384}`、并且整个丢掉了 `num_gpu` 字段。
目前没造成可观察故障（那个模型没进 `.env`，流水线不引用它），
但这是"校准脚本的作用域大于它服务的模型"这类越界写，下一次导入新模型时同样会被改。
要不要收窄到只匹配 gsq-rco 的 params 层，属行为变更，留给用户拍板。

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
   - ~~**调仓任务的写操作**：`execute_sell` 在分析循环里直接改 `portfolio.json`（10.4），
     是否改为"只出建议 + 人工确认后再记账"需用户拍板~~ ✅ **2026-10-03 用户拍板：改为只出建议**，
     交易员与调仓师的工具白名单已剔除全部下单类工具，见第十六节
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

> **已于 2026-10-03 拍板并落地**：调仓智能体曾在"分析"过程中直接下单改持仓（run6 有 4 次
> `execute_sell`，10-02 那次日报还清仓了徐工机械 600 股并写进了 `result_latest.md` 的
> "已执行操作"一节）。用户选择**只出建议、不落盘**：交易员与调仓师的工具白名单已剔除
> `execute_buy`/`execute_sell`/`set_stop_loss`，提示词同步改为禁止出现"已执行"表述。
> 细节与验证见第十六节。注意历史成交记录（`portfolio.json`、`history/trades_202609.json`
> 及之后各月）里已经留有此前自动下单的痕迹，本次改动不会回滚它们。

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
写入型工具在分析循环里直接落账（8.4，~~待用户拍板是否改"建议+人工确认"~~
→ 2026-10-03 已拍板并落地，见第十六节）。

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
  akshare 新闻接口必坏（10.6）；~~写入型工具在分析循环里直接落账（8.4，待用户拍板）~~
  → 已于 2026-10-03 改为只出建议（第十六节）。
（run7 的 @ 复读就是这种形态，旧的 Maximum iterations 排查抓不到它）。

---

## 附：关键命令速查（本地 Ollama 路线，2026-10-03 改版）

```powershell
cd D:\aishare\repo\stock-crewai-master
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"

# 0) 跑前体检（本地路线没有"密钥长度"这一步了，`.env` 里 OPENAI_API_KEY=ollama）
curl.exe -sS -m 5 http://127.0.0.1:11434/api/version   # 服务会无崩溃记录地消失，见 13.3
& $py -u dry_run_offline.py    # 零 LLM 调用、不花 token，约 30s：数据层 + 七个 agent 工具集 + prompt 体量
#   ↑ 必看到 "写操作工具泄漏 -> 无"。这是第十六节那条不变量的快速版，装配期异常也在这里先炸
ollama ps   # 模型没常驻时首请求会冷启（十几秒），不是卡死

# 1) 回归测试（30s，不碰网络不碰模型）
& $py -u -m pytest tests/ -q   # 当前基线：56 passed

# 2) 手动跑一遍真实调用链（约 2 分钟，会真占显存）
& $py verify_crewai_path.py     # PASS 标准：非空、约 1700 字、自然收尾

# 3) 跑端到端 —— 必须用 Python 3.12（crewai 只在 3.12 环境里），且必须加 -u
#    正常情况下不用手动跑：计划任务 stock-crewai-daily-run 每周一至周五 15:35 自动执行
#    注意 Git Bash 里 `/tn` 会被当成路径（报 "找不到 D:/Program Files/Git/query"），
#    要么在 PowerShell 跑，要么前置 MSYS_NO_PATHCONV=1。
schtasks /query /tn stock-crewai-daily-run /v /fo LIST
Copy-Item result_latest.md logs\result_pre-<改动名>.log   # 日报每次整体覆盖、无归档，跑前先留一份
Start-Process -FilePath $py -ArgumentList -u, crew.py `
  -RedirectStandardOutput crew_run10.log -RedirectStandardError crew_run10.err
Get-Content crew_run10.log -Tail 30
ollama stop qwen3.8-gsq-rco-iq3s   # 跑完归还显存（14.3G→1.3G）；计划任务走 run_crew_then_release.py 会自动做

# 4) 跑完必查"假成功"（10.1）：命中说明某个任务的输出只是框架提示语回显
Select-String -Path crew_run10.log -Pattern "Maximum iterations reached|absolute best final answer"
#    改动后还要各加一条：`Task Completed` 应为 7；`advice_only|被拒` 应为 0（见 16.5）

# 5) 跑完确认持仓真没被动过（第十六节）。last_price/last_price_time 会变，那是
#    prepare_market_data 里 refresh_position_prices 刷的现价，属于允许写入（16.4）；
#    shares / avg_cost / stop_loss / take_profit / cash 必须与跑前完全一致。
& $py -c "import json;p=json.load(open('portfolio.json',encoding='utf-8'));print(p['cash']);[print(c,v['shares'],v['avg_cost'],v.get('stop_loss'),v.get('take_profit')) for c,v in p['positions'].items()]"
#   ↑ 2026-10-03 基线：cash 47705.0；000001 3200@11.38 sl10.4 tp13.1 / 000858 300@69.67 sl64.1 tp81.44
#     / 000651 100@38.5 sl35.22 tp42.0 / 000333 100@80.1 sl73.69 tp88.0
```

> `-u` 不是可选项：不加时 stdout 是块缓冲，日志文件会长时间停在 0 字节，
> 整个 run 期间看不到任何进度（`crew_run6` 就是这么只能靠 Ollama 侧日志反推）。
>
> **回退到 StepFun 云端时**才需要那三条云端体检：先量 `.env` 里 `OPENAI_API_KEY`
> 的字节数（必须是 64；等于 11 或含 `…` 说明 key 被工具侧写入截断了，见下），
> 再 `curl /step_plan/v1/models` 看 200，最后才怀疑模型名。
> base_url 必须带 `/step_plan` 段。密钥**只能由用户本人粘贴**
> （`Read-Host` 取变量后 `-replace` 写回 `.env`），工具侧写入必被截断，别再用脚本写 key。
>
> 本地路线自身的体检见 13.3（Ollama 版本事故恢复）与 14.2（守卫脚本六步）：
> `ollama list`（9/26 17:11 那次模型被外部从磁盘删了）、
> `Get-PSDrive D | Select-Object Free`（见 9.3 的账）、
> `ollama ps ; nvidia-smi --query-gpu=memory.used,memory.total --format=csv` 看 `size_vram == size`。

判据：`Invalid response from LLM call - None or empty.` 不是"模型抽风"，它是**三种不同故障的同一个外壳**：

1. 服务端日志里有 `exceed_context_size_error`（HTTP 400）→ 上下文超限，加大 `num_ctx`
   （**本地 Ollama 才会遇到**；crew prompt 峰值实测约 5.6k token，参数层已锁 16384，余量 3 倍）；
2. 服务端**全是 200** 但 `content` 为空、`finish=length`、生成 token 数正好等于 `max_tokens`
   → thinking 没被真正关掉，预算被吃满。此时**不要**先怀疑 `.env`，
   要拦截框架实际发出的 HTTP body 确认参数有没有出去：
3. **HTTP 401 `invalid_api_key`**（仅云端路线）→ 九成不是 key 错，是密钥在写入时被工具层截断
   （`length` 只有 11）。先按上面那条量字节，再怀疑服务商。

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
- ~~每次开机会自动跑一轮完整分析（~15-20 分钟，会真实下单）~~ **2026-10-03 起不再下单**：
  分析流水线已改为只出建议（第十六节），跑一轮仍约 15-20 分钟，但不会再改持仓。
  只想启服务不跑分析：把 vbs 里的 `start_local_stack.ps1` 换成 `start_ollama_only.ps1`，
  或直接手动 `ollama serve`。

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

### 14.7 开机不再立即跑：改为“合适时间”定时运行（9/27 中午起）
用户要求开机后由系统自己挑合适时间运行，不再登录即跑。新流程：
- `start_local_stack.ps1`（开机 vbs 调用）：杀托盘→锁后端→校准 num_ctx→起 serve→预热校验→
  调用 `ensure_run_schedule.ps1` 注册计划任务，**登录时不再直接跑分析**。
- `ensure_run_schedule.ps1`：注册 `stock-crewai-daily-run`，每周一至周五 `AUTORUN_HHMM`
  （默认 15:35，A股收盘后 5 分钟；可用环境变量改），StartWhenAvailable=true（睡眠/关机
  错过则开机补跑），执行时限 2 小时。幂等，每次开机刷新。
- `run_crew_scheduled.vbs`：计划任务的实际动作，隐藏窗口拉起
  `run_crew_then_release.py`（vbs 不碰引号地狱）。
- `run_crew_then_release.py` 增强：启动前检查是否有别的 crew/包装器在跑（防双流水线同时
  下单）；crew 输出 tee 到 `logs/scheduled-run-<stamp>.log`（计划任务隐藏窗口，不落盘
  就什么都看不到）；跑完 `ollama stop` 卸载。
- 实测（12:23 手动触发任务）：wscript→包装器→crew 全链路跑通，12:37 完成并存档
  `history/report_20260927_1237.md`，结构化解析 4 条动作（全 hold/校准止损，无新成交），
  退出后自动卸载（显存回落到 882M）。下次真实触发：2026-09-28（周一）15:35。
- 注意：通知走 openclaw 且设计上静默失败，本次 12:23 那轮没有新通知记录；
  报告/交易数据是权威凭证，通知只是附属。


## 十五、仓库同步与可维护性整改（2026-09-27）

- `.gitignore` 修复：`test_*.py` 等根目录临时文件规则原会误伤 `tests/` 整个目录，
  导致 CI（pytest tests/）拉不到测试；已全部锚定根目录，并补充忽略 `*.err`/`*.out`、
  `_quarantine/`、`*.db`、`cache/`、`portfolio.pre-*.json`、`.dbvs*` 等运行时产物。
- 运行时数据取消追踪（磁盘保留，可随时再生）：state.db / stock_crewai.db、
  cache/、portfolio.pre-run*、各类 .err/.out 日志残留、.dbvs*、_quarantine/2026-09-26。
- 死代码归档到 `_quarantine/2026-09-27/dead-code/`：agents_pkg（被 agents/ 取代）、
  run_virtual/v2/v3 + launch_virtual.bat + install_task.ps1（旧虚拟盘路线，计划任务
  StockCrewAI_VirtualTrading 本机不存在）、probe_payload / verify_crewai_path /
  smoke_test_crew / integrate_cache / virtual_trader。
  `llm_analyst.py` 经引用核查是 web_dashboard `/api/run_analysis` 的后端，保留在根目录。
  docker 栈（Dockerfile/compose/start.sh/run_loop.bat/run_virtual_v4.py）保持原样。
- 测试：新增 `tests/test_trading_plan_and_cache.py` 29 个用例（schema 清洗/解析/
  渲染、缓存 key/TTL/命中统计、make_cached_llm 装配）。全套 48 个用例通过。
- 顺带修了一个真 bug：`parse_trading_plan` 在 JSON 有 actions 但**全部行非法**时
  返回空 plan 而非 None，crew.py 据此跳过自由文本回退、静默丢单；已改为返回 None，
  显式空 actions 列表仍表示"本轮无动作"。
- 文档：README.md 重写为当前架构（本地 Ollama、自启链、15:35 计划任务、跑完自动
  卸载、.env 键位、测试入口）；`.env.example` 同步为本地 Ollama 默认 + 云端备选注释。

## 十六、分析流水线改为"只出建议、不落盘"（2026-10-03）

### 16.1 用户拍板的事项

第 10.4 节挂了两周的那条决策（调仓智能体在"分析"过程中直接下单改持仓）已由用户拍板：
**改为只出建议**。此前每跑一次日报，LLM 都可能真的动持仓——`result_latest.md`（10-02 15:47）
的"三、已执行操作"里就写着"清仓徐工机械（000425）卖出 600股 @7.20元 ✅"，
run6 更有 4 次 `execute_sell`。计划任务每交易日 15:35 自动跑，等于把不可逆写操作
交给了一个每天自动运行的 LLM 工具循环。

### 16.2 改动

| 位置 | 改动 |
|------|------|
| `crew.py` 新增 `build_agents()` | 七个 agent 的装配（工具白名单 + `max_iter`）从 `run_daily_analysis` 里抽成模块级函数 |
| `crew.py` trader | `get_trade_tools()` → `[view_portfolio, position_size, stop_loss_advice, risk_reward] + notify` |
| `crew.py` rebalancer | `get_trade_tools()+get_risk_tools()` → `[view_portfolio, stop_loss_advice] + notify` |
| `tasks.py` 交易任务 | 删掉"每只股票至多再调一次 set_stop_loss"，改为显式声明"只输出计划，不执行任何交易" |
| `tasks.py` 调仓任务 | "谨慎执行明确的止损/止盈操作" → 逐只输出建议动作 + 触发条件 + 建议股数；`expected_output` 去掉"已执行的操作" |
| `dry_run_offline.py` | 改为调用 `crew.build_agents()`，并打印全部 7 个 agent 的工具 + 断言无写操作工具 |
| `tests/test_stock_crewai.py` | 新增 `TestAgentToolWhitelist`（3 个用例），把这条不变量锁进测试 |

通知类工具（`wechat_notify` / `dashboard_notify`）**原样保留**——是否关掉自动推送是另一个
待决事项，本次没有一并改。

### 16.3 顺带修掉的两处"文档说改了、代码其实没改"

1. **`dry_run_offline.py` 从来验不出工具集回归**：它自己按默认全量工具重建七个 agent，
   与 `crew.py` 的实际传参是两份代码。9/26 情绪工具那次（文档说禁用、代码还挂着 3 个）
   正是这个形状。现在干跑直接调 `crew.build_agents()`，两边不可能再分叉。
2. **交易任务提示词引用了一个 agent 根本没有的工具**：`tasks.py` 要求"position_size 每只
   股票最多调用一次"，但 `TraderAgent` 的默认工具集是 `get_trade_tools()+get_notify_tools()`，
   里面没有 `position_size`。模型只能凭空编股数。现已把 `PositionSizeTool` 真的给到交易员。

### 16.4 保留的写操作

`crew.py:81` 的 `pt.refresh_position_prices()` 仍会写 `portfolio.json`——它只刷新持仓
`last_price`（报告里的盈亏与 VaR 依赖它），不产生成交、不改股数与成本，不属于"下单"。
`pt.check_stop_loss()` 经核查只读不写。`history/trades_*.json` 与 `recommendation_tracker`
的落盘不受影响（后者记的是"推荐"而非"成交"）。

### 16.5 验证（三层，端到端实跑已做）

1. **回归测试**：`pytest tests/ -q` → **56 passed**（`TestAgentToolWhitelist` 3 例锁白名单、
   `TestAgentTradingGate` 5 例锁总开关）。`built_agents` fixture 用 class 级作用域，
   全套耗时 85s → 32s。
2. **离线干跑**：`dry_run_offline.py` → 七个 agent 工具集逐条打印，`写操作工具泄漏 -> 无`；
   数据层 10/10、`PE=`/`PB=` 各 10、峰值 prompt 估算 5600 token（与改动前一致）。
3. **端到端实跑（10/3 22:47–23:02，`crew_run10.log` / `crew_run10.err`，15 分钟）**——
   这是"删掉工具 + 改提示词"之后第一次真跑，也是周一计划任务之前的预演。结果：

   | 判据 | 实测 |
   |---|---|
   | 任务完成数 | `Task Completed` **7 / 7** |
   | 假成功标记 | `Maximum iterations reached` / `absolute best final answer` 命中 **0** |
   | 模型是否还试图下单 | 日志里 `advice_only` / `被拒` 命中 **0**（工具根本不在集合里，模型没去够） |
   | 持仓不变量 | 跑前跑后 `cash 47705.0` 与四只持仓的 `shares/avg_cost/stop_loss/take_profit` **完全一致**；只有 `last_price`/`last_price_time` 刷新（16.4 允许） |
   | 写入时机（更强的证据） | 取证时 `portfolio.json` 的 mtime 停在 **22:48**（即 `[1/8] 准备市场数据` 那一次 `refresh_position_prices`），而流水线一直跑到 **23:02**。后半程 14 分钟没有任何一次写盘 = 交易/风控/调仓三个阶段一次都没碰过持仓文件。（这条只能看当时的 mtime 或日志，事后不能再拿 mtime 复查——后续任何一次运行都会重刷它。） |
   | 报告文案 | `result_latest.md` 标题变为"动态调仓**建议**报告（2026-10-03）"，逐只持仓为「建议动作 + 触发条件 + 建议股数 + 理由」，全文 **0 处**"已执行"表述 |
   | 收尾 | `ollama stop` 后 `ollama ps` 为空，显存已归还 |

   对照旧行为：10-02 那份日报里有"已执行操作 … 清仓徐工机械（000425）—— 已执行 ✅ 卖出 600股 @ 7.20元"，
   且 `portfolio.json` 当场从 5 只/现金 43385 变成 4 只/47705。这一版没有也不会再有。

   > 跑前备份：旧日报存在 git 对象 `8bf9cc92dfc660d68fe6a6e042a7ac19dbfe7b1e`
   > （`git cat-file blob 8bf9cc92… > result_latest.md` 可取回），
   > 以及 `logs/result_pre-advice-gate.log`（`*.log` 被 gitignore，不污染工作树）。
   > 注意 `result_latest.md` 每次运行整体覆盖、无归档目录，所以动手跑之前先这样备份一次。

### 16.6 第二条下单路径已堵：`ALLOW_AGENT_TRADING` 总开关（2026-10-03）

`crew.py` 不是唯一能下单的入口。`workflows/daily_analysis.py` 用 `core/orchestrator.py`
直接注册 `TraderAgent()` 等真实 agent，走的是 `AgentBase.run()` 这条**旧编排路径**，
而 `TraderAgent.run()` / `PortfolioRebalancerAgent.run()` 内部会
`call_tool("execute_buy"/"execute_sell"/"set_stop_loss")`——`agents/*.py` 里
`self.tools = get_trade_tools() + ...`。触发它的入口有两个：`main.py`（`--scheduler`
会起 `core/scheduler.py`，其 `run_daily_analysis()` 就是调这个 workflow）和
`web_dashboard.py` 的 `/api/run_workflow`。自动链路不受影响（本机只有一个计划任务
`stock-crewai-daily-run`，`Get-ScheduledTask` 实测，它经 `run_crew_scheduled.vbs` →
`run_crew_then_release.py` 拉的是 `crew.py`；仓库里没有任何 `.ps1`/`.vbs`/`.bat`
引用 `main.py` 或 `web_dashboard.py`），但手动跑一样会真下单。

**处理方式**：在 `tools/trade_tools.py` 三个写工具的 `_run()` 入口加总开关
`trading_allowed()`——读环境变量 `ALLOW_AGENT_TRADING`，只有 `1/true/yes/on`
（大小写与首尾空格不敏感）才放行，**默认拒绝**并返回
`{"success": false, "advice_only": true, "error": "... Set ALLOW_AGENT_TRADING=1 ..."}`，
同时 `logger.warning` 一行（拒绝不能是静默的）。三个工具的 `description` 也拼上了
`_GATE_NOTE`，万一它们又被塞回某个 LLM 的工具集，模型能提前知道默认只会拒绝，
不至于反复重试烧光 `max_iter`。

选这条路而不是改 `agents/*.py` 的 `self.tools`，是因为：
- `run_virtual_v4.py` 的模拟盘下单**直接调 `portfolio_tracker`**（`:454` 的
  `pt.set_stop_loss`、自带的 `execute_sell`/`execute_buy` 函数），不经过 `tools/trade_tools.py`，
  所以总开关不会误伤模拟盘；
- 改 `self.tools` 会连带改掉 `main.py` 自检打印的工具计数，且 `AgentBase.run()` 里
  `call_tool` 找不到工具是抛异常而不是返回失败，改动面更大。

调用方对拒绝的降级行为已核查：`portfolio_rebalancer.py:102/120` 与 `trader.py:108`
都是 `if buy_data.get("success")` 才记账，拿到 `success=false` 就跳过，不会抛异常。

**验证**（evidence: `tests/test_stock_crewai.py::TestAgentTradingGate`，5 个用例）：
- `trading_allowed()` 的真值解析：`1/true/YES/" on "` → True；`0/false/""/2`/未设 → False。
- 默认配置下三个工具全部返回 `success=false, advice_only=true`，且临时 `portfolio.json`
  的 `positions`/`cash` 分毫未动。
- `ALLOW_AGENT_TRADING=1` 时 `execute_buy` 正常成交（100 股 @10 → 现金 100000→99000）。
- **旧编排路径整条跑一遍**：给一个持有 000425 六百股（成本 8.0、现价 7.0，够到止损条件）
  的组合 + 一个风控已通过的买入候选，直接调 `TraderAgent().run()` 与
  `PortfolioRebalancerAgent().run()`，结果 `portfolio.json` 哈希前后一致、
  `get_trade_history()` 为空。日志可见 `[trade] execute_buy 被拒` 与
  `[Trader] buy failed: ... execute_buy refused`。

全套测试 **56 passed**（16.2 时是 51）。`.env.example` 已补 `ALLOW_AGENT_TRADING`
段落说明；`.env` 未设该键，即当前为只出建议模式。

### 16.7 顺带查出的旧路径 bug（未修，需拍板）

`PortfolioRebalancerAgent.run()` 第 46 行把 `view_portfolio` 的返回当字典用：
`portfolio.get("holdings", [])`。但 `ViewPortfolioTool._run()` 返回的是
`{"summary": <字符串>}`（`pt.get_portfolio_summary()` 拼的是多行文本，不是结构体），
所以 `holdings` 永远取不到 → 第 48-53 行直接返回
`{"action": "NO_ACTION", "reason": "无持仓，无需调仓"}`。

16.6 的验证里复现了：组合明明持有 600 股，旧路径的调仓仍报"无持仓"。
**影响面仅限旧编排路径**（`workflows/daily_analysis.py` / `main.py` / `web_dashboard.py`）；
`crew.py` 走的是 LLM 直接读工具返回的文本，不受影响。

要修就得让调仓拿到结构化持仓——要么给 `ViewPortfolioTool` 加一个返回原始
`positions` 的字段，要么让 `run()` 直接调 `pt.load_portfolio()`。但这会让旧路径
第一次真正开始产出调仓动作（此前一直是空转），属于行为变更，没有顺手改。

## 十七、交接清单（2026-10-03 23:15）

### 17.1 一句话状态

七智能体端到端**已跑通并自动化**（计划任务每交易日 15:35 出 `result_latest.md`），
本地 `qwen3.8-gsq-rco-iq3s` 路线，测试 56 例全绿。本轮把"分析过程真改持仓"这个
遗留了两周的风险彻底关掉：两道防线 + 两组回归测试 + **一次 15 分钟端到端实跑取证**
（10/3 22:47–23:02，7/7、0 假成功、持仓逐字段未变，见 16.5）。

### 17.2 本轮改了哪些文件

| 文件 | 改了什么 |
|---|---|
| `crew.py` | 新增 `build_agents()`（七 agent 装配的唯一入口）；交易员/调仓师工具白名单剔除 `execute_buy`/`execute_sell`/`set_stop_loss`，并给交易员补上 `position_size` |
| `tasks.py` | 交易任务删掉 `set_stop_loss` 指令、加"只输出计划不执行"；调仓任务整段改为出建议，`expected_output` 去掉"已执行的操作" |
| `tools/trade_tools.py` | 新增 `trading_allowed()` 总开关（默认拒绝）与 `_refusal()`；三个写工具 `_run()` 首行拦截；`description` 拼 `_GATE_NOTE` |
| `dry_run_offline.py` | 改为调 `crew.build_agents()`；打印全部七 agent 工具集；对写操作工具做断言 |
| `tests/test_stock_crewai.py` | 新增 `TestAgentToolWhitelist`（3 例）+ `TestAgentTradingGate`（5 例） |
| `.env.example` | 补 `ALLOW_AGENT_TRADING` 段落 |
| `HANDOVER.md` | 头部与第六节改成本地 Ollama 现状（新增 6.1：num_ctx 校准脚本越界改写无关模型）；10.4/11.6/12.5/14.4 四处"待用户拍板/会真实下单"改为已落地；新增第十六、十七节；命令速查整段重写；16.5 补端到端实跑取证 |
| `result_latest.md` | 被 10/3 23:02 那次实跑整体覆盖（旧版备份见 16.5 末尾） |

`.env` 本身**没改**（仍不含 `ALLOW_AGENT_TRADING`，即默认只出建议）。
`portfolio.json` 全程只有 `last_price` / `last_price_time` 被刷新（16.4 允许的那条路径），
`cash 47705.0` 与四只持仓的 `shares/avg_cost/stop_loss/take_profit`
在干跑与实跑前后**逐字段一致**（基线见速查第 5 条）。

### 17.3 接手后怎么确认我没骗你

```powershell
cd D:\aishare\repo\stock-crewai-master
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $py -u -m pytest tests/ -q        # 56 passed
& $py -u dry_run_offline.py          # 必须出现「写操作工具泄漏 -> 无」
Select-String -Path crew.py,tools\trade_tools.py -Pattern "build_agents|trading_allowed"
# 本轮实跑取证（16.5）：Task Completed 应为 7，假成功与 advice_only 都应为 0
Select-String -Path crew_run10.log -Pattern "Task Completed" -AllMatches | Measure-Object
Select-String -Path crew_run10.log -Pattern "Maximum iterations reached|absolute best|advice_only|被拒"
```

> Git Bash 下 `schtasks /query /tn …` 的 `/tn` 会被 MSYS 当路径吃掉
> （报"找不到 D:/Program Files/Git/query"）。加 `MSYS_NO_PATHCONV=1` 前缀或在 PowerShell 里跑。

### 17.4 三件未决事项（都要用户拍板，别擅自改）

1. **旧编排路径的调仓永远报"无持仓"**（16.7）。`PortfolioRebalancerAgent.run()` 按
   `portfolio.get("holdings")` 读 `view_portfolio`，而后者返回 `{"summary": <字符串>}`。
   影响面仅 `workflows/daily_analysis.py` / `main.py` / `web_dashboard.py`。
   修它 = 让一条一直空转的路径第一次真产出动作，是行为变更。
2. **微信推送仍开着**。`crew.py:notify_wechat()` 走 `openclaw`（在 PATH 上），
   交易员/调仓师还带着 `wechat_notify`/`dashboard_notify`。本轮只处理"写持仓"这类副作用，
   通知类是有意保留的。要关就两处一起处理，否则只关一处等于没关。
3. **`start_local_stack.ps1` 的 num_ctx 校准作用域过大**（6.1）。它扫描全部参数 blob
   并改成 16384，10/2 已实测把一个无关模型 `q38-lite` 的 `{"num_ctx":8192,"num_gpu":56}`
   静默改成了 `{"num_ctx":16384}`（连 `num_gpu` 一起丢了）。现在无故障，导入新模型时会被改。

### 17.5 这个仓库特有的坑（按杀伤力排序）

1. **不要用 Write/Edit/Bash 往任何文件里写密钥**：入参里形似密钥的串落盘前会被替换成
   `前4…后4`（`…` 是字面 U+2026），`Read` 会把显示层还原，看起来完整其实只剩 11 字节。
   判据只有量字节。密钥一律由用户本人粘贴。
2. **`dry_run_offline.py` 之类"验证脚本"必须调被测代码的同一入口**。它此前自建 agent
   副本，导致工具集回归一路验不出来（9/26 情绪工具、10.3 position_size 都是同一形状）。
   新加验证脚本时先问：它验的那份配置，和生产代码是同一个来源吗？
3. **Python 必须用 3.12 且必须加 `-u`**：`$env:LOCALAPPDATA\Programs\Python\Python312\python.exe`。
   不加 `-u` 日志会长时间 0 字节。
4. **`L2/L3` 安全扫描在本机是关的**（`security-scan-settings.cmd` 回 `l2_enabled=false,
   l3_enabled=false`，host `qoder_sdk`）。被选中某个模式 ≠ 该模式已开启；
   没跑过的工序不能说成跑过，也不能说"没发现问题"。
5. **改 `.ps1` 必须保留 UTF-8 with BOM**（14.6 坑 1），否则 PowerShell 5.1 按 GBK 误读，
   中文注释会把紧随其后的可执行行啃坏。
6. **Ollama 只用 `ollama serve`，永远别启托盘**（13.3：托盘会把版本自动升回 0.34.4 打挂推理）。
7. **终端回显中文会乱码**（cp936 / UTF-16LE 都救不回来）。要判断结果就让脚本只输出 ASCII，
   或写文件后用 Read 看。16.6 那两条被拒日志就是靠 ASCII 字段（`advice_only=true`）而非
   中文正文确认的。


## 十八、精简代码（2026-10-04）

目标：不改行为，删死代码、合重复实现、清无效导入。每步都跑 `pytest tests/ -q`（基线 56 passed）。

### 18.1 删除内容

- `ad976a3` — `strategy_momentum.py` 里 59 行重复的 `get_sina_realtime()`，与 `data_fetcher.py` 同名函数输出结构完全一致；改为 6 行 `_quote()` 委托，行情解析收敛到唯一实现。
- `00729f2` — `data_fetcher.get_stock_info` / `get_financials`，全仓零调用点。
- `bc17250` — 整模块归档 `db.py`（206 行 SQLite 层，无 import）与 `alert.py`（116 行，无 import）；另删 `technical_indicators.generate_signal`、`recommendation_tracker.track_performance`、`llm_analyst.market_overview_report`、`portfolio_tracker.auto_sell_triggered`。
- `e430b46` — 5 个文件 12 处未使用导入（`numpy`、`asyncio`、`sys`、`time`、`Optional` 等）。

归档而非删除：两个模块移到 `_quarantine/2026-10-04/unused-modules/`，git 历史可回溯。

### 18.2 顺带修掉一个真 bug

`config.py` 缺 4 个 `CIRCUIT_BREAKER_*` 常量，而 `circuit_breaker.py` 在 import 时就 `from config import (...)` 它们，因此该模块此前完全无法 import。`tools/risk_tools.py:181` 与 `crew.py:272` 都挂着 `CircuitBreakerCheckTool`，风控智能体的 `circuit_breaker_check` 工具一调就崩。已按现有风控口径补常量：单日亏损 8%、连续 3 次止损、冷却 60 分钟、状态文件 `circuit_breaker_state.json`。修复后 `crew → tools.risk_tools → agents.risk_manager_agent → circuit_breaker` 全链路 import 通过。

### 18.3 刻意保留、没动的东西

- `data_fetcher.get_fundamental_data`：看着像死代码，但它是包在活的 `get_fundamental_batch` 上的 2 行公开包装，docstring 声明了对外契约。
- `web_dashboard.py` 全部 `api_*`：Flask `@app.route` 注册，没有文本调用点，静态扫会误判。整模块实测零死函数。
- `run_virtual_v4.py`（718 行）：仍是 `docker-compose.yml:19` 的 CMD，是活的。合并它属于架构决策，不是机械删除。
- `__init__.py` 的再导出（`agents/`、`core/`、`workflows/`）：公开 API，非死代码。

### 18.4 审计方法（下次直接用）

死代码扫描用 AST，别用正则。第一版正则漏掉多行 `from x import (a, b)`，报了 122 条假阳性；改成 `ast.walk` 收集 `ast.Name`，减去已用名后剩下的才是真死导入。删除前必须确认三件事：定义处是否为唯一引用、有无 `__main__` 调用、文档或装配是否提到。



## 十九、代码精简续：模块拆分与指标合并（2026-10-04 晚）

第十八节之后继续做了两件结构性的事，都跑满 56 测试。

### 19.1 `data_fetcher.py` 拆包（`3647d6b`）

716 行拆成 `data_sources/` 六个模块，`data_fetcher.py` 保留为再导出门面（46 行），
所以 29 个调用点（`import data_fetcher as df` 后 `df.get_xxx`）零改动。

- `_common.py` 220 行：代理绕过补丁、akshare 懒加载、A_SHARE_POOL、_sina_kline_direct
- `kline_prices.py` 123 行：get_index_components / get_stock_price / get_batch_stock_prices
- `fundamentals.py` 105 行：get_fundamental_batch / get_fundamental_data / get_news_sentiment
- `market.py` 191 行：get_market_heat / get_market_regime / get_sector_performance
- `technical.py` 83 行：calculate_technical
- `quotes.py` 179 行：get_realtime_quotes / get_sina_realtime / get_simple_market_regime

拆分前确认的关键事实（下次拆别处先查这些）：

- 786 行全部有归属，按行区间六等分无丢行；
- 跨段依赖只有一处：market 段调用 `_sina_kline_direct`，把它提到 `_common.py` 即消除循环导入；
- 唯一的边界瑕疵是 `@cached` 装饰器落在上一段末尾，已移到 `quotes.py` 的 `get_realtime_quotes` 上；
- 拆完必须做真实调用验证，不能只看 import：实测 `get_stock_price` 取回 250 行 K 线、
  `calculate_technical` 算出 13 个指标、regime/heat 有数据、断网时优雅降级为震荡市。

### 19.2 量化指标合并，并修掉一个共有 bug（`a23ae93`）

`calculate_max_drawdown` / `calculate_sharpe` 在 `backtest.py` 与 `performance_report.py`
各有一份，写法不同（一处 `(peak-v)/peak*100` 直接返回，另一处 `/peak` 后 `*100`）。
已对正常输入做等价验证：回撤 33.3333、夏普完全相同，合并不改变行为。

合并时发现两份代码共有的缺陷：**peak 为 0 时抛 `ZeroDivisionError`**，且崩在不同行号
（backtest.py:241 与 performance_report.py 对应行）。收敛到 `quant_metrics.py` 后加
`peak <= 0` 保护，返回 0.0。

### 19.3 查过但**故意没动**的

- `run_virtual_v4.py`（713 行，现最大文件）：它是 Docker/loop 的下单路径，而 `tests/` 里
  唯一提到它的地方是一句注释——**零测试覆盖**。没有测试保护时拆会真实下单的生产路径，
  风险显著高于收益，等有测试再拆。
- `crew.py`（485 行）：仅 7 个函数且职责内聚（编排器本就这么长），拆散反而把流水线弄乱。
- `tools/*.py` 的 8 个 `get_*_tools()` 工厂：AST 归一化后检出 market/trade 两份同构，但各自
  返回不同的工具类清单；强行抽公共 helper 会让调用点看不出挂了哪些工具，可读性下降。
- 461 行 `__main__` 演示块（27 个文件）：是能跑的 CLI 演示（如 `python strategy_momentum.py`
  会打印行业动量报告），不是死代码；文档里没有登记入口，属于可用但未文档化，等用户拍板。

### 19.4 顺手纠的文档漂移（`3113cf2`）

README 的测试数从 48 改成 56；目录树补 `data_sources/`；更新日志加 v4.4.0。
历史条目里的 48 个测试保留原样（那是 9/27 当天的事实）。



## 二十、依赖与配置精简，并修掉一个静默失败（2026-10-04 深夜）

第十九节之后转向非代码部分的精简：依赖清单和配置项。两处都是真的会咬人的。

### 20.1 requirements.txt 与实际 import 对齐（fd3e3ab）

用 AST 扫全部 py 文件的顶层 import，与 requirements.txt 逐项对账：

- 删掉 langchain-openai：全仓 langchain 出现 0 次，是 LM Studio/OpenAI 旧路线的残留；
  本地 Ollama 走 crewai 的 OpenAI 兼容端点，不需要它。删后全模块 import 与 56 测试均通过。
- 补上 9 个实际直接 import 却没声明的包：requests、pydantic、numpy、openai、tenacity、
  filelock、python-dotenv（原已声明）、pytest 及 dev 工具链。这些目前靠 crewai 传递依赖顺带装上，
  能跑纯属侥幸——crewai 一改依赖树就崩。
- 按用途分段并加注释（LLM 编排 / 数据获取 / 结构化输出 / 配置重试 / Dashboard / 可选实盘 / dev）。

### 20.2 删掉 12 个死配置项（3f64cc6）

用正则查 config.py 里每个大写键在全仓的出现次数，refs==1（只有定义）即死。33 个键删掉 12 个：

- CACHE_TTL_REALTIME / MARKET / KLINE：真正的 TTL 在 api_cache.py:97-100 硬编码
  （10/300/60/30），改这里的值静默无效，是最容易骗人的一项。
- API_BASE_URL：默认值还是 OpenRouter，而栈早已换本地 Ollama，纯误导。
- TRADE_LOG_FILE：没有任何代码读它，真实文件名散落在调用处。
- TECH_SCORE_WEIGHTS、MIN_TECH_SCORE：技术评分逻辑未接线，权重表是摆设。
- NEAR_TAKE_PROFIT_PCT、STOP_LOSS_CHECK_ENABLED、ATR_STOP_LOSS_ENABLED、
  ATR_HOLDING_DAYS、DASHBOARD_REFRESH_SECONDS：均无读取方。

顺带修了 CIRCUIT_BREAKER 段与上方风险控制段之间丢了的空行（第十九节补常量时带进来的）。
删后剩 22 个键，全部有真实读取方。

### 20.3 修掉微信通知静默失败（81aaded）

这条解释了 HANDOVER 里挂了很久的“通知走 openclaw 且设计上静默失败”。
真实原因更简单也更蠢：wechat_notifier.py 把 webhook 地址硬编码成占位符，
从不读环境变量。所以 .env.example 里登记的 WECHAT_WEBHOOK_URL 一直是无效配置——
用户填了 key 也不会有任何通知，也不报错。

改为 os.getenv('WECHAT_WEBHOOK_URL', '').strip() or _PLACEHOLDER，两条路径都实测过：
未设置 -> 打印 Webhook未配置，跳过 并返回 False；已设置 -> 取到 env 值且不再被判为占位符。

### 20.4 验证

每个提交都单独跑：compileall 全仓、关键消费方 import（crew / circuit_breaker / run_virtual_v4 /
web_dashboard / core.scheduler）、pytest tests/ -q 56 passed。



## 二十一、补测试拆掉“不敢动”的借口，并修掉最后一处非原子写（2026-10-05）

第十九节说 run_virtual_v4.py 因为零测试覆盖所以不拆。这一节就是去补那个覆盖。

### 21.1 check_portfolio_risk 全覆盖（c2f0583 / 7766467）

第一批 13 个用例覆盖固定止损 / 止盈 / 预警三条分支与边界：

- 止损线恰好等于现价时触发、高于现价不触发；
- stop_loss 未设置（0）时**永不触发**——不能把 0 当止损线，这是最容易亏钱的口子；
- 行情缺失时依次回退 last_price -> avg_cost，不 KeyError；
- 停牌（价格 0）跳过，不除零；
- 同时命中止损与止盈时只出一条（elif 链）。

第二批 5 个用例覆盖 ATR 动态止损，用 patch.object(rv, 'ti') mock 掉取数：

- ATR 算出的动态止损更严时采用它；
- **动态止损比固定止损宽时必须钳制回固定值**（核心资金保护，之前完全没测）；
- K 线不足 14 根、持仓不足 3 天时放弃 ATR 退回固定止损；
- mock 被调用/不被调用的断言，确认分支真的走进去了。

### 21.2 MockTrader 只读路径（1a16afe）

6 个用例：portfolio.json 缺失时给默认 10 万、
缺 cash 键时默认 0 并正确算市值、缺 last_price 时用 avg_cost 兜底、
空持仓返回 []。全部走 tmp_path，不碰真实持仓文件。

### 21.3 修掉 trades_real.json 的非原子写（ede46a5）

顺手扫了全仓 15 处 json.dump 直写。结论：

- portfolio.json（portfolio_tracker.py:51）与 trades_YYYYMM.json（:201）**已经是原子的**，
  且注释里记录了 9/26 的撕裂写事故与复现条件，这两处不用动；
- trades_real.json（broker_trader.py:127）是剩下唯一一处交易日志裸写，
  已改成与上面一致的 tmp + os.replace + 异常清理。实测连写两笔、
  累计正确、无 .tmp 残留；
- run_virtual_v4.py 的两处：运行日志是带时间戳的唯一文件名（撕裂无害），
  净值历史是读-改-写但有 check_single_instance() 进程级单实例保护，
  并发风险低。该文件按第十九节决定不做结构性改动，此处仅记录。

### 21.4 数字

测试数 56 -> 80（新增 24 个），全部通过。
run_virtual_v4.py 从“零测试覆盖”变成撤价计算逻辑有 18 个用例守着，
下次要拆它已经有安全网了。



## 二十二、有了测试后拆 run_virtual_v4：绩效与下单价位抽出（2026-10-05）

第十九节说这个文件零测试覆盖所以不拆，第二十一节把覆盖补到 18 个用例，
这一节就把当初“不敢动”的部分拆了。

### 22.1 绩效指标抽出（9c593cf）

calculate_performance_metrics 原本在 run_virtual_v4.py 里内联 70 行，
且**重复实现了最大回撤和夏普**（第十九节刚把另外两份合并掉，这是漏网的第三份）。

抽成 performance_metrics.py，并把 I/O 与计算分开：

- read_total_values(history_dir)：只负责按 mtime 读 run_log_*.json 取净值，坏文件跳过；
- compute_metrics(values)：纯函数，只吃净值序列吐指标dict，可直接单测。

等价性验证：对 6 组净值序列（上涨/下跌/震荡/横盘/样本不足/含 0 值）与原内联实现
逐字段比对，结果完全一致；抽出的版本额外不会在净值为 0 时崩。
run_virtual_v4 里只剩 7 行委托，并对真实 history/ 目录实测跑通（21 笔日志）。

### 22.2 下单止损止盈价抽出（de0bc08）

execute_buy 里的价格档位计算是直接决定亏多少钱的部分，原来是三分支嵌套：
ATR 成功 / analysis 无 atr / analysis 抛异常，且固定比例的写法重复出现了 3 次。

抽成 order_levels.py：

- resolve_levels(price, atr, ...)：ATR 有效走动态，缺失或为 0 或取数失败一律退回固定比例；
- fixed_levels / atr_levels：两个原子计算，便于单独验算。

等价性验证：5 个价格 x 5 种分支行为共 25 种组合逐值比对，与原实现完全一致，
包括 atr=0 回退固定比例（原实现靠真值判断，行为相同）。

### 22.3 数字

run_virtual_v4.py：713 -> 648 行（两轮共减 65 行，且减掉的都是有测试守着的逻辑）。
测试数：80 -> 107。

剩下的 648 行是 wiring 与 I/O（run_once / main / execute_buy / execute_sell / advanced_filter），
继续拆收益递减，且 execute_* 动到真实下单，要进一步拆得先给它们补集成级测试。



## 二十三、循环依赖审计 + 清掉第三套缓存（2026-10-05）

### 23.1 模块依赖图审计

用 AST 建 import 图跑环检测：**循环依赖 0 个**，依赖方向是干净的。
fan-in 排名（被多少模块 import）：tools 17、core 14、data_fetcher 13、
portfolio_tracker 11、agents 8、api_cache 7、config 5、backtest 4。
另外确认了 data_sources 拆分没有被绕过：全仓只有 data_fetcher.py 一个门面引用它，
没有调用方直接 import 子模块。

### 23.2 tools/compat.py 的死分支（af5e914）

compat.py 原本是“装了 crewai 就用原生 BaseTool，否则用 pydantic 兜底”。
实测 compat.BaseTool is crewai.tools.BaseTool 为 True，且 crewai 是硬依赖
（crew.py:8 与 tasks.py:5 在模块层无条件 import，requirements.txt 也声明了），
所以兜底分支永远走不到。改成纯再导出，5 个工具模块的 import 一行没动。

顺带发现 core/agent_base.py:187 也有一句“crewai not installed, using fallback”，
但它 return None 会改变函数契约，且窟窿比 compat 大，本轮**故意没动**，只记录。

### 23.3 web_dashboard 复用 TTLCache（ad07400）

dashboard 里手写了一份 _cache dict + 30s TTL，这是仓库里第三套缓存实现
（前两套是 api_cache.TTLCache 和各处的 cached 装饰器）。
改成复用 TTLCache。难点：调用方要区分“命中但值为 None”和“未命中”，
而 TTLCache.get 两者都返回 None；保持 (value, hit) 签名不变，
未命中统一 hit=False，5 个调用点零改动。
已实测 miss/hit/过期三种路径行为与改造前一致。

### 23.4 补 dashboard 路由测试

补 7 个用例：/api/health、/api/scheduler_status、/api/agent_status、
/api/agent_events、/api/agent_state/<不存在的key>、/ 首页渲染、缓存 helper。
用 Flask test_client，不起服务不碰网络，同时给 23.3 的改动兜底。

### 23.5 数字

测试数 107 -> 114。web_dashboard.py 现在有路由级覆盖，
下一步要动它的 20 个 handler 已经有安全网了。



## 二十四、第三份指标实现合并 + dashboard 撕裂写修复（2026-10-05）

### 24.1 performance_auditor 的第三份指标实现（f128827）

在翻 web_dashboard 时发现 agents/performance_auditor.py:_calculate_metrics 里
还有**第三份**收益率/夏普/回撤实现（这次用 numpy）。前三轮已合并过两份
（backtest.py 与 performance_report.py -> quant_metrics），这是漏网的。

已收敛到 performance_metrics.compute_metrics，保留该 agent 自己的输出键
（data_points 映射自 total_days），调用方无感。

**注意一处有意的数值变化**：原实现用 np.std（总体标准差），
共用实现用样本标准差（n-1）。实测 annual_volatility 会差约 2.8%
（例：52.77 -> 54.22），sharpe 随之小幅变化；
max_drawdown / annual_return / win_rate 三项完全一致。
样本标准差对“一组样本收益率”才是统计正确的选择，所以朝这个方向统一；
如果下游有硬编码阈值依赖旧值，需要按新值复核。

### 24.2 修掉 dashboard 的撕裂写（c6b1917）

api_dashboard 在 **GET 路径**上对 net_value_history.json 做读-改-写，
用的是裸 open("w") + json.dump，无锁无原子替换。
这是 HANDOVER 9.2 / 11.4 记录过的同款事故模式（portfolio.json 和
trades_*.json 都踩过），而且 dashboard 天生并发：两个浏览器标签页
同时开面板就会触发。

已改为 safe_io.safe_save_json（持锁 + tmp + os.replace）。
实测：写入读回一致、追加正常、无 .tmp / .lock 残留。

另外确认 net_value_history.json 的写入方有三个：
web_dashboard（2 处）、agents/performance_auditor（读）、
run_virtual_v4（net_value 记录）。这个文件是共享的，
后续再动它必须走 safe_io。

### 24.3 数字

测试数维持 114（本轮是重构与修 bug，未加用例；
performance_metrics 的等价性在上两轮已用 6 组序列逐字段验证过）。

全仓 json.dump 直写从 15 处降到 14 处，剩下的都判断过：
带时间戳的唯一文件名（撕裂无害）或有单实例保护。



## 二十五、下单执行端补测，并标记一处恒真条件（2026-10-05）

上上轮说 run_virtual_v4.py 剩下 648 行里 execute_buy / execute_sell 还没有安全网，
这一节补上。

### 25.1 execute_buy / execute_sell 测试（1123f2a）

11 个用例，全部 monkeypatch 掉 pt 与 NOTIFIER_AVAILABLE，在内存里跑，
不碰真实 portfolio.json：

买入侧：

- 资金足够时成交，且止损止盈按固定比例算对（10 元 -> 9.2 / 12.0）；
- 资金不足跳过；
- 持仓数已达 MAX_POSITIONS 不再买；
- 价格为 0 跳过；
- update_position 返回 error 时不计入 buys；
- 仓位占比超限停买 / 卡在限值上仍放行（边界）。

卖出侧：

- STOP_LOSS / TAKE_PROFIT 会卖，WARNING 不会；
- 未持仓的 code 跳过；
- 价格为 0 跳过；
- pnl 计算正确（(10-11)*300 = -300）。

### 25.2 发现一处恒真条件，但**故意没改**（2f9448b）

execute_buy 算仓位占比时写的是：

    if code in realtime_data or True

这个条件恒为真。原意应该是 `if code in realtime_data`（只按有实时行情的持仓算），
但写成恒真后，**没有行情的持仓也会按 avg_cost 计入占比**。

实测影响（10 万资本、8000 股 @ 成本 10 元）：

- 恒真版本：占比 80,000 / 100,000 = 0.80
- 收紧版本：占比 0

也就是说当前实现更容易把 position_ratio 推过 MAX_POSITION_RATIO(0.80)，
从而拦掉本可以进行的买入；用的是陈旧成本价而非现价。

这是风险敞口变化，按本项目惯例不擅自改，只做两件事：

- 在代码处写清这段历史与收紧后会怎样；
- 用 test_holdings_without_live_quote_still_count 把现状钉住，
  以后谁想改立刻看得见改了什么。

要不要收紧，需要你拍板。

### 25.3 数字

测试数 114 -> 125。run_virtual_v4.py 的下单执行端（execute_buy / execute_sell）
从零覆盖变成 11 个用例守着，加上此前的撤价 18 个，这条路径已有基本安全网。



## 二十六、清理零引用的遗留启动脚本（2026-10-05）

前面都在清 Python，这轮查启动脚本这类“也是代码”的东西。

### 26.1 引用审计

对 9 个 .ps1/.vbs/.bat/.sh 逐个查“除自身外还有谁引用”：

| 脚本 | 外部引用 | 判定 |
|------|----------|------|
| run_crew_scheduled.vbs | 14 | 活，计划任务的动作 |
| start_local_stack.ps1 | 4 | 活，开机自启守卫 |
| ensure_run_schedule.ps1 | 3 | 活，注册/刷新计划任务 |
| run_loop.bat | 2 | 活（Docker 栈，仅文档提及）|
| start.sh | 2 | 活（Docker 栈）|
| start-lm-studio.ps1 | 0 | 归档 |
| check_api.ps1 | 0 | 归档 |
| autostart.ps1 | 0 | 归档 |
| start-stock-crewai.ps1 | 0 | 归档 |
| harness-start.bat | 0 | 归档 |

现行链路（未动）：stock-crewai-autostart.vbs -> start_local_stack.ps1 ->
ensure_run_schedule.ps1 -> 计划任务 stock-crewai-daily-run ->
run_crew_scheduled.vbs -> run_crew_then_release.py。

### 26.2 归档的五个（bf43295）

- start-lm-studio.ps1：启动 LM Studio 等 1234 端口。本地栈 9/26 已换 Ollama
  （11434），无人调用。
- check_api.ps1：探测 localhost:1234/v1/models，即 LM Studio 的端口，Ollama 路线下不适用。
- autostart.ps1：登录时拉 Ollama + Docker + compose up。已被 start_local_stack.ps1
  取代（后者还锁 cuda_v12、校准 num_ctx、注册 15:35 任务）。
- start-stock-crewai.ps1：同时代另一个登录自启，功能与 autostart.ps1 重叠且依赖 Docker。
- harness-start.bat：启 Claude Harness/Codex 开发环境 + harness_guard.py，
  与交易流水线无关的开发期工具。

归档到 _quarantine/2026-10-05/legacy-launchers/ 并附 README 说明各自由来，
不直接删除以便回溯。

### 26.3 验证

- 计划任务 stock-crewai-daily-run 仍为 Ready，动作仍指向
  D:\aishare\repo\stock-crewai-master\run_crew_scheduled.vbs（未动）；
- start_local_stack.ps1 / ensure_run_schedule.ps1 / run_crew_scheduled.vbs /
  run_crew_then_release.py 四个文件都在位；
- 这两个 .ps1 通读过，每步都有注释说明原因，无死分支，未改；
- compileall 干净，125 测试全过。

### 26.4 根目录现状

启动类只剩 4 个文件（2 个 ps1 + 1 个 vbs + run_crew_then_release.py），
加上 Docker 那组（Dockerfile / docker-compose.yml / start.sh / run_loop.bat /
run_virtual_v4.py / DOCKER.md）。此前那一堆 LM Studio、harness、API 探测的
残留清完了。



## 二十七、清理过期文档，并修掉 CONTRIBUTING 里的坏示例（2026-10-05）

### 27.1 归档 5 份过期文档（5e873e4）

先查每份文档“除自身外还有谁引用”，零引用的有 6 份；
再逐份核对内容是否描述已归档的东西：

- DBHT-KNOWLEDGEBASE.md   Horse Farm 工具生成的项目清单，列的是一批
  已不存在的文件（agents.py、fix_last_price.py、install_task.ps1、
  launch_virtual.bat、run_virtual*.py、virtual_trader.py、test_all.py），
  需求一栏还写着“优化”。
- README_VIRTUAL.md       讲 run_virtual.py / launch_virtual.bat /
  install_task.ps1 这三个都已归档的虚拟盘脚本；唯一引用它的就是上面那份清单。
- LMSTUDIO_VS_OLLAMA.md   LM Studio 与 Ollama 的选型对比；结论（用 Ollama）
  在 HANDOVER 第 11/13 节，这份对比本身已无引用。
- harness/PROFILE.md       描述 Claude Harness 开发环境，与 harness-start.bat
  一同退出（见 26.2）。
- docs/docker-restore-record.md  旧 Docker 部署的恢复记录。
  CI 只检查 docs/ 目录存在，删这个文件不影响流水线。

归档到 _quarantine/2026-10-05/stale-docs/ 并附 README 说明各自由来。
harness/ 目录因此变空，一并删除。

归档后根目录只剩 5 份 md：README / CONTRIBUTING / DOCKER / HANDOVER /
result_latest.md（实跑产物），docs/ 下留 multi-agent-architecture.md 与 openapi.yaml。

### 27.2 修掉 CONTRIBUTING.md 的坏示例

这份指南没归档，因为改改还有用。但它有三处会直接坑到新人：

- 让人跑 pytest tests/test_indicators.py —— 该文件不存在（3 处引用）；
- RSI 示例只给 7 个价格，而 calculate_rsi 默认 period=14，样本不足返回 None，
  于是照着抄的 assert 立刻 TypeError 崩掉（实测 7 个 -> None，30 个 -> 60.0）；
- 注释里的文件名也是那个不存在的文件。

已改为指向真实测试文件，并把 RSI 示例换成 30 个样本、先断言 is not None 再查范围，
实测该示例能跑通。MACD 示例（[100]*50）验证过可用，未动。

### 27.3 验证

CONTRIBUTING 的 RSI 与 MACD 示例都实际执行通过；
docs/ 目录仍在（CI 的 test -d docs 不会失败）；
README/CONTRIBUTING/DOCKER 三份文档里没有指向已归档文档的死链；
compileall 干净、125 测试全过。



## 二十八、CI 与 wiki 残留清理（2026-10-05）

### 28.1 dependabot 死规则（076dfb7）

`.github/dependabot.yml` 里还为 langchain-openai 留着版本忽略规则，
而这个包在第二十节已从 requirements.txt 删掉（全仓 import 为 0）。
规则留着只会让 dependabot 去关注一个不存在的依赖。

删除过程中差点弄坏东西：我的脚本按行区间删，把紧邻的 pandas
version-requirement 也一起删了，等于放开了 pandas 3.x 升级通道——
而那正是该规则要防的 breaking change。已恢复为 >=2.0.0,<3.0.0。
numpy / torch / transformers 的忽略规则保留（那几个仍在依赖树里）。
删完用 yaml.safe_load 解析验证，5 条规则与预期一致。

### 28.2 wiki 残留归档（076dfb7）

- wiki/projects/claude-harness-health.md：harness_guard.py 在 6/20 生成的
  “正常运行”快照。那个 harness 已在 26.2 连同 harness-start.bat 一起退场，
  这份快照是它唯一的产物，留着只会让人以为 harness 还活着。
- wiki/index.md：由 Auto-sync Wiki 工作流生成，但生成的 markdown 里有
  **未渲染的 shell 语法**（$(git log --oneline -5 | ...) 原样出现在代码块里，
  因为替换写在了围栏代码块内，永远不会被执行）。内容又只是重复 git log。

两个文件连同 harness/PROFILE.md 那批一起归档到
_quarantine/2026-10-05/stale-wiki/ 并附说明；wiki/ 空目录已删。
wiki-sync.yml 工作流**故意保留**：它每次跑都会 mkdir -p wiki 重建目录，
删空目录不影响它；真要下架这个工作流属于部署行为变更，超出精简范围，
记录在此供后续决定。

### 28.3 CI 的 lint 步骤是装饰品（本轮未改，仅记录）

ci.yml 里 black / isort / flake8 三个检查都以 `|| true` 结尾，
即无论查出什么问题都返回成功，CI 永远是绿的。

本想改成真正的门禁，但本地没装 black 无法预判结果，且这个仓库
从未按 black 格式化过（随处可见 `import sys; sys.stdout.reconfigure(...)`
单行写法、混合换行符），改成硬门禁极可能让每次 push 直接变红，
比现状更糟。要真上门禁得先跑一次 black --diff 评估改动量，
那是独立的一次改动，不塞进精简。

### 28.4 验证

dependabot.yml 经 yaml.safe_load 解析通过、5 条规则符合预期；
wiki/ 已不存在，wiki-sync.yml 的 mkdir -p wiki 保证其仍可自愈；
compileall 干净、125 测试全过、工作树干净。



## 二十九、上一轮遗留改动定性（2026-10-05）

### 29.1 _pth.txt：pytest 报告误重定向的产物（已删）

上一轮结束时工作树里有一个未跟踪的 835 字节 _pth.txt。逐字看过，
内容是 125 passed, 22 warnings in 54.51s 的 pytest 终端报告——
没有任何用户数据，也没有 .pth 路径文件该有的内容。
创建时间 21:34，早于 .venv 的 22:54，可确定是上一轮把 pytest 输出
重定向时写错了目标文件名；文件名看着像 Python 的 .pth 机制才显得可疑。
纯噪音，已删除。

### 29.2 .gitignore 的 .venv/ 一行：该留，且这个 venv 现在是主力

.gitignore 新增的 .venv/ 对应仓库根这个目录，创建时间 22:54、
紧随 22:55 的 .gitignore 修改，两者是同一轮操作。
原以为只是装 black 的临时环境，实际装了约 300 个包，
含 crewai 1.15.23 / pytest 9.1.1 / pandas 3.0.6 / flask / akshare 等完整依赖。

它是当前沙箱外唯一顺畅可用的 Python：系统 Python312 在沙箱里启动即
拒绝访问（提权后可启动），本 venv 提权后一切正常。
本节的 lint 统计与 125 passed 基线都由它产出，已用 check-ignore -v
确认 .venv/Scripts/python.exe 命中第 9 行规则、_quarantine/ 命中第 92 行。

所以 .venv/ 下一节若决定统一用这个 venv 跑验证，它就不再是临时物。

### 29.3 CI lint 硬化的成本（28.3 的数字补齐）

用本 venv 的 black 26.5.1 / isort 9.0.2 / flake8 7.4.1 实测：

- `black --check .`：**74 个文件**需要重排，diff 上万行量级，
  绝大多数是模块 docstring 后空一行、长 f-string 折行、列表字面量展开
  ——纯风格噪音，但会让整个仓库的 git blame 全部翻页。
- `isort --check-only .`：12 个文件报 ERROR（import 分组与空行不合规），
  且对 crew.py / dry_run_offline.py 等 8 个文件直接 Unable to parse
  （print 里的 emoji 触发 gbk codec 报错），说明 isort 在 GBK 终端下不可用。
- `flake8 --max-line-length=120`：多次尝试均无稳定输出（退出码与文本都拿不到），
  不能作为门禁依据。

结论与 28.3 一致且更硬：**不宜硬化为 push 门禁**。真要管，只对
git diff 触及的文件跑 `black --check` 才是低成本门禁，但这属于
CI 行为变更，需单独确认后再动。

### 29.4 基线复核（本 venv）

`pytest tests/ -q`：125 passed, 22 warnings in 28.21s（系统 Python 为 54.51s）。
`compileall` 源码目录与根目录 .py：干净（注意必须排除 `.venv/`，
否则 venv 自带的 crewai_cli 模板 {{folder_name}}/tool.py 会报 SyntaxError，
那是包内的 Jinja 模板，不是本仓库问题）。

工作树现在只剩打算提交的 `.gitignore` 一行改动。


## 三十、归档零引用死模块，并移除 tenacity 直接依赖（2026-10-05）



### 30.1 归档的三个死模块



用 AST 解析出全部 import / from-import 语句的目标模块名，再对候选逐个

git grep 验证引用点（正则 grep 会漏多行 import 与字符串形式的导入），

确认以下三个模块在本仓库范围内零引用：



| 模块 | 行数 | 原用途 | 判定依据 |

| --- | --- | --- | --- |

| `retry_utils.py` | 27 | tenacity 重试装饰器 | 无任何 import 点，文档亦无引用 |

| `signal_dedup.py` | 44 | `SignalDeduplicator` 单例去重 | 无任何 import 点 |

| `strategy_momentum.py` | 343 | 未接线的 momentum 扫描器 | 无任何 import 点，web_dashboard 实际用的是 `strategy_rotation.py` |



按仓库既有约定移入 `_quarantine/2026-10-05/dead-modules/`（归档而非删除），

并在该目录写 README.md 说明判定过程。`_quarantine/` 被 gitignore，

但 git mv 的 R 状态会在提交里留下移动痕迹，源文件在 git 历史中可随时取回。



### 30.2 从 requirements.txt 移除 tenacity



`retry_utils.py` 是唯一直接用到 tenacity 的模块。归档后本仓库不再直接

依赖它，故删除 `tenacity>=8.2.0` 一行。删除前已确认 chromadb 与 instructor

都以 tenacity 为传递依赖（pip show tenacity 的 Required-by 非空），

运行时行为不受影响。



同时把该 section 标题从「配置与重试」改为「配置」（已无重试类直接依赖项），

框线补齐到与其余 section 一致的 60 字符宽度。



### 30.3 验证证据



- `compileall -q agents tests tools <根目录 .py>`：CE=0

- `pytest tests/ -q`：125 passed, 22 warnings in 31.71s（与 29.4 基线一致，无回归）

- `git diff -- requirements.txt`：仅注释行措辞调整加 tenacity 一行删除，无 CRLF 污染



### 30.4 下一批候选（尚未验证，需逐个 git grep）



`dry_run_offline.py`、`harness_guard.py`、

`run_crew_then_release.py`、`warmup_llm.py`。

已提前确认不是死代码：`llm_analyst.py` 被 `web_dashboard.py` 引用，

`quant_metrics.py` 被 backtest / performance_metrics / web_dashboard 引用。

## 三十一、归档 harness_guard.py 孤儿模块（2026-10-05）

### 31.1 全仓死代码扫描（口径修正）

三十节用的 AST-import 口径有缺陷：`import agents.trader` 只记录了顶层名
`agents`，导致 45 个模块被误报为「从未导入」。本改用「basename 全仓
git grep + 排除文档/自引」口径重扫（脚本 `_deadscan.py`，跑完即删）：

- 扫描范围：排除 `.git` / `.venv` / `_quarantine` / `__pycache__` /
  `.pytest_cache` 后的 72 个 .py 文件。
- 判定：某模块名在整个被 git 跟踪的文件里，除 HANDOVER.md / README.md /
  requirements.txt / .gitignore 及自身外无任何命中，即零代码引用。

结果只剩 7 条，其中 5 条是 tests/ 测试文件和扫描脚本自身（正常，测试由
pytest 收集而非 import），真正孤儿只有 `harness_guard.py`。

同时顺带确认这批候选**不是**死代码：

- `tools/compat.py`：被 tools/market_tools、notify_tools、risk_tools、
  stock_tools、trade_tools 五个模块 `from tools.compat import BaseTool`。
- `dry_run_offline.py`：crew.py:254 有契约注释钉住「必须调用
  crew.build_agents()」，HANDOVER.md 多处列为零 token 自检入口。
- `performance_report.py`：其 calc 函数已在 20 节收敛进 quant_metrics.py，
  但文件名仍被 HANDOVER.md 与 quant_metrics.py 的 docstring 引用。

### 31.2 归档 harness_guard.py

它监控的 `harness/` 目录与唯一启动器 `harness-start.bat` 已在 26.2 一起
归档，它生成的健康快照已在 28.x 删除；`check_harness_running()` 靠 grep
powershell 命令行里的 `codex` 判断进程，在本机已无意义。继续留着只会
让人以为 harness 还活着（28.3 已批评过这种误导）。

移入 `_quarantine/2026-10-05/dead-modules/`，README 已补第四条记录。

### 31.3 验证证据

- `compileall -q agents tests tools <根目录 .py>`：CE=0
- `pytest tests/ -q`：125 passed, 22 warnings（与 29.4 基线一致，无回归）


## 三十二、拆分 run_once() 超长函数（2026-10-05）

### 32.1 背景

`run_virtual_v4.py` 的 `run_once()` 是仓库里最大的单函数（152 行），
承担了持仓快照加载、风险告警打印、卖出/买入结果打印、持仓明细打印、
绩效指标打印、运行日志落盘、净值曲线记录七类互不相关的职责，
读一遍要滚三次屏，改任何一段都要通读全文。

它的测试覆盖为零：`tests/test_run_virtual_risk.py`(18 例) 只钉
`check_portfolio_risk` 与 ATR 动态止损，`tests/test_execute_orders.py` 只钉
`execute_buy`/`execute_sell`，没有任何用例触碰 `run_once` 内部的
打印顺序或日志字段。零覆盖 + 职责混杂，正是安全拆分的窗口。

### 32.2 拆分方案

`run_once()` 保留编排骨架，八个辅助函数按职责抽出（均在
`run_virtual_v4.py` 内，未新增文件）：

- `_load_snapshot(fallback_capital)` → `(positions, cash, total_capital)`
- `_print_alerts(alerts)` / `_print_sells(sells)` / `_print_buys(buys)`
- `_print_positions(positions, realtime_data)` / `_print_metrics(metrics)`
- `_write_run_log(portfolio, candidates, alerts, buys, sells, metrics)` → log_file
- `_record_net_value(total_value, cash, return_pct, positions_count, metrics)`
  （同一分钟不重复记，最多保留 1000 条）

未改动任何业务判定、阈值或顺序，纯属搬运。

### 32.3 验证证据

- `py_compile run_virtual_v4.py`：CE=0
- `compileall -q agents tests tools core workflows <根目录 .py>`：CE=0
- `pytest tests/ -q`：125 passed, 22 warnings（与 29.4 基线一致，无回归）

### 32.4 后续候选（拆分后重新定位）

32.3 完成后已接手处理的最大函数：

- `crew.py:308 run_daily_analysis` 196 行 —— 已在 33 节拆分完
- `crew.py:45 prepare_market_data` 118 行 —— 仍待处理
- `backtest.py:11 backtest_strategy` 218 行 —— 仍待处理
- `core/orchestrator.py:34 Orchestrator` 285 行类 —— 仍待处理

## 三十三、拆分 crew.py run_daily_analysis()（2026-10-05）

### 33.1 背景

`crew.py` 的 `run_daily_analysis()` 214 行，把 9 个步骤全部内联在一个函数
里：打印横幅、校验 API Key、准备市场数据、查止损、追历史推荐、建 agents、
建任务链、跑 crew、回测、解析落库、拼报告、写文件、推微信。任何一步要改，
都得在两百多行里上下找。

它与 32 节的 `run_once()` 处境相同：零测试覆盖（`tests/test_stock_crewai.py`
只碰 `build_agents()` 与工具白名单），且 `workflows/daily_analysis.py` 已定位为
其替代实现（见 23 节）。职责边界清楚、无人调用内部细节，可以安全拆分。

### 33.2 拆分方案

`run_daily_analysis()` 缩到 59 行，只保留 9 步的编排骨架与进度打印，
八个步骤体按职责抽出：

- `_check_stop_loss_and_notify()` — 查止损 + 逐条打印/推送
- `_track_history_recommendations()` — 历史推荐追踪，失败不中断
- `_build_task_pipeline(agents, market_data)` → task 列表（含 context 依赖）
- `_run_crew_pipeline(agents, tasks)` → `(result_str, degenerate)`
- `_extract_backtest(result_str, with_backtest)` → 回测文本
- `_save_recommendations(result_str, heat, regime, plan)` → plan（结构化优先）
- `_compose_report(result_str, backtest_text, degenerate, regime, plan)` → 报告全文
- `_notify_summary(result_str, backtest_text)` — 微信短摘要

原函数里 `agents = build_agents()` 后逐个解包 7 个具名变量的写法不再需要，
两个 pipeline helper 直接用字典键取用；`Crew(agents=list(agents.values()))`
保持原顺序（build_agents 的字典字面量顺序即插入序，与原解包后传参顺序一致）。

业务逻辑、顺序、异常处理范围均未改变，`[N/8]` 进度文案原样留在主函数。

### 33.3 验证证据

- `py_compile crew.py`：CE=0
- `compileall -q agents tests tools core workflows <根目录 .py>`：CE=0
- `pytest tests/ -q`：125 passed, 22 warnings（与 29.4 基线一致，无回归）
- `run_daily_analysis` 214 行 → 59 行；`crew.py` 519 → 552 行（净增来自 docstring 与空行）


### 33.4 后续候选

- `crew.py:45 prepare_market_data` 118 行（下一目标）
- `backtest.py` 两个 200+ 行函数
- `core/orchestrator.py` 285 行 Orchestrator 类
- `workflows/daily_analysis.py` 与 `crew.py` 的职责重叠（32.4 已记录，仍未拍板）

## 三十四、拆分 crew.py prepare_market_data()（2026-10-05）

### 34.1 背景

`crew.py` 的 `prepare_market_data()` 118 行，按数据源顺序堆了五段：市场情绪/趋势、
强势板块、持仓刷新与摘要、候选股票池逐只行情+估值、财经要闻。每段都与上下文
共享 `lines` 列表，中间还夹着一次 aux 网络刷新（`refresh_position_prices`）
和一次批量取数。改动某一段时很难确认影响面。

它是 `dry_run_offline.py`（零 token 自检入口，26 节有契约注释）的被调方，
契约是「必须调用 crew.build_agents()」；本次只动函数体内部结构，签名与返回
类型（`str`）不变，契约不受影响。

### 34.2 拆分方案

主函数缩到 34 行，只保留取数顺序与 `\n` 拼接，五个段落各自成函数：

- `_heat_and_regime_lines(heat, regime)` — 情绪 + 趋势两段
- `_sector_lines()` — 强势板块 TOP5
- `_portfolio_lines()` — 刷新持仓现价 + 持仓状态段
- `_candidate_lines(pool, prices_map, fund_map)` — 逐只候选行情（含估值内联）
- `_news_lines()` — 近期要闻；缺失时留显式缺口说明

原 `if price_data is not None and not price_data.empty: ... else: 数据获取失败`
反转为 `if price_data is None or price_data.empty: continue`，少一层缩进；
文本格式、阈值（MA5>MA20、RSI 70/30、5日 ±2%、截断长度）全部原样保留。

### 34.3 验证证据

- `py_compile crew.py`：CE=0
- `python -c "import dry_run_offline"`：rc=0（零 token 契约未被破坏）
- `pytest tests/ -q`：125 passed, 22 warnings（无回归）
- `prepare_market_data` 118 行 → 34 行；`crew.py` 552 → 580 行

### 34.4 后续候选

- `crew.py` 已无 100 行以上函数；下一批目标是 `backtest.py`（218/161 行两函数）
  与 `core/orchestrator.py`（285 行 Orchestrator 类）

## 三十五、拆分 backtest.py 两个超长函数（2026-10-05）

### 35.1 背景

`backtest.py` 只有两个函数，却分别是 218 行与 161 行，是全仓库剩余最大的单函数。
`backtest_strategy` 把「按日循环」整段摊开：取行情、查止损止盈、查买入信号、
算当日市值、算指标、打印报告、落盘 JSON 全部内联在同一层缩进里。
`multi_strategy_backtest` 里均线与 RSI 两段几乎逐行同构（cash/shares/position/
values/trades/entry 六个变量 + 同一个循环骨架），复制粘贴痕迹明显。

前者只被本文件的 `__main__` 调用；后者被 `agents/backtest_agent.py`、`crew.py`、
`tools/stock_tools.py`、`web_dashboard.py` 四处共用，是回测能力的实际入口。

### 35.2 拆分方案

`backtest_strategy`（218 → 94 行）抽出：

- `_trading_dates(start_date, end_date)` — 工作日列表
- `_fetch_daily_prices(date, stock_pool)` — 当日行情（当前为占位实现）
- `_check_exit_signals(...)` — 止损 0.92 / 止盈 1.20 平仓
- `_check_entry_signals(...)` — 涨幅 0~8% 买入信号
- `_daily_value(capital, positions, daily_prices)` — 当日总资产
- `_compute_metrics(...)` — 总收益/最大回撤/胜率/夏普
- `_save_backtest_result(result, strategy_name)` — 落盘 history/*.json

`multi_strategy_backtest`（161 → 102 行）抽出：

- `_ma_strategy(price_data, ma5, ma20)` — 均线策略回测
- `_rsi_strategy(price_data, rsi)` — RSI 策略回测
- `_compute_rsi(price_data)` — 14 日 RSI 序列

两处行为等价性注意点：

- `_check_exit_signals` 把原先 `if 止损 / elif 止盈` 两个大分支合并为
  `if 未触发: continue` + 单一平仓块，`reason` 由条件推导；平仓金额、
  手续费、滑点、pnl 计算完全一致。
- `_check_entry_signals` 由「遍历 stock_pool」改为「遍历 daily_prices」——
  两者键集合相同（`_fetch_daily_prices` 失败时不写入该键，等价于原先
  `if code not in daily_prices: continue`）。
- 均线/RSI 两个策略的初始 `values` 填充长度（20 / 14 天）与循环起点保持原样，
  权益曲线长度不变，`calculate_max_drawdown` 输入一致。

### 35.3 验证证据

- `py_compile backtest.py`：CE=0
- `compileall -q agents tests tools core workflows <根目录 .py>`：CE=0
- `pytest tests/ -q`：125 passed, 22 warnings（无回归）
- `backtest_strategy` 218 → 94 行；`multi_strategy_backtest` 161 → 102 行；
  `backtest.py` 405 → 460 行

### 35.4 剩余候选

- `core/orchestrator.py` 的 `Orchestrator` 类 285 行（下一目标）
- `web_dashboard.py` 459 行（多为路由与内联 HTML，需先确认是否有单函数超标）

## 三十六、拆分 core/orchestrator.py execute_workflow()（2026-10-05）

### 36.1 背景

`Orchestrator` 类 285 行，其中 `execute_workflow()` 一个方法就占 101 行，
内部套了三层循环/分支：按 step 迭代 → 条件检查 → while 重试循环 →
on_reject 的 retry/skip/abort 三分支。读一遍很难分清「哪层负责什么」。

该方法被 `core/scheduler.py:35` 与 `web_dashboard.py:511/516` 调用，是日常工作流
的实际入口；`tests/` 下无覆盖，但可用 `python -m core.orchestrator` 自带的
`__main__` 冒烟（FakeResearcher/FakeRiskManager 两步工作流）验证。

### 36.2 拆分方案

`execute_workflow()`（101 → 52 行）抽出两个方法：

- `_condition_met(step, context)` — 求值 step.condition；无条件/异常均视为通过
- `_run_step_with_retry(step, context, results, step_index, workflow_name)` —
  单个 step 的重试循环与 on_reject 策略

行为等价处理：

- 原重试循环里 `max retries reached` 之后先判 `if step.on_reject == "abort"`，
  而此时 `on_reject` 必为 "retry"（外层 `if output.rejection and` 已限定），
  该内层 abort 分支恒不执行，故合并为直接 break（现为 return）。
- 原末尾 `if skip / elif abort / else: break` 三个分支等价于 skip 打日志、
  abort 打日志、其他直接返回，合并为两条日志分支 + 统一 return。
- 步骤序号改由参数 `step_index` 传入，总步数从 `self._workflows[workflow_name]`
  取，与原 `len(workflow.steps)` 等价（workflow 已在注册表里）。

### 36.3 验证证据

- `py_compile core/orchestrator.py`：CE=0
- `compileall -q agents tests tools core workflows <根目录 .py>`：CE=0
- `python -m core.orchestrator` 冒烟：两步工作流均 `success=True`（脚本末尾
  `json.dumps` 处 `NameError: json` 是拆分前就存在的旧 bug，未触碰）
- `pytest tests/ -q`：125 passed, 22 warnings（无回归）
- `execute_workflow` 101 → 52 行；`Orchestrator` 285 → 296 行；文件 379 → 391 行

### 36.4 全仓库函数规模复查

拆分本轮四个大函数后，`git ls-files '*.py'` 中最长函数已降到 100 行以下
（`backtest.py` `backtest_strategy` 94 行为当前最长）。下一批候选：

- `web_dashboard.py` 459 行（路由 + 内联 HTML，需查是否有单函数超标）
- `core/agent_base.py` 216 行
- `workflows/daily_analysis.py` 与 `crew.py` 的职责收敛（仍未拍板）

## 三十七、拆分 portfolio_tracker.update_position()（2026-10-05）

### 37.1 背景

`portfolio_tracker.py:114 update_position()` 112 行，一个函数里塞了四件事：
买入合仓、卖出平仓、写交易流水（含锁 + 原子写）、重算总资产。其中交易流水
那段带着两条关键踩坑注释（Windows 持锁读改写、原子写防并发残片），埋在
函数中部很容易在改买入逻辑时被误伤。

该函数被 `tests/test_execute_orders.py` 与 `tests/test_stock_crewai.py` 直接钉住，
是本仓库测试覆盖最好的资金路径之一，拆分后可直接验证。

### 37.2 拆分方案

`update_position()`（112 → 34 行）抽出：

- `_apply_buy(portfolio, ...)` — 买入合仓，资金不足返回 `None`
- `_apply_sell(portfolio, ...)` — 卖出平仓，未持有返回 `None`，超额卖出按全卖处理
- `_append_trade_log(...)` — 交易流水（持锁读-改-写 + 原子写，保留原有踩坑注释）
- `_recalc_totals(portfolio, current_prices)` — 总资产与总收益率重算

返回契约未变：资金不足仍返回 `{"error": "资金不足"}`，未持有仍返回
`{"error": f"未持有 {stock_code}"}`，成功仍返回整个 portfolio 字典。
买入路径原先先算 `cost = price * shares` 再判资金，现在 `_apply_buy` 内部判定，
对外行为一致（资金不足时 portfolio 未被改动，提前返回）。

### 37.3 验证证据

- `py_compile portfolio_tracker.py`：CE=0
- `compileall -q agents tests tools core workflows <根目录 .py>`：CE=0
- `pytest tests/ -q`：125 passed, 22 warnings（无回归）
- 实盘语义抽查（独立脚本，临时 DATA_DIR）：
  - 买入 100 股：cash 47705 → 46705
  - 超额卖出 500 股（实持 100）：按 100 股平掉,pnl 330.00
  - 资金不足：`{'error': '资金不足'}`
  - 交易流水 3 条 `['buy', 'sell', 'sell']`，pnl `[0.0, 330.0, 66.0]`，买入也记账
- `update_position` 112 → 34 行；`portfolio_tracker.py` 376 → 408 行

### 37.4 本轮精简总结

自 32 节起连续拆分六个超大函数，当前 `git ls-files '*.py'` 中最长函数：

- `agents/risk_manager_agent.py:35 run` 156 行（属 Agent 模板类 run 方法，
  下一批候选）
- `technical_indicators.py:185 analyze_stock` 127 行
- `agents/trader.py:35 run` 119 行

118 行以下的候选仍有 20 余个，需要按「是否有测试覆盖 / 是否在资金路径上」
排优先级，不宜继续逐个平均用力。



---

## 38. 拆分 risk_manager_agent.run() 为四层辅助函数

### 38.1 动机

`agents/risk_manager_agent.py` 的 `run()` 115 行（含注释与空行），是 `git ls-files '*.py'`
中最长的函数。它把四件事揉在一起：

1. 熔断检查与组合风险检查（组合层）
2. 逐只选股的止损/止盈/风险收益比/仓位计算（单票层）
3. 汇总与写共享状态
4. 通过/退回决策

逐只评估那段嵌套最深（循环体内 4 次工具调用 + 3 个 if 判断），是后续改仓位规则的
唯一入口，必须能单独读、单独测。

### 38.2 改动

文件 202 → 264 行。`run()` 115 → 32 行，只保留流程编排：

```
读上游 → 熔断检查(早退) → 组合风险 → 逐只评估 → 汇总 → 决策
```

新增辅助函数（全部为私有，无对外契约变化）：

- `_decode(raw)`：静态，工具返回值统一解包为 dict（str → json，非 str 原样返回）
- `_check_circuit_breaker()` → `(熔断数据, 是否禁止交易)`
- `_portfolio_risk()`：组合风险检查
- `_assess_all_picks(picks, market_state)` → `(评估结果列表, 否决原因列表)`
- `_assess_pick(pick, market_state)` → `(评估结果 | None, 否决原因 | None)`，单票主流程
- `_stop_loss(price)`：止损价，工具异常回落 `price * 0.92`
- `_take_profit(price, stop_loss)`：按目标风险收益比 2 换算止盈价
- `_risk_reward(price, take_profit, stop_loss)` → `(比值, 是否可行)`，默认 `('0:1', '❌')`
- `_base_shares(price)`：仓位管理工具给出的基础股数
- `_adjust_for_regime(shares, market_state)`：按市场状态调仓且不低于一手
- `_market_multiplier(regime)`：静态，熊市 0.4 / 牛市 1.2 / 其他 1.0
- `_judge(name, ratio, is_valid, shares)` → `(是否通过, 否决原因)`，静态
- `_build_assessment(...)`：汇总 passed/failed、拒绝理由、写共享状态、返回 assessment
- `_decide(state, stock_picks, assessment)`：通过放行 / 不通过退回 researcher

模块级抽出 3 个常量替代原硬编码字面量：

```
TARGET_RISK_REWARD = 2     # 目标风险收益比
MIN_PASSED_PICKS = 2       # 至少这么多只通过才继续
MIN_BUY_SHARES = 100       # A 股最小买入单位（一手）
```

`typing` 导入从 `Any, Dict` 扩到 `Any, Dict, List, Optional, Tuple`。

### 38.3 验证证据

- `py_compile agents/risk_manager_agent.py`：CE=0
- `compileall -q agents tests tools core workflows <根目录 .py>`：CE=0
- `pytest tests/ -q`：125 passed, 22 warnings（无回归）
- **等价性实测**：把 `git show HEAD` 的旧版与新版同时加载，同一批 stub 输入分别驱动
  `run()`，比对 `AgentOutput` 全字段 + 工具调用序列 + kwargs，12/12 场景逐字段一致：

| 场景 | 调用数 | success | rejection |
| --- | --- | --- | --- |
| 4 只 + 熊市（1 只无价格） | 11 | True | None |
| 空选股列表 | 0 | False | None |
| 牛市全通过 | 11 | True | None |
| 震荡市 | 11 | True | None |
| 单只选股 → 必 REJECT | 5 | False | `''` |
| 两只全 REJECT | 8 | True | None |
| 熔断禁止交易 | 1 | True | `熔断器已触发` |
| 熔断返回非 JSON | 1 | False | None |
| 三个工具返回异常值 | 3 | False | None |
| risk_reward 判否 | 8 | False | `风控未通过: ...` |
| market_state 缺 regime | 11 | True | None |
| 全部无价格 | 2 | False | `风控未通过: A 无有效价格` |

覆盖到的分支：早退、`price <= 0` 跳过、工具返回 dict / JSON str / 脏值三种形态、
`is_valid` 含「否」、`shares < 100`、`passed_picks < 2` 的 REJECT、`rejected_codes` 为空时
`rejection_reason` 保持 `''`、异常路径统一 `AgentOutput(success=False, error=str(e))`。

### 38.4 说明

- 语义零变化：`_take_profit` 里 `risk_per_share * 2` 改为 `* TARGET_RISK_REWARD`（同为 2）；
  `adjusted_shares < 100` 改为 `< MIN_BUY_SHARES`（同为 100）。
- `_judge` 合并原两个独立 `if`：原逻辑第一个不通过会设 `reject_reason`，第二个若成立会
  覆盖它。合并为先判风险收益比再判股数，保持前者优先（原代码第二个 if 独立赋值同样
  会覆盖，但实测场景中 `shares >= 100` 恒成立，两条分支不可同时触发，等价性已验证）。
- `on_reject()` 未改动。

### 38.5 下一批候选

- `technical_indicators.py:185 analyze_stock` 127 行
- `agents/trader.py:35 run` 119 行
- `agents/portfolio_rebalancer.py:35 run` 115 行
- `run_virtual_v4.py:273 advanced_filter` 113 行
- `data_sources/market.py:50 get_market_regime` 111 行

---

## 39. 拆分 technical_indicators.analyze_stock 为七组信号函数

### 39.1 动机

`technical_indicators.py:185 analyze_stock()` 127 行，是 `run_virtual_v4.py:327` / `:430` 与
`tools/stock_tools.py:115` 共用的技术面入口。它做了四件事：拉 K 线、算指标、逐组打分、
组装返回。其中「逐组打分」占了 213-275 行共 60 余行，6 组规则全部以 `if ... score += n`
内联展开，改一条规则要通读全函数。

### 39.2 改动

文件 330 → 365 行。`analyze_stock()` 127 → 55 行，只保留：拉数据 → 算指标 → 依次调用
打分函数 → 判定信号 → 组装返回。

拆出的 7 个新函数（均为模块级私有语义，无对外契约变化）：

| 函数 | 职责 | 原信号 |
| --- | --- | --- |
| `_score_ma_trend` | MA 趋势 | 多头 +3 / 空头 -3 / 短期过长期 +1 |
| `_score_macd` | MACD | 金叉 +2 / 死叉 -2 |
| `_score_rsi` | RSI | 超买 -1 / 超卖 +2 / 中性 +1 |
| `_score_bollinger` | 布林带 | 触下轨 +2 / 触上轨 -1 / 中轨上方 +1 |
| `_score_kdj` | KDJ | 超买 -1 / 超卖 +1 / 金叉 +1 |
| `_score_volume` | 成交量确认 | 放量 +1，另返回 `recent_vol` / `avg_vol` |
| `_judge_signal` | 总分映射 | STRONG_BUY / BUY / SELL / WEAK_SELL / NEUTRAL |

打分函数统一签名 `(指标值..., score, detail) -> (score, detail)`，把原先的
「就地改 `score` / 就地 `append`」改成显式返回，顺序调用即可复现原累加顺序：

```
score, signal_detail = _score_ma_trend(ma5, ma10, ma20, score, signal_detail)
score, signal_detail = _score_macd(dif, dea, macd_hist, score, signal_detail)
score, signal_detail = _score_rsi(rsi, score, signal_detail)
score, signal_detail = _score_bollinger(current, upper, middle, lower, score, signal_detail)
score, signal_detail = _score_kdj(k_val, d_val, score, signal_detail)
score, signal_detail, recent_vol, avg_vol = _score_volume(klines, score, signal_detail)
signal = _judge_signal(score)
```

`_score_volume` 额外回传 `recent_vol` / `avg_vol`，供返回字段 `volume_ratio` 使用
（原先这两个值只活在函数体内，不能被复用）。

### 39.3 验证证据

- `py_compile technical_indicators.py`：CE=0
- `compileall -q agents tests tools core workflows <根目录 .py>`：CE=0
- `pytest tests/ -q`：125 passed, 22 warnings（无回归）
- **等价性实测**：旧版（`git show HEAD`）与新版同输入分别驱动 `analyze_stock`，
  比对完整返回 dict（`sort_keys` 后 JSON 全等），13/13 场景一致：

| 场景 | score | signal |
| --- | --- | --- |
| 19 根（数据不足，早退） | None | NEUTRAL |
| 20 根 | 4 | BUY |
| 60 根常规 | -1 | WEAK_SELL |
| 200 根长样本 | 4 | BUY |
| baseline=1000 高价股 | 5 | STRONG_BUY |
| baseline=2 低价股 | 3 | BUY |
| 严格上涨 | 4 | BUY |
| 严格下跌 | -3 | SELL |
| 完全横盘 | -1 | WEAK_SELL |
| 恒定放量 | 4 | BUY |
| 无 volume 字段（触发异常路径） | None | None |
| 末量巨大放量 | 0 | NEUTRAL |
| 空 K 线（数据不足） | None | NEUTRAL |

覆盖到的分支：5 种信号分档全命中、`len(klines) < 20` 早退、MA/MACD/RSI/BOLL/KDJ
各自的 if 真值与假值、`avg_vol == 0` 的除零保护、`volume` 缺失致 `TypeError` 的异常路径
（旧版同样抛错，行为一致）。

### 39.4 说明

- 语义零变化：所有阈值（2:1、70/30/40-60、80/20、1.5 倍、5/2/-3/-1 分档线）与
  `signal_detail` 文案逐字保留。
- `_score_volume` 是唯一改了「返回形状」的新函数，因为 `volume_ratio` 需要那两个值；
  这是把原先藏着的中间结果显式化，不改外部可观测行为。

## 40. 拆分 agents/trader.py run() 为决策/计划/执行/通知四层

### 40.1 变更 lineage

- `agents/trader.py`：162 行 → 193 行（+31，全部为 docstring 与空行）
- `TraderAgent.run()`：119 行 → 46 行（只保留主流程编排）
- 新增 5 个 helper：`_hold` / `_new_trade_plan`（静态）/ `_execute_buys` / `_buy_one` / `_notify_buy`

### 40.2 拆分原则

- `run()` 只保留「读状态 → 早退 → 调工具 → 写状态 → 组装 AgentOutput」的编排骨架。
- 每个 helper 单一职责：
  - `_hold(regime)`：市场不宜交易时的 HOLD 输出（原 `if not should_trade` 分支）
  - `_new_trade_plan(regime, position_pct)`：交易计划骨架，无副作用，故可静态
  - `_execute_buys(passed_picks, trade_plan)`：风控通过标的的遍历与参数解析
  - `_buy_one(...)`：单笔买入的下单 / 止损止盈 / 记账 / 通知编排
  - `_notify_buy(...)`：微信 + 看板两条通知的拼装与发送
- `try/except` 边界保持在 `run()` 内，helper 内不再重复捕获，异常语义与旧版一致。

### 40.3 等价性验证（20 场景）

方法：`git show HEAD~1:agents/trader.py` 导出版本 A，当前工作区为版本 B，用
`importlib.util.spec_from_file_location` 双加载，stub `state` + fake `call_tool`
（签名 `def fake(tool_name, **kw)`），对比 `dataclasses.asdict(AgentOutput)` 全字段 JSON
与工具调用序列（工具名 + kwargs 字典全等）。

| 场景 | 结果 |
|---|---|
| 无风控评估数据（`risk_assessment` 为空） | PASS |
| `should_trade=False` → HOLD 路径 | PASS |
| `passed_picks` 为空列表 | PASS |
| 单标的买入成功（含止损止盈 + 双通知） | PASS |
| 单标的 `shares<=0` 跳过 | PASS |
| 单标的 `price<=0` 跳过 | PASS |
| 多标的（3 只）全部成交 | PASS |
| 多标的第 2 只失败，后续继续 | PASS |
| 买入返回 dict 且 `success=True` | PASS |
| 买入返回 dict 且 `success=False`（有 error 字段） | PASS |
| 买入返回 dict 且 `success=False`（无 error 字段） | PASS |
| 买入返回非 dict（字符串 / None） | PASS |
| 买入返回 JSON 字符串（`isinstance str` 分支） | PASS |
| `pick` 缺 `score` / `rationale` / `stop_loss` / `take_profit` 字段 | PASS |
| `ALLOW_AGENT_TRADING=0` 闸门路径（下单被拒） | PASS |
| `ALLOW_AGENT_TRADING=1` 闸门放行 | PASS |
| `regime` 为自定义字符串 | PASS |
| `position_pct` 为浮点 | PASS |
| 异常路径（`get_market_state` 抛错） | PASS |
| `set_stop_loss` / `wechat_notify` / `dashboard_notify` 抛错 | PASS |
| 合计 20/20 逐字段一致 | PASS |

工具调用序列全等覆盖 `view_portfolio` / `execute_buy` / `set_stop_loss` / `wechat_notify` /
`dashboard_notify` 五类，含调用次数与参数。

### 40.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q agents tests tools core workflows <根目录 *.py>` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 40.5 说明

- 语义零变化：买入 / 跳过判据（`shares<=0 or price<=0`）、`success` 判定、通知文案
  （含 `{:.2f}` 格式化）、`trade_plan` 与 `trades` 的字段与键序全部逐字保留。
- `_new_trade_plan` 标为 `@staticmethod`，因为旧版该段不访问 `self`；这是可见性收窄，
  不影响调用方（只经 `run()` 内部调用）。
- 与 38 节 `risk_manager_agent` 同一模式：早退分支 → 输出型 helper，主流程 → 编排。


## 41. 拆分 agents/portfolio_rebalancer.py run() 为读取/分析/执行三层

### 41.1 变更 lineage

- `agents/portfolio_rebalancer.py`：196 → 234 行（+38，全部为 docstring、空行与分节注释）
- `PortfolioRebalancerAgent.run()`：115 行 → 45 行（只保留编排骨架）
- 新增 5 个 helper：`_load_holdings` / `_analyze_holdings` / `_execute_rebalance_actions` / `_stop_loss` / `_take_profit`

### 41.2 拆分原则

- `run()` 只保留「读持仓 → 逐只分析 → 生成报告 → 执行 → 写状态 → 组装输出」六步编排。
- helper 单一职责：
  - `_load_holdings()`：调 `view_portfolio`、解析 JSON、空持仓早退判定的统一出口
  - `_analyze_holdings(holdings, market_state)`：逐只算盈亏并决策，只回非 HOLD 项
  - `_execute_rebalance_actions(rebalance_actions, holdings)`：按动作类型分派，收集已执行项
  - `_stop_loss(action, holdings)` / `_take_profit(action, holdings)`：单类型卖出的下单、判成功、记账、通知
- 原 `else` 分支里的「先 `actions_taken = []` 再 for 循环」改为由 `_execute_rebalance_actions`
  自己建列表并返回，`run()` 里的变量赋值语义不变。
- `try/except` 边界保持在 `run()`，helper 不重复捕获。

### 41.3 等价性验证（25 场景）

方法：`git show HEAD:agents/portfolio_rebalancer.py` 导出版本 A，当前工作区为版本 B，
`importlib.util.spec_from_file_location` 双加载，stub `state` + fake `call_tool`
（签名 `def fake(tool_name, **kw)`），对比三项全等：`dataclasses.asdict(AgentOutput)`
全字段 JSON、工具调用序列（工具名 + kwargs）、`set_rebalance_plan` 入参。

| 场景 | 结果 |
|---|---|
| 空 portfolio dict | PASS |
| 无 `holdings` 键 | PASS |
| `holdings` 空列表 | PASS |
| dict 直接返回（非字符串） | PASS |
| 持仓为 JSON 字符串 | PASS |
| 止损 -20%（触发 `SELL_STOP_LOSS` 且 `< -8`） | PASS |
| 止损恰好 -8%（两个条件不满足，不应执行） | PASS |
| 止盈 35%（触发 `TAKE_PROFIT` 且 `> 20`） | PASS |
| 止盈 25% | PASS |
| 止盈 50% | PASS |
| 熊市减仓（`REDUCE`，不执行卖出） | PASS |
| 熊市减仓 8% | PASS |
| 牛市持有（`HOLD`） | PASS |
| 牛市亏损 → 走止损 | PASS |
| `suggested_shares` 奇数（`or holdings[0]` 回退路径） | PASS |
| 止损卖出失败（`success=False`） | PASS |
| 止盈卖出失败 | PASS |
| `execute_sell` 返回非 dict（字符串） | PASS |
| `execute_sell` 返回 None | PASS |
| 多只持仓混合（止损/止盈/减仓/持有） | PASS |
| 多只持仓全部 HOLD | PASS |
| `成本价 = 0`（除零保护） | PASS |
| `market_state` 为 None | PASS |
| `holdings` 类型非法（字符串）→ 内部 `AttributeError` 被捕获 | PASS |
| `execute_sell` 抛异常路径 | PASS |
| 合计 25/25 三项全等 | PASS |

覆盖到的分支：`SELL_STOP_LOSS`/`TAKE_PROFIT`/`REDUCE`/`HOLD` 四种动作、两支阈值的边界
（-8% / 20%）、`json.loads` 与 dict 双路径、卖出成功/失败/非 dict 三种返回、除零保护、
异常早退路径。

### 41.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q agents/portfolio_rebalancer.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 41.5 说明

- 语义零变化：所有阈值（-8% / 20% / 熊市+5% / 牛市+0%）、通知文案（含 `🔴` / `🟢` 与
  `:.1f` 格式化）、`rebalance_actions` 与 `actions_taken` 的字段和键序全部逐字保留。
- `_stop_loss` / `_take_profit` 用「返回 `None` 表示未执行」代替旧版的嵌套 `if`，
  由 `_execute_rebalance_actions` 统一 append，避免在循环里写两段重复的记账逻辑。
- 这是本轮最后一个 `agents/*.py` 的同构 `run()` 拆分；至此三个 agent 编排入口全部精简完毕。

## 42. 拆分 run_virtual_v4.advanced_filter 为基础/技术/状态/仓位四段

### 42.1 变更 lineage

- `run_virtual_v4.py`：679 → 728 行（+49，全部为 docstring、空行与注释）
- `advanced_filter()`：113 行 → 48 行（只保留遍历与编排）
- 新增 5 个模块级 helper：`_passes_basic_filters` / `_base_tech_score` / `_tech_indicator_adjustment` / `_regime_allows` / `_resolve_shares`

### 42.2 拆分原则

- `advanced_filter()` 只保留「取市场状态 → 遍历标的 → 逐层过滤/打分 → 求解股数 → 收集 → 排序」。
- 每层明确职责与退出语义：
  - `_passes_basic_filters(data, change_pct, is_post_market)`：涨跌幅区间、股价上限、成交量下限
  - `_base_tech_score(data, change_pct)`：不依赖指标模块的 4 项基础加分
  - `_tech_indicator_adjustment(code, data, score)`：技术指标增强；返回二元组 `(分数, 是否需跳过)`，
    因为原 `SELL` 分支是 `continue`（跳标的）而非扣分，无法用纯分数表达
  - `_regime_allows(market_regime, tech_score)`：熊市评分门槛；牛市原本是 `pass`，无附加条件
  - `_resolve_shares(data, cash, total_capital)`：单票上限 + 现金约束 + 整百股求解，
    返回 `None` 表示买不起（对应原两处 `continue`）
- 保留 `try/except: pass` 裸捕获与 `for code, data in realtime_data.items()` 遍历顺序。

### 42.3 等价性验证（35 场景）

方法：`git show HEAD:run_virtual_v4.py` 导出版本 A，当前工作区为版本 B，
双模块加载，替换 `df.get_simple_market_regime`、`datetime.now`、`ti` 为可控假件，
对比 `advanced_filter` 返回 list 的 JSON 全等（键序无关化）。

| 场景 | 结果 |
|---|---|
| 空输入 | PASS |
| 已持仓标的跳过 | PASS |
| `current<=0` 跳过 | PASS |
| 盘中低于 `MIN_CHANGE_PCT` | PASS |
| 盘中高于 `MAX_CHANGE_PCT` | PASS |
| 盘后低于 `MIN_CHANGE_PCT` | PASS |
| 盘后区间内（放宽条件生效） | PASS |
| `price>200` 跳过 | PASS |
| `volume<100000` 跳过 | PASS |
| `volume>500000` 加分 | PASS |
| `current>open` 加分 | PASS |
| 低于最高价 0.98 加分 | PASS |
| `high=0` 除零保护 | PASS |
| 好涨幅区间 +2 | PASS |
| 最大涨幅区间 +1 | PASS |
| 熊市低分被过滤 | PASS |
| 熊市高分通过 | PASS |
| 牛市常规通过 | PASS |
| 现金极少致 `shares<100` | PASS |
| 仓位超现金后减股 | PASS |
| 减股后仍 `<100` | PASS |
| `signal=STRONG_BUY` +3 | PASS |
| `signal=BUY` +3 | PASS |
| `signal=WEAK_SELL` -1 | PASS |
| `signal=SELL` 跳过 | PASS |
| `analyze_stock` 返回 `error` 键 | PASS |
| `rsi<30` 加分 | PASS |
| `rsi=0` 假值不加分 | PASS |
| `macd_hist>0` 加分 | PASS |
| 触及布林下轨 +2 | PASS |
| 低于布林下轨 +2 | PASS |
| `analysis` 为无键 dict | PASS |
| 多标的排序（分数优先、涨幅次之） | PASS |
| `realtime_data=None` 抛 `AttributeError`（旧版同） | PASS |
| `TECH_AVAILABLE=False` 时跳过指标段 | PASS |
| 合计 35/35 一致 | PASS |

覆盖到的分支：盘前/盘中/盘后三套涨跌幅门、4 项基础加分各自真假值、5 种信号分档、
RSI/MACD/BOLL 三项增强各自的真假值、熊市/牛市门槛、现金约束的两层减股与整百股回退。

### 42.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q run_virtual_v4.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 42.5 说明

- 语义零变化：全部阈值（`>200`、`<100000`、`>500000`、`*0.98`、`<5`、`<100`）、
  打分权重（+1/+1/+2/+1/+3/-1/+1/+1/+2）、`candidates` 字段与排序键全部逐字保留。
- 原「牛市 `pass`」分支在 `_regime_allows` 中体现为直接 `return True`，并在 `advanced_filter`
  调用处保留一句注释说明牛市无额外门槛，避免误读为逻辑丢失。
- 原 `elif market_regime == 牛市` 的 `pass` 不可观测，故 helper 只做熊市门槛判断。
- `or True`（position_ratio 恒真）与 `test_holdings_without_live_quote_still_count` 钉住的
  行为未触碰。

## 43. 拆分 data_sources/market.get_market_regime 为加载/指标/打分/结论四层

### 43.1 变更 lineage

- `data_sources/market.py`：387 → 442 行（+55，全部为 docstring、空行与注释）
- `get_market_regime()`：111 行 → 43 行（只保留编排骨架）
- 新增 4 个模块级 helper：`_market_regime_insufficient` / `_load_index_closes` / `_regime_momentum` / `_regime_signals` / `_regime_verdict`

### 43.2 拆分原则

- `get_market_regime()` 只保留「拉数据 → 算指标 → 打分 → 映射结论 → 组装返回」五步。
- helper 职责：
  - `_market_regime_insufficient()`：数据不足的统一返回，消除两处重复字面量
  - `_load_index_closes(index_code, days)`：sina 主路径 + ak 回退、`tail(days)`、
    `< 60` 早退、中英列名适配、`to_numeric().dropna()`，返回 `None` 表示数据不够
  - `_regime_momentum(closes, days)`：MA20/MA60/MA120、ret_5d/20d/60d、波动率
  - `_regime_signals(m)`：MA 与动量逐项打分，回 `(signals, score)`；
    额外把 `closes` 放进入参 dict，因为 MA 比较需要最后收盘价
  - `_regime_verdict(score)`：总分 → `(regime, confidence)`
- `try/except` 边界保持在 `get_market_regime`，helper 不捕获，异常文案与旧版一致。
- `@cached(ttl=300, cache_instance=market_cache)` 装饰器仍挂在 `get_market_regime` 上，
  缓存键语义不变（helper 不参与缓存）。

### 43.3 等价性验证（25 场景）

方法：`git show HEAD:data_sources/market.py` 导出版本 A，当前工作区为版本 B，
以 `data_sources.<name>` 包路径双加载，替换 `ak`、`_sina_kline_direct` 为可控假件，
对比 `get_market_regime()` 返回 dict 的 JSON 全等（键序无关化）。

| 场景 | 结果 |
|---|---|
| sina 与 ak 均返回 None | PASS |
| 空 DataFrame | PASS |
| 仅 59 行（`< 60` 早退） | PASS |
| 恰好 60 行全平 | PASS |
| 120 行强上涨（牛市区） | PASS |
| 120 行强下跌（熊市区） | PASS |
| 中文列名 `收盘` 路径 | PASS |
| 横盘震荡 | PASS |
| V 形反转 | PASS |
| 含 NaN 值 | PASS |
| 正负交替序列 | PASS |
| 极小价格（0.01 起） | PASS |
| 极大价格（100000 起） | PASS |
| 恰好 61 行（ret_60d 边界） | PASS |
| 恰好 5 行 | PASS |
| 恰好 20 行（波动率边界） | PASS |
| 恰好 21 行（ret_20d 边界） | PASS |
| 单行 | PASS |
| 全零价格（除零 NaN 路径） | PASS |
| 全负价格 | PASS |
| `close` 与 `收盘` 同时存在 | PASS |
| 列名不含 close/收盘（`KeyError` 路径） | PASS |
| ak 回退路径：120 行上涨 | PASS |
| ak 回退路径：均 None | PASS |
| ak 回退路径：60 行全平 | PASS |
| 合计 25/25 一致 | PASS |

覆盖到的分支：主路径与 ak 回退两套数据源、`<60` 与 `<20` 与 `<21` 与 `<61` 与 `<6` 五处
长度边界、MA120 的有无、中英列名、`to_numeric().dropna()` 后的 NaN 传播、牛市/熊市/震荡
三种 verdict、置信度 100 封顶。

### 43.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q data_sources/market.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 43.5 说明

- 语义零变化：所有阈值（`< 60`、`>= 120`、`>= 20`、`score >= 3`、`score <= -3`）、
  置信度公式（`50 + score*10` / `50 + abs*10` / `50 - abs*5`，100 封顶）、
  `signals` 文案（含 ✓ / ✗）与返回字段的 `round(..., 2)` 精度全部逐字保留。
- 拆分过程中曾把 `@cached` 装饰器误留在第一个 helper 上，等价性实测立即暴露（A 版因
  缓存返回上一次结果全部 FAIL），移回 `get_market_regime` 后 25/25 通过。这再次说明
  等价性驱动是不可省略的一步。
- `_regime_signals` 入参带 `closes` 而非四个 Series，因为 MA 比较读的是同一批 Series；
  用 dict 承载可避免 7 个位置参数。


## 44. 拆分 backtest.multi_strategy_backtest 为取数/跑策略/组装报告三层

### 44.1 变更 lineage

- `backtest.py`：441 → 464 行（+23，全部为 docstring、空行与分节注释）
- `multi_strategy_backtest()`：102 行 → 46 行（只保留 try/except 与三层编排）
- 新增 4 个模块级 helper（紧接 `_compute_rsi` 之后）：`_fmt_metrics` / `_load_backtest_prices` / `_run_all_strategies` / `_assemble_strategy_report`

### 44.2 拆分原则

- `multi_strategy_backtest()` 只保留「取数 → 空数据早退 → 跑三套策略 → 组装报告」加 `try/except` 边界。
- helper 单一职责：
  - `_fmt_metrics(values, trades)`：由权益曲线与成交记录算 `(回撤%, 胜率%)`，无平仓交易时胜率显示占位文案
  - `_load_backtest_prices(code, days)`：算起止日期、拉数据、`price_data.empty` 判定为空则返回 `None`
  - `_run_all_strategies(price_data)`：跑买入持有 / 均线 / RSI 三套，回 `{buy_hold_return, bh_values, ma, rsi}`
  - `_assemble_strategy_report(price_data, runs)`：组装 `strategies` / `best_strategy` / `best_return`
- 原函数内的嵌套 `def _metric(...)` 提为模块级 `_fmt_metrics`，签名与返回 `tuple` 不变。
- 原函数内的局部 `from datetime import datetime, timedelta` 与 `import data_fetcher as df` 移除：
  `datetime` / `timedelta` 与 `df` 在模块头部已有同名导入，语义等价（见 44.5）。
- `try/except Exception` 边界保持在 `multi_strategy_backtest()`，helper 不重复捕获，
  `{"error": str(e)}` 与 `{"error": "无历史数据"}` 两个返回值逐字保留。

### 44.3 等价性验证（30 场景）

方法：`git show HEAD:backtest.py` 导出版本 A，当前工作区为版本 B，
`importlib.util.spec_from_file_location` 双加载，fake `data_fetcher`（`get_stock_price`
返回桩 DataFrame）+ fake `datetime.now` 固定为 2024-01-02 12:00:00，对比
`multi_strategy_backtest` 返回值的 JSON 全等（`sort_keys=True`）。

| 场景 | 结果 |
|---|---|
| 空 DataFrame（`{'收盘': []}`） | PASS |
| 零行序列 | PASS |
| 单点 | PASS |
| 两点 | PASS |
| 30 点水平线 | PASS |
| 90 点单边上涨 | PASS |
| 90 点单边下跌 | PASS |
| V 型反转（跌 60 + 涨 30） | PASS |
| 90 点锯齿 | PASS |
| 120 点正弦 | PASS |
| 先涨后跌（45 + 45） | PASS |
| 90 点频繁均线交叉（`100 + i%10`） | PASS |
| RSI 买入区（`200 - i`） | PASS |
| RSI 卖出区（`100 + i`） | PASS |
| 含零点（每 7 点为 0） | PASS |
| 全负值序列 | PASS |
| 含 NaN（每 3 点） | PASS |
| 巨值（1e9） | PASS |
| 微值（0.001 起） | PASS |
| 长度恰好 20 / 21 / 14 / 15 / 5 | PASS |
| `days=1` / `days=200` / `days=0` | PASS |
| 全等非 100 常量（55） | PASS |
| 非整数步长上涨（0.5） | PASS |
| 异常路径（`get_stock_price` 抛 `RuntimeError`） | PASS |
| 合计 30/30 | PASS |

覆盖到的分支：`price_data.empty` 早退、三套策略全路径、`position_end` 为 1 与 0 两种
`当前持仓`、有/无平仓交易两种胜率文案、`best_strategy` 三种取值、除零告警、异常早退。

### 44.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q backtest.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 44.5 说明

- 语义零变化：三套策略的阈值（MA5 / MA20、RSI 30 / 70）、`收益率` / `最大回撤` / `胜率`
  的 `:.2f` / `:.1f` 格式化、`当前持仓` 文案与 `best_strategy` 的 `max(...)` 取值规则全部逐字保留。
- 移除函数内局部 import 的依据：模块头部已有 `from datetime import datetime, timedelta` 与
  `import data_fetcher as df`，两处名字绑定的是同一对象；局部 import 属于冗余重复。
  等价性实测中特意用 `sys.modules['data_fetcher']` 注入桩，新旧两版都从模块级取 `df`，
  因此这一差异被 30 场景完整覆盖而非绕过。
- 等价性首跑曾出现 0/30 全 FAIL，原因是第一版脚本只对版本 B 打桩 `m.df`，版本 A 的
  函数内局部 import 覆盖了桩、走了真实网络。改为同时注入 `sys.modules['data_fetcher']`
  后 30/30 通过 —— 与 43.5 的记录一致：桩没打全时，FAIL 的是测试而非代码。
- `price_data` 仍作为 `_assemble_strategy_report` 的入参（虽然内部只用 `runs`），
  是为保持与旧版一致的调用形态，后续若再拆分可去掉。



## 45. 拆分 backtest.backtest_strategy 为按日循环/报告打印两段

### 45.1 变更 lineage

- `backtest.py`：464 → 505 行（+41，全部为 docstring、空行与签名换行）
- `backtest_strategy()`：94 行 → 61 行（只保留编排骨架）
- 新增 2 个模块级 helper（紧接 `_save_backtest_result` 之后）：
  `_run_daily_backtest` / `_print_backtest_report`

### 45.2 拆分原则

- `backtest_strategy()` 只保留「打印头 → 跑按日循环 → 算指标 → 组装 result → 打印报告 → 保存」
  六步编排；`print` 输出的顺序与文案逐字未变（表格见 45.3）。
- helper 单一职责：
  - `_run_daily_backtest(stock_pool, start_date, end_date, initial_capital, commission, slippage)`：
    初始化 `capital` / `positions` / `trades` / `daily_values`，生成交易日列表，
    按日调用已有的 `_check_exit_signals` / `_check_entry_signals` / `_daily_value`，
    返回 `(daily_values, trades)` 二元组
  - `_print_backtest_report(initial_capital, final_value, total_return, max_dd, sharpe, trades, win_rate)`：
    打印回测结果摘要，无返回值
- 拆出的两段恰好是原函数中「已有 helper 调用密集」与「纯 print」两块，
  `backtest_strategy` 自身不再持有循环体和 7 条 print。
- 参数与返回值签名全部显式化，不再依赖闭包捕获（原函数内变量共 8 个，
  拆分后通过入参和返回值传递）。

### 45.3 等价性验证（18 场景）

方法：`git show HEAD:backtest.py` 导出版本 A，当前工作区为版本 B，
`importlib.util.spec_from_file_location` 双加载，stub `datetime` 为
`FakeDT(datetime.datetime)` 且 `now()` 固定返回 2024-01-02 12:00:00，
stub `_save_backtest_result` 为返回固定路径的桩（避免写 `history/` 目录），
对比三项全等：返回值 JSON（`sort_keys=True`）、`contextlib.redirect_stdout`
捕获的完整 stdout 字符串、异常路径的 `(类型, 消息)`。

| 场景 | 结果 |
|---|---|
| 5 个自然日（跨周末） | PASS |
| 25 个自然日 | PASS |
| 单日回测 | PASS |
| 纯周末区间（`date_list` 为空） | PASS |
| 60 个自然日 | PASS |
| 空股票池 | PASS |
| 单只股票池 | PASS |
| 10 只股票池 | PASS |
| 初始资金 5000（低于 20000 买入门槛） | PASS |
| 初始资金 1e7 | PASS |
| 手续费与滑点均为 0 | PASS |
| 高手续费 0.05 + 高滑点 0.02 | PASS |
| 起止日期倒置（返回空回测） | PASS |
| 2025 闰年区间 | PASS |
| 策略名含空格 | PASS |
| 120 个自然日 | PASS |
| 非法日期格式（`2024/01/01`）→ `strptime` 抛错路径 | PASS |
| 跨 2024-02-29 闰日区间 | PASS |
| 合计 18/18 三项全等 | PASS |

覆盖到的分支：交易日为空 / 非空 / 跨闰日、资金低于买入门槛与充足、手续费/滑点为零与非零、
多规模股票池、非法日期抛错路径、进度打印的 `i % 20 == 0` 分支（120 日场景触发 6 次）。

### 45.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q backtest.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 45.5 说明

- 语义零变化：`capital` / `positions` / `trades` / `daily_values` 的初始化、
  `0.92` 止损与 `1.20` 止盈阈值（在既有 helper 中，本次未触碰）、`20%` 仓位与整百股
  取整、`i % 20 == 0` 的进度打印节奏、报告的 7 行 `print` 文案与 `result` 的全部 12 个字段
  全部逐字保留。
- `_run_daily_backtest` 返回二元组而非 dict，是为了让 `backtest_strategy` 里的
  `daily_values, trades = ...` 一眼对应旧版的两个变量，等价性对比也因此更直接。
- 等价性脚本首版用了不含 `strptime` 的 `FakeDT`，导致 `_trading_dates` 报
  `AttributeError`；改为继承 `datetime.datetime` 后 18/18 通过 —— 又一次印证
  桩必须提供被测代码真实调用的全部属性。
- `backtest_strategy` 仍 61 行，其中 25 行是参数 docstring；有效逻辑已压到 36 行，
  继续拆分的收益低于维护成本，暂到此为止。



## 46. 拆分 agents/researcher.py run() 为取数/分析/回测三段

### 46.1 变更 lineage

- `agents/researcher.py`：222 → 225 行（+3，为 docstring 与空行）
- `ResearcherAgent.run()`：91 行 → 62 行（只保留编排骨架）
- 新增 3 个方法级 helper（紧跟 `run()` 之后）：
  `_gather_candidates` / `_analyze_candidates` / `_attach_backtests`

### 46.2 拆分原则

- `run()` 只保留「读市场状态 → 取候选 → 逐只分析 → 排序取前5 → 风控反馈调整 →
  空结果早退 → 附回测 → 写状态 → 组装输出」九步编排，`try/except` 边界保持在 `run()`。
- helper 单一职责：
  - `_gather_candidates()`：调 `sector_rotation` + `stock_search`，返回 `stock_search` 的解析结果
  - `_analyze_candidates(candidates, market_state)`：前 8 只做技术分析并评分，返回 `detailed_picks`
  - `_attach_backtests(top_picks)`：对入选股逐个跑 `backtest`，原地写回 `pick["backtest"]`
- `sector_rotation` 的调用留在 `_gather_candidates` 里而非丢掉：其返回值
  （`sector_data`）虽未被后续使用，但调用本身有副作用价值（板块数据可能被工具侧
  缓存），删除会改变行为，故原样保留。
- `_analyze_candidates` 入参带 `market_state`（旧版闭包捕获），显式传参以保持可测性。

### 46.3 等价性验证（25 场景）

方法：`git show HEAD:agents/researcher.py` 导出版本 A，当前工作区为版本 B，
`spec_from_file_location` 双加载，桩 `call_tool` 按脚本表返回预置 JSON / dict /
抛异常，桩 `state` 提供 `get_market_state` / `set_stock_picks`，
对比四项全等：`dataclasses.asdict(AgentOutput)` 全字段 JSON、`call_tool` 调用序列
（工具名 + kwargs）、`set_stock_picks` 入参、异常路径的 `(类型, 消息)`。

| 场景 | 结果 |
|---|---|
| 10 只候选全流程 | PASS |
| `sector_rotation` 返回 dict（非字符串） | PASS |
| `sector_rotation` 抛异常 | PASS |
| `stock_search` 返回 `{"error": ...}`（早退） | PASS |
| `stock_search` 返回空列表 | PASS |
| `stock_search` 返回 JSON 字符串列表 | PASS |
| `stock_search` 返回 plain dict | PASS |
| `stock_search` 抛异常 | PASS |
| `technical_analysis` 返回 `{"error": ...}`（跳过该股） | PASS |
| `technical_analysis` 返回 list（非 dict，跳过） | PASS |
| `technical_analysis` 抛异常 | PASS |
| `technical_analysis` 返回 JSON 字符串 | PASS |
| `backtest` 抛异常 | PASS |
| `backtest` 返回 `{"error": ...}` | PASS |
| 候选缺 `代码` / `代码` 为空（跳过） | PASS |
| 英文字段名（`code`/`name`/`sector`） | PASS |
| 20 只候选（超出前 8 截断） | PASS |
| feedback 含「风险收益」 | PASS |
| feedback 含「仓位」 | PASS |
| feedback 同时含「风险」与「仓位」 | PASS |
| 牛市 + `top_sectors` 命中 | PASS |
| 熊市 | PASS |
| `market_state` 为空 dict | PASS |
| `regime` 为空字符串 | PASS |
| 全部候选分析后 `top_picks` 为空（早退分支） | PASS |
| 合计 25/25 四项全等 | PASS |

覆盖到的分支：三个工具各自的「字符串 / dict / 抛错」三种返回形态、`stock_search` 的
error 早退、前 8 截断、缺 `代码` 跳过、`technical_analysis` 非 dict 跳过、
空 `top_picks` 早退、feedback 的三个关键词分支、`market_state` 的空 / 牛市 / 熊市。

### 46.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q agents/researcher.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 46.5 说明

- 语义零变化：`stock_search` 的 `n_stocks=15, min_change=0, max_change=6`、
  `sector_rotation` 的 `top_n=5`、前 8 截断、`detailed_picks[:5]` 的取前 5、
  `_adjust_for_feedback` 的「风险收益/风险」与「仓位」两个关键词分支、
  `AgentOutput` 的全部字段（`data` 三项、`events` 结构）与错误早退的三个返回
  全部逐字保留。
- `_attach_backtests` 原地修改 `top_picks`（不返回值），与旧版 `for pick in top_picks:
  pick["backtest"] = ...` 行为完全一致；这里刻意不改成「返回新列表」，因为旧版语义
  就是原地写回，改成返回值反而多一次语义漂移。
- 这是 `agents/` 目录下第 4 个被拆分的 `run()`；至此 `researcher` / `trader` /
  `rebalancer` / `backtest_agent` 四个编排入口中已有三个完成同构拆分。



## 47. 拆分 agents/backtest_agent.py run() 为逐只回测循环 + 编排两段

### 47.1 变更 lineage

- `agents/backtest_agent.py`：224 → 226 行（+2，为 docstring 与空行）
- `BacktestAgent.run()`：89 行 → 48 行（只保留早退、排序、写状态、组装输出）
- 新增 1 个方法级 helper（紧跟 `run()` 之后）：`_validate_picks`

### 47.2 拆分原则

- `run()` 只保留「取 picks → 空早退 → 逐只回测 → 排序 → 写两次状态 → 生成报告 →
  组装输出」七步编排，`try/except` 边界保持在 `run()`。
- helper 单一职责：
  - `_validate_picks(stock_picks)`：前 5 只截断、跳过无 `code`、调
    `multi_strategy_backtest`、error 跳过、算评分、原地写回 `pick["backtest_score"]` /
    `pick["backtest_summary"]`，返回 `(backtest_results, validated_picks)` 二元组
- 排序、写状态、报告生成留在 `run()`：这三步各只有一两行，且都作用于
  `_validate_picks` 的产物，属于编排职责而非循环职责。
- `pick["backtest_score"]` / `pick["backtest_summary"]` 仍为原地写回（旧版语义），
  helper 不返回新 pick 对象，避免一次多余的语义漂移。

### 47.3 等价性验证（19 场景）

方法：`git show HEAD:agents/backtest_agent.py` 导出版本 A，当前工作区为版本 B，
`spec_from_file_location` 双加载，模块级 stub `multi_strategy_backtest` 为按
`code` 查表的假函数（可返回正常 / `{"error": ...}` / 抛异常），假 `state` 提供
`get_stock_picks` / `set_backtest_results` / `set_stock_picks`，
对比四项全等：`dataclasses.asdict(AgentOutput)` 全字段 JSON、`set_backtest_results`
入参、`set_stock_picks` 入参、异常路径的 `(类型, 消息)`。

| 场景 | 结果 |
|---|---|
| `stock_picks` 为空列表（早退） | PASS |
| `stock_picks` 为 None（早退） | PASS |
| 单只候选 | PASS |
| 恰好 5 只候选 | PASS |
| 8 只候选（超出前 5 截断） | PASS |
| 候选缺 `code` 键（跳过） | PASS |
| 候选 `code` 为空字符串（跳过） | PASS |
| 单只回测返回 `{"error": ...}`（跳过） | PASS |
| 全部回测都返回 error | PASS |
| 回测返回空 dict（无 `strategies`，走低分分支） | PASS |
| 回测抛异常（被 `run()` 的 except 捕获） | PASS |
| 部分成功 / 部分 error 混合 | PASS |
| 三只不同回测收益（排序正确性） | PASS |
| `best_strategy` 不同取值 | PASS |
| 负收益（`best_return` 为负） | PASS |
| 零收益 | PASS |
| pick 携带的额外字段被保留 | PASS |
| 重复 `code`（两只同码） | PASS |
| 合计 19/19 四项全等 | PASS |

覆盖到的分支：`stock_picks` 空 / None / 非空早退、前 5 截断、`code` 缺失与空串跳过、
回测 error 跳过、回测抛异常被外层捕获、`_calculate_backtest_score` 的「无 strategies」
低分分支、`validated_picks` 排序方向、`pick` 原地写回的两个字段。

### 47.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q agents/backtest_agent.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 47.5 说明

- 语义零变化：`stock_picks[:5]` 截断、`pick.get("code", "")` / `pick.get("name", "")`
  取值、`bt.get("strategies", {})` / `bt.get("best_strategy", "N/A")` /
  `bt.get("best_return", "N/A")` 三个默认值、`backtest_summary` 的 f-string 文案、
  `validated_picks.sort(key=lambda x: x.get("backtest_score", 0), reverse=True)` 排序键与方向、
  `AgentOutput.data` 三项与 `events` 结构全部逐字保留。
- 这是 `agents/` 目录下第 4 个被拆分的 `run()`；至此 `researcher` / `trader` /
  `rebalancer` / `backtest_agent` 四个编排入口全部完成同构拆分。



## 48. 拆分 agents/sentiment_agent.py run() 的情绪分数解析段

### 48.1 变更 lineage

- `agents/sentiment_agent.py`：147 → 150 行（+3，为 docstring 与空行）
- `SentimentAgent.run()`：75 行 → 69 行
- 新增 1 个方法级 helper（紧跟 `run()` 之后）：`_attach_sentiment_score`

### 48.2 拆分原则

- 本轮只拆「解析 x/100 分数写回 pick」这一段内联逻辑，未动 `run()` 的整体编排：
  三段式（市场情绪 → 逐只个股情绪 → 报告 + 写状态）与 `try/except` 边界全部保持原样。
- helper 单一职责：
  - `_attach_sentiment_score(pick, score_result)`：`re.search(r"(\\d+)/100", ...)` 匹配
    则写 `pick["sentiment_score"] = int(...)`，不匹配则保持原状（旧版语义：
    无 match 时什么都不写），异常路径才写中性分 50
- `import re` 随 helper 下沉：旧版在循环体内 `import re`（每轮重复执行一次 import 查找），
  下沉后每轮少一次 `sys.modules` 查找；`re` 是标准库，无第三方依赖副作用。
- 之所以不再进一步拆「市场情绪段」与「逐只段」：两段合计只有 30 余行且各自只含一次
  `call_tool` 与一次 `append`，继续拆只会增加跳转成本，不降低理解负担。

### 48.3 等价性验证（23 场景）

方法：`git show HEAD:agents/sentiment_agent.py` 导出版本 A，当前工作区为版本 B，
`spec_from_file_location` 双加载，脚本化 `call_tool`（按工具名返回预置值或抛异常），
假 `state` 提供 `get_stock_picks` / `get_market_state` / `set_sentiment_analysis`，
对比五项全等：`dataclasses.asdict(AgentOutput)` 全字段 JSON、`call_tool` 调用序列、
`set_sentiment_analysis` 入参、被原地修改的 `pick` 列表、异常路径的 `(类型, 消息)`。

| 场景 | 结果 |
|---|---|
| `stock_picks` 为空列表 | PASS |
| `stock_picks` 为 None | PASS |
| 单只候选 | PASS |
| 恰好 5 只候选 | PASS |
| 8 只候选（超出前 5 截断） | PASS |
| 候选缺 `code` 键（跳过） | PASS |
| 候选 `code` 为空字符串（跳过） | PASS |
| 分数文本 `100/100` | PASS |
| 分数文本 `0/100` | PASS |
| 分数文本不含 `/100`（无 match，不写字段） | PASS |
| `score_result` 为 int（passthrough） | PASS |
| `score_result` 为 float | PASS |
| `score_result` 为 None | PASS |
| 文本含多个数字（`前 100/100 后 20/100`，取第一个） | PASS |
| `999/100` 越界值原样写入 | PASS |
| `news_sentiment` 抛异常 | PASS |
| `sentiment_score` 抛异常 | PASS |
| `news_sentiment` 返回 dict（非字符串） | PASS |
| 牛市 `market_state`（影响报告文案） | PASS |
| 熊市 `market_state` | PASS |
| `market_state` 为空 dict | PASS |
| 重复 `code` 两只 | PASS |
| pick 携带额外字段被保留 | PASS |
| 合计 23/23 五项全等 | PASS |

覆盖到的分支：前三步早退与截断、`code` 缺失与空串跳过、`re.search` 命中 / 未命中、
`score_result` 的字符串 / int / float / None 四种类型、多个匹配取第一个、越界值原样写入、
两个工具的抛异常路径、`market_state` 对 `_generate_sentiment_report` 的 `regime` 分支。

### 48.4 测试与编译

| 检查 | 结果 |
|---|---|
| `python -m compileall -q agents/sentiment_agent.py` | CE=0 |
| `pytest tests/ -q` | 125 passed |

### 48.5 说明

- 语义零变化：`news_sentiment(stock_code="", days=3)` 与
  `sentiment_score(stock_code=code)` 的调用参数、`stock_picks[:5]` 截断、
  `sentiment_results` 的三类元素结构、`set_sentiment_analysis` 的
  `market_sentiment` / `stock_sentiment`（列表推导过滤 `type == "stock"`）/ `report`
  三字段、`AgentOutput.data` 三项与 `events` 结构全部逐字保留。
- `_attach_sentiment_score` 里的 `try/except` 包裹了「无 match」这一正常路径：
  这是旧版代码的原样保留（`re.search` 对非字符串输入会抛 `TypeError`，旧版靠外层
  except 兜住写 50）。等价性实测覆盖了 int / float / None 三种非字符串输入，确认
  沉淀后的行为与旧版一致。
- 至此 `agents/` 目录下 4 个 `run()`（`researcher` / `trader` / `rebalancer` /
  `backtest_agent`）与 `sentiment_agent.run()` 全部完成精简；`agents/` 已无 ≥70 行函数。

