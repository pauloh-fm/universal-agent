# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 agent
WORKDIR /app
COPY --from=build --chown=agent:agent /app /app
COPY --chown=agent:agent agents ./agents
ENV PATH="/app/.venv/bin:$PATH" DATA_DIR=/data AGENTS_DIR=/app/agents
RUN mkdir -p /data && chown agent:agent /data
USER agent
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["universal-agent", "serve", "--host", "0.0.0.0", "--port", "8000"]
