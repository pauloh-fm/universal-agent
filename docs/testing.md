# Testing

```bash
make check          # ruff + format + mypy strict + pytest
uv run pytest -q    # tests only
```

The suite runs offline and needs no key: the model is replaced by `ScriptedChatModel`.

## Scripting the model

`ScriptedChatModel(script=[...])` returns the given `AIMessage`s in order, then falls back to echoing. Use it to
simulate exactly which tools the model calls:

```python
from langchain_core.messages import AIMessage
from tests.conftest import tool_call


async def test_ticket_needs_approval(make_runtime, settings):
    rt = make_runtime(
        [
            tool_call("create_ticket", {"title": "Broken", "description": "Arrived broken"}),
            AIMessage(content="Ticket opened."),
        ]
    )
    first = await rt.chat("support", "t1", "I want a human")
    assert first.status == "awaiting_approval"

    done = await rt.resume("support", "t1", approved=True)
    assert done.reply == "Ticket opened."
```

Fixtures (`tests/conftest.py`):

- `settings`: fake provider, repository `agents/`, a temporary `data_dir`.
- `make_runtime(script)`: `AgentRuntime` with an in-memory checkpointer and the scripted model.
- `tool_call(name, args, call_id)`: builds an `AIMessage` with one tool call.

HTTP tests use `fastapi.testclient.TestClient(create_app(settings, runtime=rt))`. Without `runtime=`, the app uses the
real SQLite checkpointer from `settings.data_dir` (see `test_sqlite_persistence`).

## What to test

| Layer | Example |
| --- | --- |
| Tool logic | Pure function, edge cases, error strings. |
| Agent loading | `AgentRegistry.from_directory` has no errors. |
| Wiring | Scripted tool calls produce the expected reply. |
| Safety | Each `write` tool waits for approval and does nothing when rejected. |
| API | Status codes, validation, auth. |

## Evaluating a real model

Model quality (did it choose the right tool?) is not deterministic and costs money, so keep it out of `make check`.
A simple approach: a script `scripts/eval.py` that loads acceptance examples from a YAML file, runs them against the
configured model with `AgentRuntime` and an `InMemorySaver`, and reports which tool was called and whether the reply
contains the expected facts. Run it manually or on a schedule, never on every commit.
