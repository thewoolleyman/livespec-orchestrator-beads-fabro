# Local constraints — W7 live-golden-master greeting skeleton

This is a MINIMAL repo whose sole deliverable is the hello-world greeting
program described in `SPECIFICATION/`. It is intentionally NOT a full
livespec-impl repo. The implement-stage prompt's general family discipline is
overridden HERE for these local specifics (the prompt treats this file as
authoritative for local constraints):

- **No Red-Green-Replay ritual, no commit-refuse hook.** This repo installs a
  benign pass-through git hook. Implement the greeting with a normal test +
  implementation and commit them together in ONE ordinary commit. Do NOT author
  a separate failing "Red" commit; do NOT amend; do NOT look for `TDD-*`
  trailers. A `feat:`-subject commit carrying both the test and the impl is
  correct here.
- **What to build:** expose a Python function `greet(name: str) -> str` that
  returns exactly `Hello, <name>!`. Put it in `src/greeting/greet.py` and export
  it so `from greeting.greet import greet` works (the package is already on the
  path via pyproject). For the input `Ada` it MUST return `Hello, Ada!`.
- **Add a test** under `tests/` (e.g. `tests/test_greet.py`) asserting
  `greet("Ada") == "Hello, Ada!"`.
- **The gate** is `just check` (it runs `uv run pytest -q`). Hand the janitor a
  green tree: run `mise exec -- just check` yourself and make it pass.
- **Commit message:** every commit body MUST end with the trailer line
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (per the
  implement-stage prompt).
- Do NOT touch `.beads/`, do NOT run `bd init`, do NOT modify `SPECIFICATION/`.
