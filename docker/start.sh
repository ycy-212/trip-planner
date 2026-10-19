#!/bin/bash
# trip-planner 容器启动脚本：后端 uvicorn(8000) + 前端 nginx(7860)
set -e

cd /app/backend

# 启动后端（仅容器内可访问，由 nginx 统一对外）
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1 &
BACKEND_PID=$!

# 等待后端就绪（最长 90 秒，覆盖依赖初始化）
for i in $(seq 1 90); do
    if curl -sf http://127.0.0.1:8000/health > /dev/null; then
        echo "[start.sh] backend ready"
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "[start.sh] backend exited unexpectedly"
        exit 1
    fi
    sleep 1
done

# 收到终止信号时先停后端再退出（bash 充当 PID 1 转发信号）
trap 'kill -TERM "$BACKEND_PID" 2>/dev/null; exit 0' TERM INT

# 前台运行 nginx 对外服务
nginx -g 'daemon off;' &
NGINX_PID=$!

wait "$NGINX_PID"
echo "[start.sh] nginx exited, shutting down backend"
kill -TERM "$BACKEND_PID" 2>/dev/null
