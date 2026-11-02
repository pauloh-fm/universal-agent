# Extending

Recipes for common next steps. Each keeps the core contracts: tools declare risk, write tools need approval, tests run offline.

## Other model providers

`build_chat_model` in `src/universal_agent/llm.py` returns any LangChain `BaseChatModel` that supports `bind_tools`.

```python
# uv add langchain-anthropic
if settings.llm_provider == "anthropic":
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=settings.llm_model, api_key=..., timeout=settings.llm_timeout_seconds)
```

Add the value to the `llm_provider` `Literal` in `config.py` and document it. Same pattern for `langchain-google-genai`,
`langchain-aws`, etc. Alternatively, keep `openai` and point `LLM_BASE_URL` at a gateway (LiteLLM, OpenRouter) that
speaks the OpenAI protocol for every provider.

## Retrieval (RAG)

`search_knowledge` is a keyword search over Markdown paragraphs: fine for a few dozen documents. To scale:

1. Index documents at startup or in a separate job into a vector store (pgvector, Qdrant, Chroma, SQLite-vec).
2. Register a new `read` tool, e.g. `search_docs`, that embeds the query and returns the top passages *with source names*.
3. Keep "cite the [source]" in the prompt so answers stay verifiable.

## MCP tools

Tools from [Model Context Protocol](https://modelcontextprotocol.io/) servers can be adapted with
`langchain-mcp-adapters` (`uv add langchain-mcp-adapters`). Wrap each MCP tool in a factory registered with
`@register_tool` so it gets an explicit risk level; do not bulk-import MCP tools as `read`.

## Channels

The runtime does not know about channels. An adapter (web chat, chat apps, email) only needs to:

1. Authenticate the incoming user and derive a stable `thread_id` from it.
2. Call `AgentRuntime.chat(agent, thread_id, text)` (in-process) or `POST /agents/{agent}/threads/{id}/messages`.
3. If the result is `awaiting_approval`, show the pending action with *Approve / Reject* and call `resume`.
   The approver can be the end user (confirming their own request) or staff, depending on the action.
4. Deliver `reply` back to the channel.

Webhooks must respond fast: acknowledge first and process in a background task or queue.

## Streaming

Use `graph.astream(..., stream_mode="messages")` in a new endpoint that returns Server-Sent Events. Keep the existing
endpoints for clients that do not stream.

## Multi-agent

Two simple patterns, both compatible with the template:

- **Router**: a small agent (or a classifier) chooses which agent receives the message; the channel adapter forwards it.
- **Agent as a tool**: register a `read` tool that calls `AgentRuntime.chat(other_agent, derived_thread, question)` and
  returns the reply. Keep a depth limit to avoid agents calling each other forever.

## Memory across threads

Long-term facts about a user (preferences, profile) belong in your database, exposed through a `read` tool
(`get_user_profile`) and a `write` tool (`update_user_profile`), not in the graph state.

## Postgres checkpoints

See [deployment](deployment.md#scaling).
