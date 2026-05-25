FROM python:3.11-slim

LABEL maintainer="cpufreestyle"
LABEL description="Stock CrewAI - A股虚拟盘自动交易系统"

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY *.py .
COPY portfolio.json.example portfolio.json.example

# 创建数据目录
RUN mkdir -p /app/history /app/data

# 数据卷挂载点
VOLUME ["/app/history", "/app/data"]

# 默认命令：单次运行
CMD ["python", "run_virtual_v4.py"]
