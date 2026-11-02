# AI build guide

A playbook for AI coding agents (Claude Code, Codex, Cursor, Copilot, Gemini, Aider, ...) and for humans directing them.
Goal: turn this template into a **working, tested, deployable** agent product, without breaking its safety properties.

Work through the phases in order. Each phase ends with a check that must pass before moving on.

---

## Ground rules (apply to every phase)

1. **Run `make check` before declaring anything done.** It runs ruff, ruff format, mypy strict and pytest.
2. **Tests never call paid or external APIs.** Use `ScriptedChatModel` (see [testing](testing.md)) and fakes/monkeypatch for I/O.
3. **Declare tool risk honestly.** Anything that sends, creates, updates, deletes, pays, books or publishes is `risk="write"`.
   Never route a write tool around the `approval` node.
4. **No secrets in the repo.** New credentials become `SecretStr | None` settings in `config.py`, placeholders in
   `.env.example`, and a row in `docs/configuration.md`.
5. **Add dependencies with `uv add <pkg>`** (`uv add --dev` for tooling). Never `pip install`.
6. **Keep `AgentState` small.** Conversation + step counter. Business data lives behind tools.
7. **Docs are part of the change.** Behaviour, configuration or API changes update the matching file in `docs/`.
8. **Style:** type hints everywhere, docstrings on public functions, line length 130. Tool docstrings are read by the model:
   write them as instructions ("Use it when ...").

### Where things live

| Need to... | Edit |
| --- | --- |
| Add an agent | `agents/<name>/agent.yaml` + `prompt.md` ([guide](creating-agents.md)) |
| Add a tool | `src/universal_agent/tools/<module>.py` + import in `tools/__init__.py` ([guide](creating-tools.md)) |
| Add a setting | `config.py` + `.env.example` + `docs/configuration.md` |
| Change the agent loop | `graph.py` (+ tests in `tests/test_runtime.py`) |
| Add an endpoint | `api.py` + `docs/api.md` + `tests/test_api.py` |
| Add a model provider | `llm.py` (`build_chat_model`) |

### Commands

```bash
uv sync                          # install
make check                       # everything CI runs
uv run universal-agent agents    # validate agent folders
uv run universal-agent chat <agent>
uv run universal-agent serve     # API on :8000, OpenAPI at /docs
```

---

## Phase 0. Baseline

```bash
uv sync && make check && uv run universal-agent agents
```

Check: all green, two agents listed, no errors. If not, fix the environment first ([troubleshooting](troubleshooting.md)).

## Phase 1. Write down the product (no code)

Create `docs/product.md` in the fork with:

- **Who** uses the agent and through which channel (web, API, chat app, internal tool).
- **Jobs**: the 3 to 10 concrete tasks it must do, each as "When <situation>, the agent <does X> using <data/system>".
- **Actions** with side effects (these will be `write` tools) and who approves them.
- **Data sources** (documents, databases, APIs) and how to authenticate.
- **Out of scope**: what it must refuse or hand off to a human.
- **Acceptance examples**: 5 to 15 example conversations with the expected outcome. They become tests in phase 4.

Check: every job maps to either knowledge, a `read` tool or a `write` tool.

## Phase 2. Agents

For each distinct role (do not create more agents than needed; one agent with good tools beats several thin ones):

1. Copy `agents/assistant/` to `agents/<name>/`, set `name` to the folder name.
2. Write `prompt.md` with sections *Role*, *How to answer*, *Rules*, *Style* ([guide](creating-agents.md)).
3. Put reference documents in `agents/<name>/knowledge/*.md`, one fact per paragraph.
4. Delete the example agents you do not need, and the tests that reference them.

Check: `uv run universal-agent agents` shows no errors.

## Phase 3. Tools

For each data source or action from phase 1:

1. Write the pure logic as a plain function and unit-test it.
2. Wrap it with `@register_tool("<name>", risk=...)` ([guide](creating-tools.md)).
3. Credentials via settings; timeouts on every network call; return `"error: ..."` strings for expected failures.
4. Add the tool to the agents that need it.

Check: `make check` green; each tool has a unit test and appears in at least one agent.

## Phase 4. Behaviour tests

Turn the acceptance examples from phase 1 into tests with `ScriptedChatModel`:

- **Routing**: given a user message, the scripted tool calls lead to the expected reply.
- **Approval**: every `write` tool returns `awaiting_approval` first and does nothing until approved;
  rejected calls never execute.
- **Failure**: tools that error produce a graceful reply.

These tests verify the *wiring*, not the model's judgement. For model quality, add an optional eval script
(see [testing](testing.md#evaluating-a-real-model)) that is not part of `make check`.

Check: `make check` green.

## Phase 5. Real model smoke test

1. `cp .env.example .env`, set `LLM_PROVIDER=openai`, model and key (or a local model).
2. `uv run universal-agent chat <agent>` and run 3 to 5 acceptance examples by hand.
3. Adjust prompts and tool docstrings where the model chose the wrong tool or answered without using one.

Check: the examples behave as specified. Record the model used in `docs/product.md`.

## Phase 6. Integrate a channel (if needed)

The API is channel-agnostic. For chat apps, write a small adapter that maps the channel's user/conversation id to
`thread_id`, calls `POST .../messages`, and turns `awaiting_approval` into a confirmation UI ([extending](extending.md#channels)).

Check: an end-to-end test of the adapter with a mocked channel.

## Phase 7. Deploy

Follow [deployment](deployment.md): set `API_TOKEN`, put it behind HTTPS, persist `/data`, set the model key as a secret.

Check: `GET /health` returns `ok` on the deployed URL; an authenticated request without the token returns 401;
one real conversation works.

---

## Definition of done

- `make check` passes; CI is green.
- `uv run universal-agent agents` reports no errors.
- Every `write` tool has an approval test.
- `.env.example` and `docs/configuration.md` list every setting.
- `docs/product.md` describes what the agent does and does not do.
- No secrets, personal data or real customer data in the repository.

## Common mistakes

| Mistake | Do instead |
| --- | --- |
| Putting "always ask before sending" in the prompt | Mark the tool `write`; the graph enforces it. |
| Returning large JSON from a tool | Return the few fields the model needs, as short text. |
| One agent per tiny task | One agent per role; more tools, fewer agents. |
| Storing customer data in `AgentState` | Store it behind a tool; keep the state small. |
| Testing with a real model in CI | Script the model; keep real-model evals optional. |
| Catching every exception in a tool silently | Return a specific `"error: ..."` the model can act on. |
