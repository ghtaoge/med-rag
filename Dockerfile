FROM python:3.13-slim AS backend

WORKDIR /app

# 安装系统依赖（PaddleOCR 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# 复制应用代码
COPY app/ app/
COPY config.yaml .
COPY data/ data/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ── 前端构建 ──
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build


# ── 最终镜像（Nginx + 后端 + 前端） ──
FROM python:3.13-slim AS production

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# 应用代码
COPY app/ app/
COPY config.yaml .
COPY data/ data/

# 前端构建产物
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Nginx 配置
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

# 启动脚本
COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 80

CMD ["/app/start.sh"]
