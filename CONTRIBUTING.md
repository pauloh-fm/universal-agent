# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Setup

```bash
uv sync
make check
```

## Workflow

1. Open an issue for larger changes so the design can be discussed first.
2. Create a branch, write tests first for behaviour changes, then the code.
3. Run `make check` (ruff, format, mypy strict, pytest). CI runs the same.
4. Update docs in `docs/` when behaviour, configuration or the API changes.
5. Open a pull request using the template.

## Guidelines

- Keep the core small. New integrations usually belong in `docs/extending.md` as a recipe, or as an optional module.
- Tests must run offline. Use `ScriptedChatModel` and fakes; never call paid APIs in the test suite.
- Side-effecting tools must be `risk="write"`.
- No secrets, personal data or real customer data in code, tests, fixtures or examples.
- Commit messages: imperative mood, short subject (`Add Postgres checkpointer recipe`). Conventional Commits welcome.

## License of contributions

By contributing you agree that your contributions are licensed under the [Apache License 2.0](LICENSE), as stated in
section 5 of the license.
