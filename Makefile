.PHONY: install test lint fmt typecheck check serve chat

install:   ## Install dependencies (incl. dev)
	uv sync --all-extras

test:      ## Run the test suite (offline, no API key)
	uv run pytest -q

lint:      ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

fmt:       ## Auto-format and fix lint
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Static types (mypy strict)
	uv run mypy src

check: lint typecheck test ## Everything CI runs

serve:     ## HTTP API on http://127.0.0.1:8000
	uv run universal-agent serve

chat:      ## Terminal chat with the example assistant
	uv run universal-agent chat assistant
