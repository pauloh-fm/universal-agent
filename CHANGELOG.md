# Changelog

All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning: [SemVer](https://semver.org/).

## [0.1.0] - 2026-11-02

### Added

- LangGraph agent loop with step limit and history trimming.
- Human approval for `write` tools via `interrupt`, with approve/reject resume.
- Agents defined as folders (`agent.yaml`, `prompt.md`, `knowledge/`), validated at load.
- Tool registry with risk levels; example tools `calculator`, `current_time`, `search_knowledge`, `create_ticket`.
- OpenAI-compatible model client and offline `ScriptedChatModel`.
- FastAPI HTTP API with optional bearer token; SQLite thread persistence.
- CLI: `serve`, `chat`, `agents`.
- Docker image, compose file, CI workflow, documentation and AI build guide.
