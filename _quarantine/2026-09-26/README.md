# 隔离区 2026-09-26

这些不是"删掉的代码"，是从项目根目录**改名挪进来**的一次性实验产物，随时可原样取回：

```bash
cd D:/aishare/repo/stock-crewai-master
mv _quarantine/2026-09-26/<文件名> .
```

## 为什么这批东西可以离开根目录

全部服务于同一个已经翻篇的假设：**用本地 Ollama 跑 27B 量化 GGUF**。
现在流水线走 StepFun 云端，那批"关 thinking / 撑 num_ctx / 改 chat_template"的探针
既跑不动也不再需要。留在根目录只会让下一次接手的人以为它们还有用。

## 分组清单

| 组 | 文件 | 原本在证明什么 |
|---|---|---|
| chat_template 改造 | `Modelfile.qwen38.notink`、`Modelfile.qwen38.thinkoff`、`Modelfile.qwen38.ctx32k`、`Modelfile.qwen38q2`、`Modelfile.qwen38q2.local`、`find_tmpl.py`、`patch_tmpl.py`、`think_check.json` | 从 GGUF blob 里捞出模板、改写、再 `ollama create`。HANDOVER 第四节记录的"内容寻址 blob 重建"用的就是这几个 |
| 上下文长度 | `read_ctxlen.py`、`ctxlen_out.txt`、`ctxlen_result.txt`、`test_ctx.py`、`test_numctx.py`、`test_numctx2.py`、`test_big.py` | 证明 `num_ctx=8192` 会被 400 `exceed_context_size_error` 打死 → Cause A |
| thinking 开关 | `test_nothink.py`、`test_nothink2.py`、`test_reason.py`、`probe_think.py`、`probe_thinkswitch.py`、`smoke_ollama.py`、`ab_test.py` | 证明 `reasoning_effort` 没真进请求体（Cause B）以及 none/low 的耗时差 |
| 空响应复现 | `repro_final.py`、`probe_ctx.py`、`test_flaky.py` | 复现 `Invalid response from LLM call` |
| 运行日志 | `crew_run.{log,err}`、`crew_run2~5.{log,err}`、`smoke_ollama.log`、`smoke_preflight.out`、`smoke_test.log`、`ab_test.out`、`probe_think*.out`、`repro_final.out` | 过程日志。**`crew_run6.log/.err` 特意留在根目录**——第十节通篇按行号引用它 |

## 留在根目录的三个，是有原因的

- `verify_crewai_path.py` —— 走真实 CrewAI 调用链的 2 分钟自检，Cause B 的回归工具
- `probe_payload.py` —— 拦截框架实际发出的 HTTP body，同上
- `dry_run_offline.py` —— 零 LLM 调用的"数据层 → 任务装配 → prompt 体量"干跑（新增）
