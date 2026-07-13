# `bd-guard` — warn-first non-lifecycle `bd` guard (stopgap)

A thin wrapper that fronts every `bd` (beads) invocation on the host and warns
(or, opt-in, blocks) the two **explicit** non-lifecycle operations that keep
polluting the fleet's beads tenant with off-lifecycle statuses:

1. `bd update ... --status <S>` where `S` is not a livespec lifecycle status;
2. `bd update ... --claim` (which sets status to `in_progress`).

Everything else — `create`, `list`, `show`, `close`, `dep`, `config`,
`history`, `--json`, and every other subcommand/flag — passes through
**unchanged**.

This is a **STOPGAP** until beads ships the upstream fixes (a `status.default`
and a lifecycle-aware `--claim`/`--status`). It is designed to be **trivially
removable**: run `rollback.sh` and delete the `bd-guard/` directory.

## The lifecycle statuses (authoritative)

```
backlog  pending-approval  ready  active  acceptance  blocked  closed
```

This set is `ALLOWED_BEADS_STATUSES` in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/_store_statuses.py`,
derived from the `WorkItemStatus` Literal (`done` projected to `closed`). Beads'
native `open` / `in_progress` / `deferred` are non-conformant.

## Out of scope (deliberately)

The bare `bd create` → `open` default is **not** guarded here: it cannot be
cleanly detected at a single-command wrapper on `bd` v1.0.5 (no
`create --status`), so a bare `create` is indistinguishable from a conformant
one. That case is handled elsewhere by the store normalizer plus the upstream
`status.default` work. `--defer` (sets a defer date, not a status) is likewise
not guarded.

## Behavior contract

- **Mode** via `LIVESPEC_BD_GUARD_MODE`, default **`warn`**:
  - `warn` — print a one-line stderr warning naming the violation and the
    correct alternative, then **still exec the real bd** (transparent
    passthrough; nothing breaks). This is the observation phase used to
    enumerate offending callers.
  - `fail` — print the same message as an error and exit non-zero **without**
    execing (block the operation).
  - Any other/unset value is treated as `warn`; the wrapper never blocks unless
    explicitly set to `fail`, so a misconfiguration cannot brick `bd`.
- **Transparency (load-bearing).** For every passthrough (and warn-mode
  violation) argv is preserved exactly and the real bd's stdin/stdout/stderr +
  exit code are preserved via `exec` (no fork, no wait, no added latency).
  Warnings go to **stderr only** — stdout is never touched, so `--json` stays
  byte-identical.
- **Locating the real bd.** `LIVESPEC_BD_REAL` if set, else
  `/usr/local/bin/bd-real` (the path the installer relocates the real binary
  to).

Example warnings:

```
livespec bd-guard: 'bd update --status in_progress' is non-lifecycle; use --status active
livespec bd-guard: 'bd update --claim' is non-lifecycle; use --status active
```

## Install / rollback (host mutation — run by a maintainer, NOT by CI)

The installer and rollback are **delivered but never executed** by the test
suite, CI, or the PR that adds them. A maintainer runs them explicitly. Because
the default mode is `warn`, installing is safe to observe with — the wrapper
does not block anything until you set `LIVESPEC_BD_GUARD_MODE=fail`.

**Install (swap the real bd behind the guard):**

```sh
# from this repo root:
sudo bd-guard/install.sh
# idempotent: moves /usr/local/bin/bd -> /usr/local/bin/bd-real (once),
# installs bd-guard.sh as /usr/local/bin/bd.
bd --version            # confirms passthrough to the real bd still works
```

Optionally point tooling at the wrapper (it already is, since the wrapper IS
`/usr/local/bin/bd`):

```sh
export LIVESPEC_BD_PATH=/usr/local/bin/bd
```

**Observe, then optionally enforce:**

```sh
# warn is the default first rollout — leave it, watch stderr for offenders.
# Once callers are clean, opt in to blocking:
export LIVESPEC_BD_GUARD_MODE=fail
```

**Rollback (restore the real bd, remove the guard):**

```sh
sudo bd-guard/rollback.sh
# idempotent: moves /usr/local/bin/bd-real -> /usr/local/bin/bd.
bd --version
# then, if desired, delete this directory entirely:
# rm -rf bd-guard
```

## Tests

Hermetic, no real `bd`, no host mutation:

```sh
just check-bd-guard      # shellcheck (if present) + the hermetic harness
# or directly:
bash bd-guard/test/run-tests.sh
```

The harness points `LIVESPEC_BD_REAL` at a generated stub that records its exact
argv, emits controlled stdout/stderr, and exits with a controlled code, then
asserts warn/fail behavior, exact argv preservation, byte-identical `--json`
passthrough, exit-code passthrough, and every edge argv form
(`--status=`, `-s`, `-s<val>`, reordered flags, `--` terminator, no-args).
