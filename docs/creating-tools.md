# Creating tools

## Anatomy

```python
# src/universal_agent/tools/weather.py
import httpx
from langchain_core.tools import BaseTool, StructuredTool

from .registry import ToolContext, register_tool


@register_tool("get_weather", risk="read", description="Current weather for a city.")
def _get_weather(ctx: ToolContext) -> BaseTool:
    def get_weather(city: str) -> str:
        """Get the current weather for a city. Use it when the user asks about weather."""
        try:
            r = httpx.get("https://wttr.in/" + city, params={"format": "3"}, timeout=10)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            return f"error: weather service unavailable ({exc.__class__.__name__})"
        return r.text.strip()

    return StructuredTool.from_function(get_weather)
```

Then import the module so registration runs, in `src/universal_agent/tools/__init__.py`:

```python
from . import builtin, weather  # noqa: F401
```

And list it in an agent: `tools: [get_weather]`.

## Rules

| Rule | Why |
| --- | --- |
| The inner function name must equal the registered name | The registry checks it; the model calls tools by this name. |
| Type-annotate every parameter | The JSON schema sent to the model is generated from the signature. |
| Write the docstring as an instruction to the model | It is the tool description the model sees. |
| Return a short string | Tool output goes back into the context; long outputs cost tokens and confuse the model. |
| Return `"error: ..."` for expected failures | The model can explain or retry. Unexpected exceptions are also caught by `ToolNode`. |
| Set timeouts on all I/O | A hanging tool blocks the run. |
| Never put secrets in arguments or outputs | Read them from `ctx.settings` or environment inside the factory. |

## Risk levels

- `read`: no observable side effect (lookups, math, search). Runs immediately.
- `write`: changes the world (send email/message, create/update/delete records, payments, publishing, booking).
  Pauses for approval while `write` is in `REQUIRE_CONFIRMATION_FOR` (the default).

When in doubt, choose `write`. Tools not found in the risk map are treated as `write`.

## The factory and `ToolContext`

The decorator registers a *factory* called once per agent graph with:

- `ctx.agent_name`, `ctx.agent_dir`: scope storage or knowledge per agent.
- `ctx.settings`: runtime settings (data dir, your own settings).

Create clients (HTTP sessions, DB pools) in the factory, not on every call.

## Credentials

Add a setting in `config.py` (type `SecretStr | None`), document it in `.env.example` and `docs/configuration.md`, and read it
in the factory. Fail with a clear message if it is missing:

```python
token = ctx.settings.crm_token
if token is None:
    raise ValueError("get_customer needs CRM_TOKEN")
```

## Testing a tool

Test the plain logic directly, then the tool inside the graph with a scripted model:

```python
async def test_weather_tool(make_runtime, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse("Paris: 20C"))
    rt = make_runtime([tool_call("get_weather", {"city": "Paris"}), AIMessage(content="20C in Paris.")])
    ...
```

Never hit real external services in the default test run.
