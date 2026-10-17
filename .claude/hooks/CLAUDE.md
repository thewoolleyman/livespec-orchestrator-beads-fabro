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

## The sandbox path guard

Two modules enforcing the `contracts.md` paragraph "The run's working tree
survives the agent." (Scenario 180) for the Claude adapter:

- `livespec_sandbox_path_guard.py` — the PreToolUse entry point and the only
  IO: the environment, the sandbox-root listing, the symlink resolutions, and
  the hook's stdout contract. Registered in `.claude/settings.json` on `Bash`.
- `livespec_sandbox_path_policy.py` — the pure decision: which paths a factory
  run cannot survive losing, which paths an executed destructive segment of a
  shell command would act on, and whether either destroys the other.

It is repo-local rather than plugin-distributed, and the reason is one step on
from the test-first order guard's. The plugin reaches a consuming project
through a PINNED CACHE build, so a hook registered there protects the build it
was released in rather than the tree a run has checked out; this guard has to
travel with that tree. It is also invoked with a bare `python3` and never
through a resolved virtualenv, because a guard that fails to START is a guard
that does not protect.

Scope note, so the next reader does not take it for an omission: the governing
paragraph applies to every ACP adapter whose runtime offers a hook that runs
before each shell command, and the Codex adapter's runtime DOES offer one —
`codex-acp` 0.16.0 embeds codex-rs's `hook_runtime`, whose `PreToolUse` event,
`hooks/hooks.json` registration and per-project `trusted_hash` gate are all
present in the shipped binary. Reaching it needs the Dispatcher to project a
`hooks.json` into the sandbox `$CODEX_HOME`, which no assertion of this
work-item covers. That projection is unbuilt, not refused.

Three properties of the policy an editor must not invert. The protected set is DISCOVERED
from the layout the caller can read rather than configured, because the two
engine layouts put the clone in different places and nothing in the sandbox
announces which. That discovery is also what makes the policy INERT outside a
factory sandbox, which is the governing clause's own scope. And the comparison
includes every directory ABOVE a protected path but nothing below one: `rm -rf
..` from the repository root ends the run, while removing the clone's `.git` or
emptying the whole tree is in-tree and v142 allows it.

## The shared shell reading

`livespec_shell_shape.py` is the one place a Bash command is separated into the
words a shell would EXECUTE and the bytes it would merely carry. Both the
test-first order guard's target extraction and the sandbox path policy read it.
Keep it that way: two copies of this reading would let the two guards disagree
about which half of a command is data, which is the exact distinction both of
them exist to make. (`livespec_footgun_guard.py` still carries its own simpler
regex segmenting; consolidating that is a separate concern.)

