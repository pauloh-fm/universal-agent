# Universal Agent

A small, production-minded template for building **tool-using AI agents** with
[LangGraph](https://github.com/langchain-ai/langgraph) and [FastAPI](https://fastapi.tiangolo.com/).

- **Agents are folders.** An agent is an `agent.yaml` + a `prompt.md` (+ optional `knowledge/`). No code needed to add one.
- **Tools are typed functions** with a declared risk level: `read` or `write`.
- **Human approval for side effects.** Any `write` tool pauses the run (LangGraph `interrupt`) until a person approves or rejects it.
- **Any OpenAI-compatible model.** OpenAI, Ollama, vLLM, LiteLLM, OpenRouter, or a gateway in front of other providers.
- **Persistent threads** in SQLite, survive restarts.
- **Runs offline out of the box** with a deterministic fake model: tests and the first run need no API key.
- **Ready-made examples:** a clinic receptionist that books appointments (local calendar or Google Calendar) and an
  e-commerce assistant that places and tracks orders. All example data is fictitious.
- **Documented for humans and AI coding agents.** See [`docs/`](docs/) and the [AI build guide](docs/ai-build-guide.md).

```
POST /agents/support/threads/42/messages {"message": "My order arrived broken, I want a refund"}
-> {"status": "awaiting_approval", "pending_tool_calls": [{"name": "create_ticket", "args": {...}, "risk": "write"}]}

POST /agents/support/threads/42/approval {"approved": true}
-> {"status": "completed", "reply": "Ticket a1b2c3d4 created. Our team will reply within one business day."}
```

## Quick start

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <your-fork-url> my-agent && cd my-agent
uv sync                                   # install
uv run pytest -q                          # offline test suite
uv run universal-agent chat assistant     # terminal chat with the fake model
```

Use a real model:

```bash
cp .env.example .env
# edit .env:
#   LLM_PROVIDER=openai
#   LLM_MODEL=gpt-4o-mini
#   LLM_API_KEY=sk-...
uv run universal-agent serve              # http://127.0.0.1:8000/docs
```

Local model with Ollama: `LLM_PROVIDER=openai`, `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=llama3.1`, no key.

Docker: `docker compose up --build` (API on `127.0.0.1:8000`, data in a named volume).

## How it works

```
HTTP / CLI --> AgentRuntime --> LangGraph graph (one per agent, built from agents/<name>/) --> SQLite checkpoints

START -> agent (LLM) -+- no tool calls ---------------------------------------> END
                      +- read tools  -> tools -> agent
                      +- write tool  -> approval (interrupt) -+- approved -> tools -> agent
                                                              +- rejected -> agent
```

Details: [`docs/architecture.md`](docs/architecture.md).

## Project layout

```
src/universal_agent/
  config.py        settings from env / .env
  llm.py           chat model factory + offline ScriptedChatModel
  agents.py        loads and validates agents/<name>/
  graph.py         the LangGraph state machine (approval, step limit, history trim)
  runtime.py       AgentRuntime: chat / resume / history
  api.py           FastAPI app
  __main__.py      CLI: serve | chat | agents
  tools/
    registry.py    @register_tool, risk levels, ToolContext
    builtin.py     calculator, current_time, search_knowledge, create_ticket
    scheduling.py  clinic config, free-slot computation, calendar backends
    clinic.py      appointment tools (clinic-example)
    google_calendar.py  optional Google Calendar backend
    ecommerce.py   catalog and order tools (ecommerce-example)
agents/            example agents: assistant, support, clinic-example, ecommerce-example
tests/             offline test suite
docs/              documentation (start with docs/README.md)
```

## Documentation

| Guide | For |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, run, first request |
| [Architecture](docs/architecture.md) | How the pieces fit and why |
| [Example agents](docs/examples.md) | Clinic scheduling and e-commerce examples, how to adapt them |
| [Google Calendar](docs/integrations/google-calendar.md) | Connect the clinic example to a real calendar |
| [Creating agents](docs/creating-agents.md) | New agent in 5 minutes |
| [Creating tools](docs/creating-tools.md) | New tool, risk levels, testing |
| [Configuration](docs/configuration.md) | Every environment variable |
| [HTTP API](docs/api.md) | Endpoints, payloads, errors |
| [Testing](docs/testing.md) | Offline tests with scripted models |
| [Deployment](docs/deployment.md) | Docker, reverse proxy, production checklist |
| [Security](docs/security.md) | Threat model and safe defaults |
| [Extending](docs/extending.md) | Channels, RAG, MCP, other providers, multi-agent |
| [AI build guide](docs/ai-build-guide.md) | Rules and a phased playbook any AI coding agent can follow to turn this template into a working product |
| [Troubleshooting](docs/troubleshooting.md) | Common errors |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

[Apache License 2.0](LICENSE). You may use, modify and distribute it, including commercially. Keep the license and
`NOTICE` file; the license also grants a patent license from contributors.
