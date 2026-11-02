# HTTP API

Base URL: `http://127.0.0.1:8000` by default. Interactive OpenAPI docs at `/docs`.

Authentication: when `API_TOKEN` is set, send `Authorization: Bearer <token>` on every route except `/health`.

`thread_id` must match `[A-Za-z0-9_.-]{1,128}`. Use it to map your users/conversations (e.g. `user-123`, `ticket.987`).
Threads are scoped per agent: `support/threads/1` and `assistant/threads/1` are different conversations.

## `GET /health`

```json
{"status": "ok", "version": "0.1.0"}
```

## `GET /agents`

```json
{
  "agents": [{"name": "support", "description": "...", "version": "0.1.0", "tools": ["search_knowledge", "create_ticket"]}],
  "errors": {"broken-agent": "invalid agent.yaml: ('description',) Field required"}
}
```

## `POST /agents/{agent}/threads/{thread_id}/messages`

Body: `{"message": "text"}` (1 to 20,000 characters).

Response (`TurnResult`):

```json
{"status": "completed", "reply": "Refunds take up to 5 business days [returns.md].", "pending_tool_calls": []}
```

or, when a tool needs approval:

```json
{
  "status": "awaiting_approval",
  "reply": null,
  "pending_tool_calls": [
    {"id": "call_abc", "name": "create_ticket", "args": {"title": "Broken item", "description": "..."}, "risk": "write"}
  ]
}
```

## `POST /agents/{agent}/threads/{thread_id}/approval`

Body: `{"approved": true}` or `{"approved": false, "reason": "wrong customer"}`.

Approves or rejects **all** pending tool calls of that thread. Returns a `TurnResult` (it may ask for approval again if
the model proposes another write action).

## `GET /agents/{agent}/threads/{thread_id}`

```json
{
  "messages": [{"role": "human", "content": "..."}, {"role": "ai", "content": "..."}, {"role": "tool", "content": "..."}],
  "pending_tool_calls": []
}
```

Roles: `human`, `ai`, `tool`. AI messages that only call tools have empty `content`.

## Errors

| Status | When |
| --- | --- |
| 401 | Missing or wrong bearer token. |
| 404 | Unknown agent. |
| 409 | Message sent while the thread waits for approval, or approval sent when nothing is pending. |
| 422 | Invalid body or `thread_id`. |
| 500 | Unexpected error (e.g. the model API is down). Check the server log. |
