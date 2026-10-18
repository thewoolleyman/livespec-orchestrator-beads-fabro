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

Four properties of the policy an editor must not invert. The protected set is DISCOVERED
from the layout the caller can read rather than configured, because the two
engine layouts put the clone in different places and nothing in the sandbox
announces which. That discovery is also what makes the policy INERT outside a
factory sandbox, which is the governing clause's own scope. And the comparison
includes every directory ABOVE a protected path but nothing below one: `rm -rf
..` from the repository root ends the run, while removing the clone's `.git` or
emptying the whole tree is in-tree and v142 allows it.

The fourth is the only place the guard deliberately NARROWS, and it has a
trap inside it. A DESTINATION — the last operand of `mv` or of a dereferencing
`ln` — destroys nothing when the path is already a directory, because the
moved or linked path is created INSIDE it; the clause says as much, its
refusal condition being unmet by a segment that "removes, moves, or replaces
only paths that are not protected paths". So `mv /tmp/patch.diff .` must run.
The trap is the flag that makes a destination a PLAIN NAME: under it a
symbolic link to a directory is RE-POINTED rather than written through, so
`ln -sfn /tmp/elsewhere <link>` destroys the engine's own working-directory
link while the filesystem reports that link as a directory exactly as an
ordinary destination. No filesystem reading can separate those two, and the
command's own flags can — which is why the destination mark is decided in
`removal_targets`, from the command, and the directory reading arrives
separately at `refused_path`. The SOURCE side is untouched by any of it: `mv
/workspace /tmp/moved-root` moves the root away and is refused.

That trap has TWO flag spellings and they do not share a verb set, which is
the part a reader is most likely to get wrong. `-T` /
`--no-target-directory` is coreutils' "treat DEST as a normal file" and means
that to BOTH `ln` and `mv`; it is `mv`'s only spelling of it, so `mv -T
<file> <link>` leaves a regular file where the link was and the engine's next
checkpoint cannot chdir into its working directory. `-n` is the same reading
for `ln` ALONE, because GNU `mv -n` is `--no-clobber`, a flag whose whole
purpose is to destroy less. `_PLAIN_DESTINATION_FLAGS` therefore pairs each
spelling with its own verbs rather than testing both against one set. The
reading is also case-sensitive on purpose: `-t` is `--target-directory`, a
different flag.

A link an agent makes that points at a protected path is PERMANENT, and
anyone building a simulation here has to plan for it. Resolution is what
stops such a link standing in for the path it points at, and it applies to
the command that would remove the LINK as much as to any other — so once the
link exists, its name can never be reclaimed. The refusal must therefore say
two things a bare victim name cannot: which word the command actually wrote
(`stand_in_targets`, asked over the same three readings as `refused_path` so
the two cannot disagree about a spared destination), and that the name is
gone for good. Measured 2026-10-18 on run 01M577JN5RK7220F6B50PN1227, where
the absence of both cost a proof replay: `rm -f
/tmp/proof-capture/agent-made-link` was refused naming `/workspace`, a path
absent from the command, under a remedy — build the simulation under a
scratch directory — the agent had already followed. **So point every link in
a simulation at a path inside that same simulation, and give the simulation a
name no earlier run has used.** A fixed name makes the block that creates it
one-shot.

## The shared shell reading

`livespec_shell_shape.py` is the one place a Bash command is separated into the
words a shell would EXECUTE and the bytes it would merely carry. Both the
test-first order guard's target extraction and the sandbox path policy read it.
Keep it that way: two copies of this reading would let the two guards disagree
about which half of a command is data, which is the exact distinction both of
them exist to make. (`livespec_footgun_guard.py` still carries its own simpler
regex segmenting; consolidating that is a separate concern.)

