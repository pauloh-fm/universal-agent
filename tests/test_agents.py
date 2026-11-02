from pathlib import Path

from universal_agent.agents import AgentRegistry


def write_agent(root: Path, name: str, yaml_text: str, prompt: str = "You are a test agent.") -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "agent.yaml").write_text(yaml_text, encoding="utf-8")
    (folder / "prompt.md").write_text(prompt, encoding="utf-8")


def test_example_agents_load(settings) -> None:
    registry = AgentRegistry.from_directory(settings.agents_dir)
    assert registry.errors == {}
    assert set(registry.agents) == {"assistant", "support"}


def test_bad_agents_are_skipped_not_fatal(tmp_path: Path) -> None:
    write_agent(tmp_path, "good", "name: good\ndescription: ok\ntools: [calculator]\n")
    write_agent(tmp_path, "unknown-tool", "name: unknown-tool\ndescription: x\ntools: [rm_rf]\n")
    write_agent(tmp_path, "mismatch", "name: other\ndescription: x\n")
    write_agent(tmp_path, "empty-prompt", "name: empty-prompt\ndescription: x\n", prompt="  ")
    write_agent(tmp_path, "bad-yaml", "name: [unclosed\n")
    (tmp_path / "no-files").mkdir()
    registry = AgentRegistry.from_directory(tmp_path)
    assert set(registry.agents) == {"good"}
    assert set(registry.errors) == {"unknown-tool", "mismatch", "empty-prompt", "bad-yaml", "no-files"}
    assert "rm_rf" in registry.errors["unknown-tool"]


def test_missing_root(tmp_path: Path) -> None:
    assert AgentRegistry.from_directory(tmp_path / "absent").agents == {}
