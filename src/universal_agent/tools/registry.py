"""Tool registry.

A *tool* is a LangChain ``BaseTool`` plus metadata the runtime needs:

* ``risk`` - ``"read"`` (no side effects) or ``"write"`` (changes something outside the
  agent: sends a message, creates a record, spends money). Write tools pause the graph
  for human confirmation by default.
* a *factory* - receives a :class:`ToolContext` so a tool can be scoped to one agent
  (its folder, its knowledge base) and to the runtime settings.

Register new tools with :func:`register_tool`. Agents opt in by listing the tool name
in ``agent.yaml``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain_core.tools import BaseTool

from ..config import Settings

Risk = Literal["read", "write"]


@dataclass(frozen=True)
class ToolContext:
    agent_name: str
    agent_dir: Path
    settings: Settings


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    risk: Risk
    factory: Callable[[ToolContext], BaseTool]
    description: str = ""


_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(
    name: str, *, risk: Risk, description: str = ""
) -> Callable[[Callable[[ToolContext], BaseTool]], Callable[[ToolContext], BaseTool]]:
    """Decorator for a tool factory.

    >>> @register_tool("get_weather", risk="read")
    ... def _factory(ctx: ToolContext) -> BaseTool: ...
    """

    def decorator(factory: Callable[[ToolContext], BaseTool]) -> Callable[[ToolContext], BaseTool]:
        if name in _REGISTRY:
            raise ValueError(f"Tool '{name}' is already registered")
        _REGISTRY[name] = ToolDefinition(name=name, risk=risk, factory=factory, description=description)
        return factory

    return decorator


def get_tool_definition(name: str) -> ToolDefinition:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown tool '{name}'. Registered: {sorted(_REGISTRY)}") from None


def registered_tools() -> dict[str, ToolDefinition]:
    return dict(_REGISTRY)


def build_tools(names: list[str], ctx: ToolContext) -> tuple[list[BaseTool], dict[str, Risk]]:
    """Instantiate the tools an agent asked for. Returns the tools and a name->risk map."""
    tools: list[BaseTool] = []
    risks: dict[str, Risk] = {}
    for name in names:
        definition = get_tool_definition(name)
        tool = definition.factory(ctx)
        if tool.name != name:
            raise ValueError(f"Factory for '{name}' returned a tool named '{tool.name}'")
        tools.append(tool)
        risks[name] = definition.risk
    return tools, risks
