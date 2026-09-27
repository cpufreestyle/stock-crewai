# Docker 使用说明

## 快速开始

### 1. 准备配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入 API Key
# OPENAI_API_KEY=sk-xxx
# OPENAI_BASE_URL=https://xxx
# MODEL_NAME=deepseek/deepseek-chat-v3-0324
```

### 2. 初始化持仓数据

```bash
cp portfolio.json.example portfolio.json
```

### 3. 构建并启动

```bash
# 虚拟盘自动交易（循环模式，交易时段每10分钟执行）
docker compose up -d

# 查看日志
docker compose logs -f
```

### 4. 运行 CrewAI 多智能体分析（可选）

```bash
# 单次分析
docker compose run --rm stock-analyst

# 查看 AI 分析报告
cat result_latest.md
```

## 常用命令

```bash
# 停止
docker compose down

# 重启
docker compose restart

# 查看实时日志
docker compose logs -f stock-crewai

# 进入容器调试
docker compose exec stock-crewai bash

# 重建镜像（代码更新后）
docker compose build --no-cache
docker compose up -d
```

## 数据持久化

| 容器路径 | 宿主机路径 | 说明 |
|---------|-----------|------|
| `/app/portfolio.json` | `./portfolio.json` | 持仓数据 |
| `/app/history/` | `./history/` | 运行日志 |
| `/app/data/` | `./data/` | 其他数据 |

## 定时任务

### 方案 A: Docker 内部循环（推荐）

容器以 `--loop` 模式运行，自动在交易时段执行。

### 方案 B: 宿主机 Cron

```bash
# 编辑 crontab
crontab -e

# 交易日 09:35 自动运行 CrewAI 分析
35 9 * * 1-5 cd /path/to/stock-crewai && docker compose run --rm stock-analyst
```

## 注意事项

1. **API Key** 必须在 `.env` 中配置，否则 LLM 分析无法运行
2. **时区** 默认为 `Asia/Shanghai`，确保交易时段判断正确
3. **数据持久化** 挂载了 `portfolio.json` 和 `history/`，删除容器不丢失数据
4. **内存** 建议 Docker 分配至少 1GB 内存给容器
