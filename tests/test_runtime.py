import json

import pytest
from langchain_core.messages import AIMessage

from universal_agent.graph import STEP_LIMIT_REPLY
from universal_agent.runtime import NoPendingApprovalError, PendingApprovalError

from .conftest import tool_call


async def test_plain_reply(make_runtime) -> None:
    rt = make_runtime([AIMessage(content="Hello!")])
    result = await rt.chat("assistant", "t1", "hi")
    assert result.status == "completed" and result.reply == "Hello!"


async def test_read_tool_runs_without_approval(make_runtime) -> None:
    rt = make_runtime([tool_call("calculator", {"expression": "19*3"}), AIMessage(content="It is 57.")])
    result = await rt.chat("assistant", "t1", "19 times 3?")
    assert result.reply == "It is 57."
    history = await rt.history("assistant", "t1")
    assert any(m["role"] == "tool" and m["content"] == "57" for m in history)


async def test_write_tool_waits_then_runs_after_approval(make_runtime, settings) -> None:
    call = tool_call("create_ticket", {"title": "Broken item", "description": "Arrived broken"})
    rt = make_runtime([call, AIMessage(content="Ticket opened.")])
    first = await rt.chat("support", "c1", "my item arrived broken, I want a human")
    assert first.status == "awaiting_approval"
    assert first.pending_tool_calls[0]["name"] == "create_ticket"
    assert first.pending_tool_calls[0]["risk"] == "write"
    tickets = settings.data_dir / "tickets.jsonl"
    assert not tickets.exists()  # nothing happened yet

    with pytest.raises(PendingApprovalError):
        await rt.chat("support", "c1", "hello?")

    done = await rt.resume("support", "c1", approved=True)
    assert done.status == "completed" and done.reply == "Ticket opened."
    saved = [json.loads(line) for line in tickets.read_text().splitlines()]
    assert saved[0]["title"] == "Broken item" and saved[0]["agent"] == "support"


async def test_rejected_write_never_runs(make_runtime, settings) -> None:
    rt = make_runtime([tool_call("create_ticket", {"title": "x", "description": "y"}), AIMessage(content="OK, not opened.")])
    await rt.chat("support", "c2", "open a ticket")
    result = await rt.resume("support", "c2", approved=False, reason="not needed")
    assert result.reply == "OK, not opened."
    assert not (settings.data_dir / "tickets.jsonl").exists()
    history = await rt.history("support", "c2")
    assert any(m["role"] == "tool" and "Rejected by the user" in m["content"] for m in history)


async def test_resume_without_pending(make_runtime) -> None:
    rt = make_runtime()
    await rt.chat("assistant", "t9", "hi")
    with pytest.raises(NoPendingApprovalError):
        await rt.resume("assistant", "t9", approved=True)


async def test_step_limit_stops_loops(make_runtime, settings) -> None:
    loop = [tool_call("current_time", {}, f"c{i}") for i in range(settings.max_steps + 2)]
    result = await make_runtime(loop).chat("assistant", "t1", "loop forever")
    assert result.reply == STEP_LIMIT_REPLY


async def test_threads_are_isolated(make_runtime) -> None:
    rt = make_runtime()
    await rt.chat("assistant", "a", "first thread")
    await rt.chat("assistant", "b", "second thread")
    a = await rt.history("assistant", "a")
    assert all("second" not in m["content"] for m in a)


async def test_tool_error_is_reported_not_raised(make_runtime) -> None:
    rt = make_runtime([tool_call("calculator", {"expression": "1/0"}), AIMessage(content="Cannot divide by zero.")])
    result = await rt.chat("assistant", "t1", "1/0")
    assert result.reply == "Cannot divide by zero."
