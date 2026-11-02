# Creating agents

An agent is a folder under `AGENTS_DIR` (default `agents/`):

```
agents/
  billing/
    agent.yaml        required
    prompt.md         required
    knowledge/        optional, Markdown files read by search_knowledge
      plans.md
```

## 1. `agent.yaml`

```yaml
name: billing                  # must equal the folder name; ^[a-z][a-z0-9-]{1,40}$
description: Answers billing questions and opens refund tickets.   # 1-300 chars, shown in GET /agents
version: 0.1.0                 # optional, informational
model: gpt-4o                  # optional; overrides LLM_MODEL for this agent only
tools:                         # optional; names registered with @register_tool
  - search_knowledge
  - calculator
  - create_ticket
```

Validation happens at startup. Run `uv run universal-agent agents` to see errors such as unknown tools or a name mismatch.

## 2. `prompt.md`

The whole file becomes the system prompt. A structure that works well:

```markdown
# Role
Who the agent is, for whom, and the single goal.

# How to answer
Numbered procedure. When to call which tool. What to do when a tool returns nothing.

# Rules
Hard limits: never invent prices, always cite [source], ask before ...

# Style
Tone, length, language.
```

Tips:

- Tell the model *when* to use each tool. Tool descriptions say *what* a tool does; the prompt says *when*.
- Do not rely on the prompt for safety. Mark the tool as `write` instead; the graph enforces approval.
- Keep it short. Long prompts cost tokens on every call.
- Write the prompt in the language you want answers in, or instruct "answer in the user's language".

## 3. Knowledge (optional)

Put Markdown files in `knowledge/`. The `search_knowledge` tool splits them into paragraphs and returns the best matches
with their file name, so the agent can cite `[file.md]`. Separate topics with blank lines; one fact per paragraph works best.

## 4. Test it

```bash
uv run universal-agent agents
uv run universal-agent chat billing
```

Add a test that scripts the tool calls you expect (see [testing](testing.md)):

```python
async def test_billing_uses_knowledge(make_runtime):
    rt = make_runtime([tool_call("search_knowledge", {"query": "refund"}), AIMessage(content="Refunds take 5 days [plans.md].")])
    result = await rt.chat("billing", "t1", "how long do refunds take?")
    assert "[plans.md]" in result.reply
```

Note: tests load agents from the repository `agents/` folder (see `tests/conftest.py`).
