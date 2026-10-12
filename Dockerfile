# AskSQL API 镜像。构建上下文 = 仓库根（pyproject.toml / uv.lock / start_api.py 都在根目录）。
#
# 构建:  docker build -t asksql-api .
# 运行:  建议用 docker compose（见 docker-compose.yml），单容器跑需要自行提供
#        FALKORDB_URL 并给 /app/backend/src/app/data 挂卷。

FROM python:3.13-slim

# uv 官方推荐：从官方镜像拷 uv/uvx，不经过 pip 安装
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 先只拷依赖清单，把「装依赖」这层缓存住（代码变动不会击穿它）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再拷其余源码（.dockerignore 负责把无关大目录挡在上下文外）
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8065

# 启动前先跑迁移：manage.db 挂卷后是空库时，alembic upgrade head 负责建表。
# exec 让 python 接过 PID 1，能正确收到 SIGTERM。
CMD ["sh", "-c", "uv run alembic -c backend/alembic.ini upgrade head && exec python start_api.py"]
