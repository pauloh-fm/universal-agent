# Security policy

## Supported versions

Security fixes are applied to the latest release on `main`.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private vulnerability reporting: **Security** tab → **Report a vulnerability** on this repository.
Include steps to reproduce, affected version or commit, and impact.

You can expect an acknowledgement within 7 days. We will coordinate a fix and disclosure date with you and credit you
unless you prefer otherwise.

## Scope

In scope: the code in this repository (runtime, approval flow, API, built-in tools, Docker image).
Out of scope: vulnerabilities in model providers, and prompt-injection outcomes that require a tool the template marks
as `write` to be approved by a human (that is the intended control). Bypasses of the approval step are in scope.

See also [docs/security.md](docs/security.md).
