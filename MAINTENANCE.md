# RTHYM-MOC Maintenance Schedule

This project uses a lightweight maintenance cadence so solver quality and
documentation do not drift between feature additions.

## Ongoing

- Triage new bug reports and validation regressions as they arrive.
- Keep behavior-changing pull requests paired with automated tests or updated
  validation/reference documentation (`docs/validation.md`).

## Monthly Review

At least once per month, review the following:

- open issues and pending pull requests
- failing or flaky CI runs
- validation/reference assets and optional TSNet performance notes that may need
  refreshed documentation
- opportunities to simplify recently changed solver or binding code

If a recurring pain point shows up across more than one change, schedule a
small refactor instead of continuing to patch around it locally.

## Pre-release Review

Before each tagged release:

- run the full local validation stack (`pytest -q`, `ruff check rthym_moc`,
  `mypy rthym_moc`)
- review `CHANGELOG.md` and user-facing documentation for scope changes
- confirm new validation tolerances and reference assets are documented in
  `docs/validation.md`
- confirm the C++ extension has been rebuilt if `src/` changed

## Refactor Triggers

Prefer a targeted refactor when any of the following occurs:

- the same bug pattern appears in more than one node/device path
- a public API contract requires repeated test-only workarounds
- a benchmark becomes hard to understand because setup helpers are too implicit
- binding or import logic accumulates special cases that obscure supported scope

The goal is steady maintenance rather than large, infrequent cleanups.