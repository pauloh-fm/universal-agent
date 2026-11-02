"""The agent graph: model -> (optional human approval) -> tools -> model ... -> answer.

::

    START -> agent --(no tool calls)--------------------------> END
               |
               +--(only read tools)--> tools --> agent
               |
               +--(any write tool)---> approval --approved--> tools --> agent
                                           |
                                           +--rejected--> agent (told it was rejected)

The ``approval`` node uses LangGraph ``interrupt()``: the run stops, the state is saved
by the checkpointer, and it continues only when the caller resumes the thread with a
decision. This is what makes side effects safe: the model can *propose* a write, but a
human (or a policy) decides.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from .state import AgentState
from .tools import Risk

STEP_LIMIT_REPLY = "I stopped because this request needed too many steps. Please narrow it down."


def trim_history(messages: Sequence[BaseMessage], limit: int) -> list[BaseMessage]:
    """Keep the last ``limit`` messages without starting on an orphan ToolMessage."""
    trimmed = list(messages[-limit:])
    while trimmed and isinstance(trimmed[0], ToolMessage):
        trimmed.pop(0)
    return trimmed


def build_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    *,
    system_prompt: str,
    tool_risks: dict[str, Risk] | None = None,
    confirm_risks: Sequence[Risk] = ("write",),
    max_steps: int = 8,
    max_context_messages: int = 40,
    checkpointer: Any = None,
) -> Any:
    names = [tool.name for tool in tools]
    if len(names) != len(set(names)):
        raise ValueError("Tool names must be unique")
    risks = tool_risks or {}
    bound = model.bind_tools(list(tools)) if tools else model

    async def agent(state: AgentState) -> dict[str, Any]:
        steps = state.get("steps", 0) + 1
        if steps > max_steps:
            return {"steps": steps, "messages": [AIMessage(content=STEP_LIMIT_REPLY)]}
        history = trim_history(state["messages"], max_context_messages)
        response = await bound.ainvoke([SystemMessage(content=system_prompt), *history])
        return {"steps": steps, "messages": [response]}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        if not calls:
            return END
        if any(risks.get(call["name"], "write") in confirm_risks for call in calls):
            return "approval"
        return "tools"

    def approval(state: AgentState) -> Command[Literal["tools", "agent"]]:
        last = state["messages"][-1]
        calls = [
            {"id": c["id"], "name": c["name"], "args": c["args"], "risk": risks.get(c["name"], "write")}
            for c in getattr(last, "tool_calls", [])
        ]
        decision = interrupt({"kind": "tool_approval", "tool_calls": calls})
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        if approved:
            return Command(goto="tools")
        reason = decision.get("reason", "") if isinstance(decision, dict) else ""
        rejected = [
            ToolMessage(
                content=f"Rejected by the user. Do not retry without asking. {reason}".strip(),
                tool_call_id=c["id"],
                name=c["name"],
                status="error",
            )
            for c in calls
        ]
        return Command(goto="agent", update={"messages": rejected})

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent)
    builder.add_edge(START, "agent")
    if tools:
        builder.add_node("tools", ToolNode(list(tools), handle_tool_errors=True))
        builder.add_node("approval", approval)
        builder.add_conditional_edges("agent", route, ["tools", "approval", END])
        builder.add_edge("tools", "agent")
    else:
        builder.add_edge("agent", END)
    return builder.compile(checkpointer=checkpointer)
