# Architecture

## Components

| Module | Responsibility |
| --- | --- |
| `config.py` | `Settings` (pydantic-settings). Reads env vars and `.env`. Validates provider settings. |
| `llm.py` | `build_chat_model(settings)` returns a LangChain `BaseChatModel`. `ScriptedChatModel` is the offline model. |
| `tools/registry.py` | `@register_tool(name, risk=...)` registers a *factory* that builds a `BaseTool` for a given `ToolContext`. |
| `tools/builtin.py` | Example tools. |
| `agents.py` | Loads `agents/<name>/`, validates the manifest, checks every tool exists. Bad agents are skipped, not fatal. |
| `graph.py` | `build_graph(...)` compiles the LangGraph state machine. |
| `state.py` | `AgentState`: `messages` + `steps`. |
| `runtime.py` | `AgentRuntime`: caches one compiled graph per agent; `chat`, `resume`, `pending`, `history`. |
| `api.py` | FastAPI app. Owns the SQLite checkpointer lifecycle. Optional bearer-token auth. |
| `__main__.py` | CLI: `serve`, `chat`, `agents`. |

Dependency direction: `api` / `__main__` → `runtime` → `graph`, `agents`, `llm`, `tools` → `config`.
Nothing imports `api`. This keeps the runtime usable from any other entry point (queue worker, chat channel, notebook).

## The graph

```
START ─► agent ─┬─ no tool calls ─────────────────────────────► END
                ├─ only read tools ─► tools ─► agent
                └─ any write tool ──► approval ─┬─ approved ─► tools ─► agent
                                                └─ rejected ─► agent   (ToolMessage "Rejected by the user")
```

- **agent**: calls the model with `system prompt + trimmed history`. Increments `steps`. If `steps > MAX_STEPS`, it
  answers with a fixed message instead of calling the model, which ends any tool loop.
- **route**: inspects the last `AIMessage.tool_calls`. If any call's risk is in `REQUIRE_CONFIRMATION_FOR`, go to approval.
  Unknown tools are treated as `write` (fail safe).
- **approval**: calls `interrupt({"kind": "tool_approval", "tool_calls": [...]})`. The run stops and the checkpointer
  saves the state. The caller resumes with `Command(resume={"approved": bool, "reason": str})`.
  Approval is per *turn*: all tool calls in that model message are approved or rejected together.
- **tools**: LangGraph `ToolNode` with `handle_tool_errors=True`: exceptions become error `ToolMessage`s the model can read.

## Request lifecycle

1. `POST /agents/support/threads/42/messages` → `AgentRuntime.chat("support", "42", text)`.
2. The runtime refuses (409) if the thread already waits for approval: you cannot talk over a pending decision.
3. Thread id in LangGraph is `"support:42"`, so different agents never share a conversation.
4. The graph runs until it ends or interrupts. The runtime reads the saved state and returns a `TurnResult`:
   `completed` with `reply`, or `awaiting_approval` with `pending_tool_calls`.
5. `POST .../approval` → `AgentRuntime.resume(...)` → graph continues from the checkpoint.

## Design decisions

| Decision | Why |
| --- | --- |
| Agents as folders (YAML + Markdown) | Non-developers can edit prompts; diffs are readable; adding an agent needs no code. |
| Risk on the tool, not in the prompt | Safety must not depend on the model obeying instructions. |
| `interrupt` + checkpointer for approval | Approval can take hours; the run survives restarts and needs no in-memory state. |
| Fake model as default | Tests are deterministic and free; CI never needs secrets. |
| One OpenAI-compatible client | Covers OpenAI, local models and every major gateway with one dependency. Others plug into `llm.py`. |
| Small state | State is serialised on every step. Business data belongs in tools and databases. |
| Keyword retriever in `search_knowledge` | Zero dependencies, good enough for a few dozen documents; swap for vectors when needed ([extending](extending.md#retrieval-rag)). |
| Broken agent does not crash the server | One bad YAML should not take every agent offline; errors are visible at `GET /agents`. |

## Limits of the template (on purpose)

- No user accounts or multi-tenancy. Add them in front of the API or in the thread id scheme.
- No streaming responses. See [extending](extending.md#streaming).
- SQLite checkpoints fit one instance. For horizontal scaling use `langgraph-checkpoint-postgres`.
