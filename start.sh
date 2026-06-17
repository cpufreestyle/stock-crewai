#!/bin/bash
# stock-crewai startup script with headroom proxy compression
set -e

echo "[START] 安装 headroom 依赖..."
pip install --no-cache-dir "httpx[http2]" > /dev/null 2>&1 || true

echo "[START] 启动 headroom proxy..."
headroom proxy \
  --port 8787 \
  --host 0.0.0.0 \
  --intercept-tool-results \
  --mode token \
  --no-cache \
  --stateless \
  --anyllm-provider openai \
  --openai-api-url http://host.docker.internal:1234/v1 \
  --log-file /var/log/headroom.jsonl \
  &

HEADROOM_PID=$!
echo "[START] headroom proxy PID=$HEADROOM_PID"
sleep 4

# Health check using Python
if python -c "import requests; requests.get('http://localhost:8787/health', timeout=5)" 2>/dev/null; then
    echo "[START] headroom proxy 健康检查通过 ✅"
else
    echo "[WARN] headroom proxy 未响应，将以 passthrough 模式继续..."
fi

# docker-compose command 示例: ["python", "main.py", "--dashboard"]
# 或: ["python", "run_virtual_v4.py", "--loop"]
# 去掉开头的 "python"，将剩余参数作为完整命令执行
ARGS=()
SKIP_NEXT=0
for arg in "$@"; do
    if [ "$arg" = "python" ]; then
        continue
    fi
    ARGS+=("$arg")
done

SCRIPT="${ARGS[0]:-/app/run_virtual_v4.py}"
REST_ARGS=("${ARGS[@]:1}")

echo "[START] 启动: python $SCRIPT ${REST_ARGS[*]}..."
exec python "$SCRIPT" "${REST_ARGS[@]}"
