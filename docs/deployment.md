# Deployment

## Docker

```bash
cp .env.example .env    # set LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, API_TOKEN
docker compose up -d --build
curl -s 127.0.0.1:8000/health
```

The image:

- runs as a non-root user (uid 10001);
- stores threads in the `/data` volume;
- mounts `./agents` read-only, so prompt changes need only a restart (`docker compose restart`);
- binds to `127.0.0.1` in `compose.yaml`; expose it through a reverse proxy.

## Without Docker (systemd)

```ini
# /etc/systemd/system/universal-agent.service
[Unit]
Description=Universal Agent
After=network-online.target

[Service]
WorkingDirectory=/opt/universal-agent
EnvironmentFile=/opt/universal-agent/.env
ExecStart=/opt/universal-agent/.venv/bin/universal-agent serve --host 127.0.0.1 --port 8000
User=agent
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/universal-agent/.data

[Install]
WantedBy=multi-user.target
```

```bash
uv sync --frozen --no-dev
sudo systemctl enable --now universal-agent
```

## Reverse proxy

Any proxy with TLS works. Caddy example:

```
agent.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Model calls can take tens of seconds; set proxy read timeouts to at least `LLM_TIMEOUT_SECONDS * MAX_STEPS`.

## Production checklist

- [ ] `API_TOKEN` set to a long random value (`openssl rand -hex 32`), or the API is reachable only from a private network.
- [ ] HTTPS in front of the API.
- [ ] `LLM_API_KEY` stored as a secret (env file with `chmod 600`, Docker/Kubernetes secret), never in the image.
- [ ] `DATA_DIR` on persistent storage and backed up.
- [ ] `REQUIRE_CONFIRMATION_FOR` includes `write`.
- [ ] Logs collected; alert on 5xx.
- [ ] Spending limit configured at the model provider.

## Scaling

The default SQLite checkpointer is for a single instance. For several replicas, switch to
`langgraph-checkpoint-postgres` (`uv add langgraph-checkpoint-postgres`) and create the saver in `api.py`'s lifespan
with `AsyncPostgresSaver.from_conn_string(...)`; call `await saver.setup()` once. Everything else is stateless.
