# 钉到 bookworm，避免 python:3.11-slim 浮点标签漂移到 trixie 后 apt 源异常
FROM python:3.11-slim-bookworm

LABEL maintainer="cpufreestyle"
LABEL description="Stock CrewAI - A股虚拟盘自动交易系统"

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 说明：原 Dockerfile 在此安装 wget/curl/gnupg，但本项目为纯 Python 应用
# （akshare/py-mini-racer 均为 Python 包，运行时无需系统 wget/curl/gnupg），
# 该步骤在 trixie 源下会 502 失败，故移除；ca-certificates 已由 slim 基础镜像提供。

# 安装所有项目依赖（与 requirements.txt 保持一致）
# 使用清华/阿里云镜像加速 GitHub Actions 中的构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 复制项目代码（含多 Agent 结构）
RUN mkdir -p /app/core /app/agents /app/tools /app/workflows /app/templates /app/static /app/harness
COPY *.py ./
COPY core/ core/
COPY agents/ agents/
COPY tools/ tools/
COPY workflows/ workflows/
COPY templates/ templates/
COPY static/ static/
COPY harness/ harness/
COPY tests/ tests/
COPY pytest.ini .
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
