"""Agent specifications loaded from disk.

Layout of one agent (see docs/creating-agents.md)::

    agents/<name>/
        agent.yaml      # metadata + tool list (required)
        prompt.md       # system prompt (required)
        knowledge/      # optional Markdown files for the search_knowledge tool

A broken agent folder never takes the others down: it is skipped and reported in
``AgentRegistry.errors``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from .tools import get_tool_definition

log = logging.getLogger(__name__)

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


class AgentManifest(BaseModel):
    name: str = Field(pattern=NAME_PATTERN.pattern)
    description: str = Field(min_length=1, max_length=300)
    version: str = "0.1.0"
    tools: list[str] = []
    model: str | None = None
    """Optional per-agent model override (same provider as LLM_PROVIDER)."""


@dataclass(frozen=True)
class AgentSpec:
    manifest: AgentManifest
    prompt: str
    directory: Path

    @property
    def name(self) -> str:
        return self.manifest.name


def load_agent(directory: Path) -> AgentSpec:
    manifest_path = directory / "agent.yaml"
    prompt_path = directory / "prompt.md"
    if not manifest_path.is_file():
        raise ValueError("missing agent.yaml")
    if not prompt_path.is_file():
        raise ValueError("missing prompt.md")
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("agent.yaml must be a mapping")
    try:
        manifest = AgentManifest.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid agent.yaml: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}") from exc
    if manifest.name != directory.name:
        raise ValueError(f"name '{manifest.name}' must match folder '{directory.name}'")
    for tool in manifest.tools:
        get_tool_definition(tool)  # raises KeyError with the list of known tools
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError("prompt.md is empty")
    return AgentSpec(manifest=manifest, prompt=prompt, directory=directory)


@dataclass
class AgentRegistry:
    agents: dict[str, AgentSpec] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_directory(cls, root: Path) -> AgentRegistry:
        registry = cls()
        if not root.is_dir():
            log.warning("agents directory %s does not exist", root)
            return registry
        for directory in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            try:
                spec = load_agent(directory)
            except (ValueError, KeyError) as exc:
                registry.errors[directory.name] = str(exc)
                log.error("skipping agent %s: %s", directory.name, exc)
                continue
            registry.agents[spec.name] = spec
        return registry

    def get(self, name: str) -> AgentSpec:
        try:
            return self.agents[name]
        except KeyError:
            raise KeyError(name) from None
