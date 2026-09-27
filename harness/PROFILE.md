# Stock-CrewAI Harness Profile

## 项目概述
- **项目**: Stock-CrewAI 量化交易系统
- **语言**: Python 3.11
- **框架**: CrewAI + LangChain + Flask
- **数据源**: A股（akshare）、美股（efinance）
- **交易API**: 策场（Coze Signal Arena）

## 核心文件
- `crew.py` - 主入口，8 Agent 工作流
- `agents/` - Agent 定义目录
- `core/` - 核心逻辑
- `tools/` - 工具函数
- `docker-compose.yml` - 容器编排

## 常用命令
```bash
# 启动交易系统
docker compose up -d

# 查看日志
docker compose logs -f stock-crewai

# 运行测试
pytest tests/

# 开发模式（不用 Docker）
python crew.py
```

## LLM 配置
- 当前 Provider: MIMO v2.5
- 备用: LM Studio (localhost:1234)

## 注意事项
- A股 T+1 规则
- 熊市严禁扛单，触发止损无条件离场
- 总仓位 ≤30%
