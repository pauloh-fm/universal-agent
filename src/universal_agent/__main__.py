"""Command line entry point.

universal-agent serve                 # HTTP API on :8000
universal-agent chat <agent>          # interactive terminal chat
universal-agent agents                # list agents and loading errors
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

from .config import get_settings


def _cmd_agents() -> int:
    from .agents import AgentRegistry

    registry = AgentRegistry.from_directory(get_settings().agents_dir)
    for spec in registry.agents.values():
        print(f"{spec.name:20} {spec.manifest.description}  tools={spec.manifest.tools}")
    for name, error in registry.errors.items():
        print(f"{name:20} ERROR: {error}", file=sys.stderr)
    return 1 if registry.errors else 0


async def _chat(agent: str) -> int:
    from langgraph.checkpoint.memory import InMemorySaver

    from .runtime import AgentRuntime

    runtime = AgentRuntime(get_settings(), checkpointer=InMemorySaver())
    if agent not in runtime.registry.agents:
        print(f"Unknown agent '{agent}'. Available: {sorted(runtime.registry.agents)}", file=sys.stderr)
        return 2
    thread = uuid.uuid4().hex[:8]
    print(f"Chatting with '{agent}' (thread {thread}). Ctrl+D to quit.")
    while True:
        try:
            text = (await asyncio.to_thread(input, "you> ")).strip()
        except EOFError:
            print()
            return 0
        if not text:
            continue
        result = await runtime.chat(agent, thread, text)
        while result.status == "awaiting_approval":
            print("agent wants to run:", json.dumps(result.pending_tool_calls, ensure_ascii=False, indent=2))
            answer = (await asyncio.to_thread(input, "approve? [y/N] ")).strip().lower()
            result = await runtime.resume(agent, thread, approved=answer in {"y", "yes"})
        print(f"{agent}> {result.reply}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="universal-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    chat = sub.add_parser("chat", help="chat with an agent in the terminal")
    chat.add_argument("agent")
    sub.add_parser("agents", help="list agents")
    args = parser.parse_args(argv)

    if args.command == "agents":
        return _cmd_agents()
    if args.command == "chat":
        return asyncio.run(_chat(args.agent))

    import logging

    import uvicorn

    from .api import create_app

    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level=settings.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
