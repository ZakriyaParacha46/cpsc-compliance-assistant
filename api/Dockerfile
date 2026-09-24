# Built natively for arm64 (Apple Silicon locally, t4g on EC2, ubuntu-24.04-arm in CI).
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY ingest ./ingest
COPY eval ./eval
ENV PATH="/app/.venv/bin:$PATH"

# uid 1000 matches ec2-user, so files written to mounted folders (data/) stay yours.
RUN useradd --uid 1000 app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"
# No --proxy-headers: app.main.client_ip reads X-Forwarded-For itself and trusts only our own
# proxies (TRUSTED_PROXY_HOPS), so a client can't forge its IP to dodge rate limits.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
