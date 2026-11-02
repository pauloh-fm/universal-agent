# Security

## Threat model

An LLM agent turns untrusted text (user messages, documents, web pages, tool output) into actions. Assume the model
**can be manipulated** by any text it reads (prompt injection). The template therefore enforces safety outside the model.

| Risk | Mitigation in the template | Your responsibility |
| --- | --- | --- |
| Model triggers an unwanted side effect | `write` tools pause for human approval; unknown tools are treated as `write`. | Mark every side-effecting tool `write`. Show approvers the exact arguments. |
| Tool loops / runaway cost | `MAX_STEPS` per turn; `MAX_CONTEXT_MESSAGES` bounds tokens per call. | Set a spending limit at the provider. |
| Unauthenticated access | Optional bearer token with constant-time comparison. | Set `API_TOKEN`; use HTTPS; do not expose port 8000 directly. |
| Cross-conversation leakage | Threads namespaced by agent; `thread_id` validated. | Derive `thread_id` from your authenticated user, never from client input alone. |
| Code execution through tools | Example calculator parses an AST whitelist, no `eval`. | Never pass model output to `eval`, shells, SQL strings or file paths without validation. |
| Secret leakage | Secrets are `SecretStr`, read from env, `.env` git-ignored. | Do not return secrets from tools; do not log prompts with personal data unless needed. |
| Malformed agent config | Validation at load; bad agents skipped and reported. | Review prompt changes like code. |

## Guidance for tool authors

- Validate arguments as if they came from an attacker: they come from the model, which reads user text.
- Use allow-lists (IDs, enums) instead of free text for anything that selects a resource.
- Scope credentials to the minimum (read-only keys for read tools).
- Make write tools idempotent where possible, or include a confirmation token.
- Treat content fetched from the web or documents as data, never as instructions.

## Reporting vulnerabilities

See [SECURITY.md](../SECURITY.md).
