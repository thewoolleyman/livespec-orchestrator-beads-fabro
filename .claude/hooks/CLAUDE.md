# .claude/hooks/

Repo-local hook entry points that run around Claude/plugin setup and local
footgun guards.

Rules:

- Preserve hook process contracts: exit codes and stdout/stderr are part of the
  operator surface.
- Keep host mutation explicit, bounded, and reversible where the hook changes
  files or plugin cache state.
- Do not add product logic here; SHARED behavior belongs under
  `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`. The test-first
  order guard is the worked exception, and the reason it is one is worth
  stating so the next reader does not route it: it imports
  `livespec_dev_tooling`, a DEV dependency, and the shipped plugin package
  must not depend on dev tooling — so that tree cannot host it. It is
  repo-local enforcement, not shared behavior. A hook that could live in the
  package still belongs in the package.
- Do not print secrets.

## The uv hook launcher

`livespec_uv_hook_launcher.py` is not a guard. It is the front door the two
`uv run`-started PreToolUse hook commands in `.claude/settings.json` are
invoked through, and it owns the one decision those guards cannot make for
themselves. `uv run` exits 2 before the interpreter starts when `pyproject.toml`
cannot be parsed, and Claude Code reads a PreToolUse exit status 2 as a deny —
so a manifest left with merge-conflict markers refuses every guarded tool call,
including the ones that would repair it, and no guard's own fail-open boundary
is ever reached. The launcher detects that state ahead of `uv`, allows the call,
and writes one line to stderr naming the manifest and the guard it skipped.
`SPECIFICATION/scenarios.md` "Scenario 194" is the ratified behaviour.

It runs under bare `python3` and imports nothing outside the standard library,
because the project virtualenv is exactly what is unreachable in the state it
exists for. Its two fail directions are opposite, as the guards' are: a manifest
it cannot READ fails toward the guard, which is launched and decides as usual,
since standing a guard down on an unrelated filesystem fault would trade a loud
wedge for a silent loss of enforcement; the hook BOUNDARY fails open, because
trouble inside the launcher must never reach Claude Code as a deny.

## The test-first order guard

Four modules, split by cohesion rather than by size, with only public names
crossing each boundary:

- `livespec_tdd_order_guard.py` — the PreToolUse entry point and the only IO:
  the git reads, the environment, and the hook's stdout contract. Registered
  in `.claude/settings.json` on `Write|Edit|MultiEdit|Bash`.
- `livespec_tdd_order_targets.py` — which paths a tool is about to write,
  from the structured `file_path` and from five shell write forms.
- `livespec_tdd_order_policy.py` — the pure decision table over HEAD state,
  existence at HEAD, and a pending test change.
- `livespec_tdd_order_span.py` — one scrubbed OTLP decision span per verdict.

Two fail directions, and they are deliberately opposite. The DECISION is
fail-CLOSED: an unreadable HEAD refuses rather than admitting a product write
on a repository the guard cannot see. The HOOK is fail-OPEN at its boundary,
because a crashing PreToolUse hook wedges every tool call in the session. The
one sanctioned fail-open inside the decision is the Bash tokenizer, since a
lexer error must not refuse legitimate work.

