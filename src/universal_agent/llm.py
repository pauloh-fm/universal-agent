"""Chat model factory.

The runtime only depends on LangChain's ``BaseChatModel`` interface, so adding a new
provider means returning another ``BaseChatModel`` here. Nothing else changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .config import Settings


class ScriptedChatModel(BaseChatModel):
    """Deterministic, offline chat model.

    * With ``script``: returns each scripted ``AIMessage`` in order (used by tests to
      simulate tool calls precisely).
    * Without a script (or after it ends): echoes the last user message, and summarises
      the last tool result when there is one. Good enough for demos and smoke tests.
    """

    script: list[AIMessage] = []
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.cursor < len(self.script):
            message = self.script[self.cursor]
            self.cursor += 1
        else:
            message = AIMessage(content=_echo(messages))
        return ChatResult(generations=[ChatGeneration(message=message)])


def _echo(messages: list[BaseMessage]) -> str:
    if messages and isinstance(messages[-1], ToolMessage):
        return f"Tool result: {messages[-1].content}"
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return f"[fake model] You said: {message.content}"
    return "[fake model] Hello."


def build_chat_model(settings: Settings) -> BaseChatModel:
    if settings.llm_provider == "fake":
        return ScriptedChatModel()

    from langchain_openai import ChatOpenAI

    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else "not-needed"
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )
