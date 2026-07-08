#!/bin/bash
# Med-Rag 启动脚本 — 同时启动后端 + Nginx

set -e

# 启动后端 FastAPI（后台运行）
echo "Starting Med-Rag backend..."
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 &
BACKEND_PID=$!

# 等待后端启动
sleep 3

# 检查后端是否运行
if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "Backend is running (PID: $BACKEND_PID)"
else
    echo "Warning: Backend health check failed, but continuing..."
fi

# 启动 Nginx（前台运行）
echo "Starting Nginx..."
nginx -g 'daemon off;'
