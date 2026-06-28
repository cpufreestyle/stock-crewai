FROM python:3.11-slim

LABEL maintainer="cpufreestyle"
LABEL description="Stock CrewAI - A股虚拟盘自动交易系统"

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 安装系统依赖（用于 akshare 的 py-mini-racer 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# 安装所有项目依赖（与 requirements.txt 保持一致）
# 使用清华/阿里云镜像加速 GitHub Actions 中的构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 额外安装 headroom-ai（token 压缩）
RUN pip install --no-cache-dir headroom-ai -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 复制项目代码（含多 Agent 结构）
RUN mkdir -p /app/core /app/agents /app/tools /app/workflows /app/templates /app/static /app/harness
COPY *.py .
COPY core/ core/
COPY agents/ agents/
COPY tools/ tools/
COPY workflows/ workflows/
COPY templates/ templates/
COPY static/ static/
COPY harness/ harness/
COPY portfolio.json.example portfolio.json.example
COPY start.sh .
RUN chmod +x start.sh
COPY .env.example .env.example

# 创建数据目录
RUN mkdir -p /app/history /app/data /app/backtest_results /var/log

# 数据卷挂载点
VOLUME ["/app/history", "/app/data"]

# 默认命令
CMD ["python", "main.py", "--dashboard"]
