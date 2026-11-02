"""Built-in example tools. Copy one of these when writing your own (see docs/creating-tools.md)."""

from __future__ import annotations

import ast
import json
import operator
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

from .registry import ToolContext, register_tool

# --- calculator (read) -----------------------------------------------------------------

_OPERATORS: dict[type[ast.AST], Callable[..., float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic without ``eval``: only numbers and + - * / // % ** ( )."""
    if len(expression) > 200:
        raise ValueError("Expression too long")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = _eval(node.left), _eval(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent too large")
            return float(_OPERATORS[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return float(_OPERATORS[type(node.op)](_eval(node.operand)))
        raise ValueError("Only arithmetic is allowed")

    return _eval(ast.parse(expression, mode="eval"))


@register_tool("calculator", risk="read", description="Exact arithmetic.")
def _calculator(ctx: ToolContext) -> BaseTool:
    def calculator(expression: str) -> str:
        """Evaluate an arithmetic expression exactly, e.g. '(1200 * 0.15) + 40'. Use it for any math."""
        try:
            value = safe_eval(expression)
            return str(int(value)) if value.is_integer() else f"{value:.10g}"
        except (ValueError, SyntaxError, ZeroDivisionError) as exc:
            return f"error: {exc}"

    return StructuredTool.from_function(calculator)


# --- current_time (read) ---------------------------------------------------------------


@register_tool("current_time", risk="read", description="Current UTC date and time.")
def _current_time(ctx: ToolContext) -> BaseTool:
    def current_time() -> str:
        """Return the current date and time in UTC (ISO 8601)."""
        return datetime.now(UTC).isoformat(timespec="seconds")

    return StructuredTool.from_function(current_time)


# --- search_knowledge (read) -----------------------------------------------------------

_WORD = re.compile(r"\w+", re.UNICODE)


def _chunks(folder: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in sorted(folder.glob("**/*.md")):
        for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
            if block.strip():
                out.append((path.name, block.strip()))
    return out


def search_folder(folder: Path, query: str, top_k: int = 3) -> list[tuple[str, str]]:
    """Tiny keyword retriever over Markdown paragraphs. Swap for a vector store when you outgrow it."""
    terms = {t.lower() for t in _WORD.findall(query) if len(t) > 2}
    if not terms or not folder.is_dir():
        return []
    scored = []
    for source, text in _chunks(folder):
        words = {w.lower() for w in _WORD.findall(text)}
        score = len(terms & words)
        if score:
            scored.append((score, source, text))
    scored.sort(key=lambda item: -item[0])
    return [(source, text) for _, source, text in scored[:top_k]]


@register_tool("search_knowledge", risk="read", description="Search the agent's knowledge/ folder.")
def _search_knowledge(ctx: ToolContext) -> BaseTool:
    folder = ctx.agent_dir / "knowledge"

    def search_knowledge(query: str) -> str:
        """Search this agent's knowledge base. Always cite the returned [source] when you use it."""
        hits = search_folder(folder, query)
        if not hits:
            return "No matching documents."
        return "\n\n".join(f"[{source}]\n{text}" for source, text in hits)

    return StructuredTool.from_function(search_knowledge)


# --- create_ticket (write) -------------------------------------------------------------


@register_tool("create_ticket", risk="write", description="Create a support ticket (example side effect).")
def _create_ticket(ctx: ToolContext) -> BaseTool:
    outbox = ctx.settings.data_dir / "tickets.jsonl"

    def create_ticket(title: str, description: str, priority: str = "normal") -> str:
        """Create a support ticket for a human team. Priority: low, normal or high."""
        ticket = {
            "id": uuid.uuid4().hex[:8],
            "agent": ctx.agent_name,
            "title": title,
            "description": description,
            "priority": priority if priority in {"low", "normal", "high"} else "normal",
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        outbox.parent.mkdir(parents=True, exist_ok=True)
        with outbox.open("a", encoding="utf-8") as file:
            file.write(json.dumps(ticket, ensure_ascii=False) + "\n")
        return f"Ticket {ticket['id']} created."

    return StructuredTool.from_function(create_ticket)
