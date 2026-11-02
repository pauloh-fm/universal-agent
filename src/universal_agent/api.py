"""HTTP API (FastAPI).

Endpoints (full reference with examples in docs/api.md)::

    GET  /health
    GET  /agents
    POST /agents/{agent}/threads/{thread_id}/messages   {"message": "..."}
    POST /agents/{agent}/threads/{thread_id}/approval   {"approved": true, "reason": ""}
    GET  /agents/{agent}/threads/{thread_id}
"""

from __future__ import annotations

import hmac
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings, get_settings
from .runtime import AgentRuntime, NoPendingApprovalError, PendingApprovalError, TurnResult

THREAD_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def get_runtime(request: Request) -> AgentRuntime:
    return request.app.state.runtime  # type: ignore[no-any-return]


Rt = Annotated[AgentRuntime, Depends(get_runtime)]


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class ApprovalIn(BaseModel):
    approved: bool
    reason: str = Field(default="", max_length=1_000)


def create_app(settings: Settings | None = None, runtime: AgentRuntime | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if runtime is not None:
            app.state.runtime = runtime
            yield
            return
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(settings.data_dir / "checkpoints.sqlite")) as saver:
            app.state.runtime = AgentRuntime(settings, checkpointer=saver)
            yield

    app = FastAPI(title="Universal Agent", version=__version__, lifespan=lifespan)

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.api_token is None:
            return
        expected = f"Bearer {settings.api_token.get_secret_value()}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    def agent_name(runtime: AgentRuntime, name: str) -> str:
        if name not in runtime.registry.agents:
            raise HTTPException(status_code=404, detail=f"Unknown agent '{name}'")
        return name

    def thread(thread_id: str) -> str:
        if not THREAD_ID.match(thread_id):
            raise HTTPException(status_code=422, detail="thread_id must match [A-Za-z0-9_.-]{1,128}")
        return thread_id

    Auth = Depends(require_token)

    def as_json(result: TurnResult) -> dict[str, Any]:
        return {"status": result.status, "reply": result.reply, "pending_tool_calls": result.pending_tool_calls}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/agents", dependencies=[Auth])
    async def list_agents(rt: Rt) -> dict[str, Any]:
        return {
            "agents": [
                {"name": s.name, "description": s.manifest.description, "version": s.manifest.version, "tools": s.manifest.tools}
                for s in rt.registry.agents.values()
            ],
            "errors": rt.registry.errors,
        }

    @app.post("/agents/{agent}/threads/{thread_id}/messages", dependencies=[Auth])
    async def post_message(rt: Rt, body: MessageIn, agent: str, thread_id: str) -> dict[str, Any]:
        try:
            result = await rt.chat(agent_name(rt, agent), thread(thread_id), body.message)
        except PendingApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return as_json(result)

    @app.post("/agents/{agent}/threads/{thread_id}/approval", dependencies=[Auth])
    async def post_approval(rt: Rt, body: ApprovalIn, agent: str, thread_id: str) -> dict[str, Any]:
        try:
            result = await rt.resume(agent_name(rt, agent), thread(thread_id), approved=body.approved, reason=body.reason)
        except NoPendingApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return as_json(result)

    @app.get("/agents/{agent}/threads/{thread_id}", dependencies=[Auth])
    async def get_thread(rt: Rt, agent: str, thread_id: str) -> dict[str, Any]:
        name, tid = agent_name(rt, agent), thread(thread_id)
        return {"messages": await rt.history(name, tid), "pending_tool_calls": await rt.pending(name, tid)}

    return app
