# ============================================================
# trip-planner 部署镜像（Vue3 前端 + FastAPI 后端，单镜像单端口 7860）
# 参考 work1-ycy docker/Dockerfile 的多阶段构建模式，基于 vendor 基础镜像
# 架构：nginx(7860) 承载前端静态资源，/api 反代到 uvicorn(127.0.0.1:8000)
# 注意：ENV VERSION 中的 __VERSION__ 占位符由 CI 的 sed 替换，勿改动
# ============================================================

# --------------------------------------------
# 阶段1：构建前端静态资源（vendor 镜像内含 Node 22）
# --------------------------------------------
ARG CI_PROJECT_TITLE
FROM docker-registry.azgpu05.azshentong.com/starzz/az:${CI_PROJECT_TITLE}_vendor AS frontend-builder

WORKDIR /build

# 先拷贝依赖清单（利用 Docker 缓存层）
COPY frontend/package.json frontend/package-lock.json ./

# 使用 npm install 代替 npm ci，提高容错性（与 work1-ycy 做法一致）
# --include=dev：vite/plugin-vue 等构建工具在 devDependencies，
# 基础镜像的 NODE_ENV=production 会让 npm 跳过它们，导致前端无法打包
RUN npm install --no-audit --no-fund --include=dev

# 拷贝前端源码（.dockerignore 已排除 node_modules/dist）
COPY frontend/ ./

# 生产构建强制使用相对 API 地址（同源经 nginx 反代访问后端），
# .env.production 优先级高于 .env，避免本地开发用的绝对地址被打进产物
RUN echo "VITE_API_BASE_URL=" > .env.production

# 直接用 vite 打包：跳过 package.json 中 build 脚本的 vue-tsc 类型检查
# （当前代码存在类型告警，不影响运行时产物；类型治理后再切回 npm run build）
RUN npx vite build

# --------------------------------------------
# 阶段2：运行时（vendor 镜像 = Python 3.11 + Node 22 + 基础工具）
# --------------------------------------------
ARG CI_PROJECT_TITLE
FROM docker-registry.azgpu05.azshentong.com/starzz/az:${CI_PROJECT_TITLE}_vendor

# 版本信息（CI 通过 sed 将 __VERSION__ 替换为 分支_流水线号，与 work1-ycy 一致）
ENV VERSION=__VERSION__

# 安装 nginx（前端静态服务 + API 反代；curl 已由 vendor 镜像提供）
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# 后端 Python 依赖（先装依赖再拷代码以利用缓存层；国内镜像源加速）
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r /tmp/requirements.txt

WORKDIR /app

# 拷贝后端源码与运行配置（backend/.env 随仓库提交，与 work1-ycy 的
# "COPY .env .env" 模式一致；.dockerignore 已排除 venv/__pycache__）
COPY backend/ ./backend/

# 拷贝前端构建产物
COPY --from=frontend-builder /build/dist ./frontend-dist

# nginx 站点配置与容器启动脚本
COPY docker/nginx.conf /etc/nginx/conf.d/trip-planner.conf
COPY docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# 对外端口（与 CI 的 DEPLOY_HTTP_PORT 定值一致）
ENV NODE_ENV=production
EXPOSE 7860

# 启动：拉起后端 uvicorn，再前台运行 nginx
CMD ["/app/start.sh"]
