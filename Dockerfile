FROM docker.m.daocloud.io/library/python:3.11-slim

LABEL maintainer="cpufreestyle"
LABEL description="Stock CrewAI - A股虚拟盘自动交易系统 (Dashboard minimal)"

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 仅安装 Dashboard 和 Agent 框架所需的最小依赖
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
    flask flask-cors flask-compress apscheduler \
    pandas python-dotenv requests pydantic

# 复制项目代码（含多 Agent 结构）
RUN mkdir -p /app/core /app/agents /app/tools /app/workflows /app/templates /app/static
COPY *.py .
COPY core/ core/
COPY agents/ agents/
COPY tools/ tools/
COPY workflows/ workflows/
COPY templates/ templates/
COPY static/ static/
COPY portfolio.json.example portfolio.json.example
COPY start.sh .
RUN chmod +x start.sh
COPY .env.example .env.example

# 创建数据目录
RUN mkdir -p /app/history /app/data /var/log

# 数据卷挂载点
VOLUME ["/app/history", "/app/data"]

# 默认命令
CMD ["python", "main.py", "--dashboard"]
