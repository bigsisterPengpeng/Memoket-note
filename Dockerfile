FROM node:22-bookworm-slim AS web
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
COPY shared /build/shared
RUN npm run build

FROM python:3.11-slim-bookworm AS wheels
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY backend/requirements.txt backend/requirements-agents.txt backend/constraints.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    -r requirements.txt -r requirements-agents.txt -c constraints.txt

FROM python:3.11-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="Memoket NOTE" \
      org.opencontainers.image.description="An agent-native writing workspace with local KITE memory" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/bigsisterPengpeng/Memoket-note"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KITE_DATA_DIR=/data \
    MEMOKET_NOTE_WEB_DIR=/app/web \
    HOME=/data
RUN --mount=type=bind,from=wheels,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index /wheels/*.whl \
    && groupadd --gid 10001 note \
    && useradd --uid 10001 --gid note --home-dir /data --no-create-home note \
    && mkdir /data && chown note:note /data
WORKDIR /app/backend
COPY backend/app ./app
COPY backend/skills ./skills
COPY --from=web /build/frontend/dist /app/web
COPY LICENSE /app/LICENSE
COPY docs/third-party-notices.md /app/third-party-notices.md
COPY docs/licenses /app/licenses
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=3).close()"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
