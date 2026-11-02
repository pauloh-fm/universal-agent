# Changelog

All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning: [SemVer](https://semver.org/).

## [0.2.0] - 2026-11-02

### Added

- `clinic-example` agent: appointment scheduling with opening hours, holidays, minimum notice, booking window and
  double-booking protection; tools `clinic_info`, `find_available_slots`, `book_appointment`, `find_my_appointments`,
  `cancel_appointment`.
- Optional Google Calendar backend (`uv sync --extra google`, `CALENDAR_BACKEND=google`) and integration guide.
- `ecommerce-example` agent: tools `search_products`, `get_order_status`, `create_order`, `cancel_order`.
- `docs/examples.md`.

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
