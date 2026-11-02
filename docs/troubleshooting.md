# Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `LLM_PROVIDER=openai needs LLM_API_KEY` at startup | Real provider without key or base URL. | Set `LLM_API_KEY`, or `LLM_BASE_URL` for a local server, or use `LLM_PROVIDER=fake`. |
| Agent missing from `GET /agents` | Loading error. | See `errors` in `GET /agents` or run `uv run universal-agent agents`. |
| `Unknown tool 'x'` | Tool not registered or module not imported. | Check the name in `@register_tool` and that `tools/__init__.py` imports the module. |
| `name 'a' must match folder 'b'` | `name:` differs from folder name. | Rename one of them. |
| Replies like `[fake model] You said: ...` | Running the fake model. | Configure a real provider in `.env`. |
| 409 on `/messages` | The thread waits for approval. | Call `/approval` first, or use a new `thread_id`. |
| 409 on `/approval` | Nothing pending on that thread. | Check `GET /agents/{agent}/threads/{id}`. |
| The model never calls tools | Model without tool calling, or vague tool docstrings. | Use a tool-capable model; make docstrings say *when* to use the tool; lower temperature. |
| `I stopped because this request needed too many steps` | Hit `MAX_STEPS`. | Inspect the thread history for a loop; improve tool errors/prompts; raise `MAX_STEPS` only if the task needs it. |
| Answers ignore older messages | `MAX_CONTEXT_MESSAGES` trimmed them. | Raise it, or add a summarisation step. |
| 500 after a long wait | Model API timeout or outage. | Check logs; raise `LLM_TIMEOUT_SECONDS`; check the provider status. |
| `uv run` fails to build the project | Missing `LICENSE`/`NOTICE` or broken `pyproject.toml`. | Restore the files; run `uv sync`. |
