FROM node:24-bookworm-slim AS console
WORKDIR /console
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPSPILOT_DB=/data/opspilot.sqlite3 OPSPILOT_WEB_DIR=/app/web
COPY requirements-runtime.lock ./
RUN python -m pip install --no-cache-dir -r requirements-runtime.lock
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts/manage_users.py scripts/backup_db.py ./scripts/
RUN python -m pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home opspilot \
    && mkdir /data && chown opspilot:opspilot /data
COPY --from=console /console/dist ./web/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)"
# Compose binds host loopback. TLS ingress is a separate deployment boundary.
CMD ["uvicorn", "opspilot_x.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
