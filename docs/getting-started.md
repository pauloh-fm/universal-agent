# Getting started

## 1. Install

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/), git.

```bash
git clone <your-fork-url> my-agent
cd my-agent
uv sync
```

## 2. Verify

```bash
make check        # or: uv run pytest -q
uv run universal-agent agents
```

Expected:

```
assistant            General assistant that can do exact math and tell the current time.  tools=['calculator', 'current_time']
clinic-example       Receptionist for a fictitious clinic. Answers questions and books or cancels appointments after confirmation.  tools=[...]
ecommerce-example    Shopping assistant for a fictitious online store. Finds products, tracks orders and places or cancels orders after confirmation.  tools=[...]
support              Answers questions from the knowledge base and opens support tickets after confirmation.  tools=['search_knowledge', 'create_ticket']
```

## 3. Talk to an agent (offline)

```bash
uv run universal-agent chat assistant
you> hello
assistant> [fake model] You said: hello
```

The fake model only echoes. It exists so you can run and test everything without a key.

## 4. Use a real model

```bash
cp .env.example .env
```

Pick one:

```dotenv
# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...

# Ollama (local, free)
LLM_PROVIDER=openai
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1

# Any OpenAI-compatible gateway (OpenRouter, LiteLLM, vLLM...)
LLM_PROVIDER=openai
LLM_BASE_URL=https://your-gateway/v1
LLM_MODEL=provider/model-name
LLM_API_KEY=...
```

The model must support tool calling.

```bash
uv run universal-agent chat support
you> how long do I have to return an item?
support> You can return any unused item within 30 days of delivery [returns.md].
you> it arrived broken, I want to talk to a person
agent wants to run: [{"name": "create_ticket", "args": {...}, "risk": "write"}]
approve? [y/N] y
support> Done, ticket 3f9a1c2e was created.
```

## 5. Run the HTTP API

```bash
uv run universal-agent serve      # http://127.0.0.1:8000/docs
```

```bash
curl -s localhost:8000/agents/support/threads/demo/messages \
  -H 'content-type: application/json' -d '{"message":"I need a human, my item is broken"}'
# {"status":"awaiting_approval","reply":null,"pending_tool_calls":[...]}

curl -s localhost:8000/agents/support/threads/demo/approval \
  -H 'content-type: application/json' -d '{"approved":true}'
# {"status":"completed","reply":"...","pending_tool_calls":[]}
```

Next: [create your own agent](creating-agents.md).
