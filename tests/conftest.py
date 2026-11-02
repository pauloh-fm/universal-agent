from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from universal_agent.config import Settings
from universal_agent.llm import ScriptedChatModel
from universal_agent.runtime import AgentRuntime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(llm_provider="fake", agents_dir=ROOT / "agents", data_dir=tmp_path / "data", _env_file=None)  # type: ignore[call-arg]


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


@pytest.fixture
def make_runtime(settings: Settings):
    def factory(script: list[AIMessage] | None = None) -> AgentRuntime:
        model = ScriptedChatModel(script=script or [])
        return AgentRuntime(settings, checkpointer=InMemorySaver(), model=model)

    return factory
