# LM Studio vs Ollama 本地推理后端对比

> 针对 stock-crewai 项目（Docker + CrewAI 多智能体炒股分析）的本地 LLM 后端选型测试。
> 测试时间：2026-09-06

## 测试环境
- 硬件：NVIDIA RTX 4060 Ti 16GB（同一张卡，避免跨机差异）
- 后端 A：Ollama（llama.cpp + CUDA）
- 后端 B：LM Studio（`lms` CLI 启动 server，`/v1` OpenAI 兼容接口）
- 两者底层均为 llama.cpp + CUDA，差异只在封装层与模型库。

## 测试方法
- 通过 OpenAI 兼容的 `/v1/chat/completions` 接口发送同口径中文金融分析 prompt。
- 固定 `max_tokens` 后取 `usage.completion_tokens` 与墙钟耗时，计算 tokens/s。
- Ollama：`num_predict=300`；LM Studio：`max_tokens=300`。

## 实测结果

| 后端 | 模型 | 规模 | 生成 tokens | 耗时 | 速度 | 对接项目状态 |
|------|------|------|------------|------|------|------------|
| Ollama | qwen2.5:14b-instruct | 14B 稠密 | 207 | 7.57s | **27.34 tps** | ✓ 已端到端跑通 CrewAI，产出 `result_latest.md` |
| LM Studio | gemma-4-e4b-it-mtp-assistant-ultralight | 4B | 59 | 0.40s | **156.95 tps** | ✓ API 正常，但模型不适配本项目 |

## 关键发现
1. **后端效率几乎相等**：157 vs 27 的差距纯粹来自模型规模（4B vs 14B，差约 5.8 倍，符合规模规律）。同一模型无论走 Ollama 还是 LM Studio，速度基本一致——瓶颈是模型大小，不是后端封装。
2. **LM Studio 本机无适配模型**：本地仅 1 个 4B 小模型（gemma）+ 1 个 embedding 模型，缺乏适合中文金融分析 + 工具调用的 14B 模型；Ollama 已备好 `qwen2.5:14b` 并全程验证可用。
3. **无法严格同模型对比**：Ollama 不支持 gemma4 架构导入（报 `invalid model name: "gemma4"`），故只能跨模型测，结论以「规模主导速度」为准。
4. **Ollama 的坑**：`qwen2.5:14b-instruct` 标签名在 Ollama 下会报 `does not support chat`（模板未启用 chat），需改用 `qwen2.5:14b`（已验证可正常 chat + 工具调用）。

## 对本项目的选型结论
- **保持 Ollama**：项目需要「中文金融分析 + CrewAI 工具调用 + Docker 容器化 + 开机自启」全链路自动化。Ollama 的 headless/CLI 模式天然契合，且已端到端验证产出。
- **LM Studio 更适合**：交互式手动试模型、GUI 调参、快速体验新模型——这些不是本项目的运行场景。
- **不值得切换**：若改 LM Studio 做后端，需把 `OPENAI_BASE_URL` 指向 `http://host.docker.internal:1234/v1` 并再下载 9GB `qwen2.5:14b`，收益为零（后端效率相同），且牺牲容器化自动化的便利性。

## 如需切换（备用方案）
`.env`：
```
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://host.docker.internal:1234/v1
OPENAI_MODEL=qwen2.5:14b
```
前提：LM Studio 中已加载 `qwen2.5:14b` 模型并开启 server 监听 1234 端口。

## 临时文件清理
本次对比产生的 `payload*.json` / `bench*.bat` / `Modelfile.gemma` / `lms_models.json` 等已删除。
