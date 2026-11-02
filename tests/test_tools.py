import pytest

from universal_agent.tools import builtin
from universal_agent.tools.builtin import safe_eval, search_folder
from universal_agent.tools.registry import get_tool_definition, register_tool


@pytest.mark.parametrize(("expr", "expected"), [("2+2", 4), ("(1200*0.15)+40", 220), ("-3**2", -9), ("7//2", 3)])
def test_safe_eval_arithmetic(expr: str, expected: float) -> None:
    assert safe_eval(expr) == expected


@pytest.mark.parametrize("expr", ["__import__('os')", "a+1", "2**1000", "'x'*3", "True+1", "1" * 300])
def test_safe_eval_rejects_non_arithmetic(expr: str) -> None:
    with pytest.raises((ValueError, SyntaxError)):
        safe_eval(expr)


def test_search_folder_ranks_and_cites(settings) -> None:
    hits = search_folder(settings.agents_dir / "support" / "knowledge", "how many days to return an item")
    assert hits and hits[0][0] == "returns.md"
    assert "30 days" in hits[0][1]


def test_search_folder_missing_dir(tmp_path) -> None:
    assert search_folder(tmp_path / "nope", "anything") == []


def test_registry_rejects_duplicates() -> None:
    with pytest.raises(ValueError):
        register_tool("calculator", risk="read")(lambda ctx: None)  # type: ignore[arg-type,return-value]


def test_risks_declared() -> None:
    assert get_tool_definition("calculator").risk == "read"
    assert get_tool_definition("create_ticket").risk == "write"
    assert builtin  # module imported -> tools registered
