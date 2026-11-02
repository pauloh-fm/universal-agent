# Configuration

All settings come from environment variables (case-insensitive) or a `.env` file in the working directory.
Environment variables win over `.env`. Template: [`.env.example`](../.env.example).

## Model

| Variable | Default | Description |
| --- | --- | --- |
| `LLM_PROVIDER` | `fake` | `fake`: offline echo model. `openai`: any OpenAI-compatible Chat Completions API. |
| `LLM_MODEL` | `gpt-4o-mini` | Model name sent to the API. Agents can override it with `model:` in `agent.yaml`. |
| `LLM_BASE_URL` | unset | API base URL, e.g. `http://localhost:11434/v1`. Unset means `https://api.openai.com/v1`. |
| `LLM_API_KEY` | unset | API key. Required for `openai` unless `LLM_BASE_URL` points to a server without auth. |
| `LLM_TEMPERATURE` | `0.2` | 0 to 2. Low values make tool use more reliable. |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-request timeout. The client retries twice. |

The model must support tool calling (function calling).

## Runtime

| Variable | Default | Description |
| --- | --- | --- |
| `AGENTS_DIR` | `agents` | Folder with one sub-folder per agent. |
| `DATA_DIR` | `.data` | Writable folder: `checkpoints.sqlite` (threads) and example tool output. |
| `MAX_STEPS` | `8` | Max model calls per user turn. Stops tool loops. |
| `MAX_CONTEXT_MESSAGES` | `40` | Messages sent to the model per call (most recent). Full history stays in the checkpoint. |
| `REQUIRE_CONFIRMATION_FOR` | `["write"]` | JSON list of risk levels needing approval: `["write"]`, `["read","write"]` or `[]` (no approval, not recommended). |

## Calendar (clinic-example)

| Variable | Default | Description |
| --- | --- | --- |
| `CALENDAR_BACKEND` | `local` | `local`: appointments in `DATA_DIR/<agent>-appointments.json`. `google`: Google Calendar. |
| `GOOGLE_CALENDAR_ID` | unset | Calendar ID from Google Calendar settings. Required for `google`. |
| `GOOGLE_CREDENTIALS_FILE` | unset | Path to the service-account JSON key, outside the repository. Required for `google`. |

Setup: [Google Calendar integration](integrations/google-calendar.md). Requires `uv sync --extra google`.

## HTTP API

| Variable | Default | Description |
| --- | --- | --- |
| `API_TOKEN` | unset | If set, every route except `/health` requires `Authorization: Bearer <token>`. Set it in every non-local deployment. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

## Adding a setting

1. Add a typed field to `Settings` in `src/universal_agent/config.py` (use `SecretStr` for secrets).
2. Add a commented placeholder to `.env.example`.
3. Add a row here.
4. Read it from `ctx.settings` inside tool factories, or from `get_settings()` elsewhere.
