"""High-level runtime: one object the API (or your own code) talks to.

``AgentRuntime`` loads agents from disk, builds one compiled graph per agent lazily,
and exposes two operations:

* :meth:`chat` - send a user message to a thread.
* :meth:`resume` - approve or reject the pending tool calls of a thread.

Both return a :class:`TurnResult`. Threads are persisted by the LangGraph checkpointer,
so conversations survive restarts when SQLite is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from .agents import AgentRegistry, AgentSpec
from .config import Settings
from .graph import build_graph
from .llm import build_chat_model
from .tools import ToolContext, build_tools


@dataclass
class TurnResult:
    status: Literal["completed", "awaiting_approval"]
    reply: str | None = None
    pending_tool_calls: list[dict[str, Any]] = field(default_factory=list)


class AgentRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        checkpointer: Any,
        registry: AgentRegistry | None = None,
        model: BaseChatModel | None = None,
    ) -> None:
        self.settings = settings
        self.checkpointer = checkpointer
        self.registry = registry or AgentRegistry.from_directory(settings.agents_dir)
        self._model = model
        self._graphs: dict[str, Any] = {}

    def _model_for(self, spec: AgentSpec) -> BaseChatModel:
        if self._model is not None:
            return self._model
        if spec.manifest.model:
            return build_chat_model(self.settings.model_copy(update={"llm_model": spec.manifest.model}))
        return build_chat_model(self.settings)

    def graph(self, agent_name: str) -> Any:
        if agent_name not in self._graphs:
            spec = self.registry.get(agent_name)
            ctx = ToolContext(agent_name=spec.name, agent_dir=spec.directory, settings=self.settings)
            tools, risks = build_tools(spec.manifest.tools, ctx)
            self._graphs[agent_name] = build_graph(
                self._model_for(spec),
                tools,
                system_prompt=spec.prompt,
                tool_risks=risks,
                confirm_risks=self.settings.require_confirmation_for,
                max_steps=self.settings.max_steps,
                max_context_messages=self.settings.max_context_messages,
                checkpointer=self.checkpointer,
            )
        return self._graphs[agent_name]

    @staticmethod
    def _config(agent_name: str, thread_id: str) -> dict[str, Any]:
        # Namespacing by agent keeps two agents from sharing a thread by accident.
        return {"configurable": {"thread_id": f"{agent_name}:{thread_id}"}}

    async def chat(self, agent_name: str, thread_id: str, message: str) -> TurnResult:
        graph = self.graph(agent_name)
        config = self._config(agent_name, thread_id)
        if await self.pending(agent_name, thread_id):
            raise PendingApprovalError("This thread is waiting for a tool approval. Resume it first.")
        await graph.ainvoke({"messages": [HumanMessage(content=message)], "steps": 0}, config)
        return await self._result(graph, config)

    async def resume(self, agent_name: str, thread_id: str, *, approved: bool, reason: str = "") -> TurnResult:
        graph = self.graph(agent_name)
        config = self._config(agent_name, thread_id)
        if not await self.pending(agent_name, thread_id):
            raise NoPendingApprovalError("Nothing to approve on this thread.")
        await graph.ainvoke(Command(resume={"approved": approved, "reason": reason}), config)
        return await self._result(graph, config)

    async def pending(self, agent_name: str, thread_id: str) -> list[dict[str, Any]]:
        state = await self.graph(agent_name).aget_state(self._config(agent_name, thread_id))
        calls: list[dict[str, Any]] = []
        for item in state.interrupts:
            if isinstance(item.value, dict):
                calls.extend(item.value.get("tool_calls", []))
        return calls

    async def history(self, agent_name: str, thread_id: str) -> list[dict[str, Any]]:
        state = await self.graph(agent_name).aget_state(self._config(agent_name, thread_id))
        out = []
        for m in state.values.get("messages", []):
            out.append({"role": m.type, "content": m.content if isinstance(m.content, str) else str(m.content)})
        return out

    async def _result(self, graph: Any, config: dict[str, Any]) -> TurnResult:
        state = await graph.aget_state(config)
        if state.interrupts:
            calls = [c for i in state.interrupts if isinstance(i.value, dict) for c in i.value.get("tool_calls", [])]
            return TurnResult(status="awaiting_approval", pending_tool_calls=calls)
        last = state.values["messages"][-1]
        reply = last.content if isinstance(last, AIMessage) and isinstance(last.content, str) else str(last.content)
        return TurnResult(status="completed", reply=reply)


class PendingApprovalError(RuntimeError):
    pass


class NoPendingApprovalError(RuntimeError):
    pass
