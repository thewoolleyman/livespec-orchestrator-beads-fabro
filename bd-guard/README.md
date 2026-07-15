# `bd-guard` — warn-first non-lifecycle `bd` guard (stopgap)

A thin wrapper that fronts every `bd` (beads) invocation on the host and warns
(or, opt-in, blocks) the **explicit** non-lifecycle operations that keep
polluting the fleet's beads tenant with off-lifecycle statuses:

1. `bd update ... --status <S>` where `S` is not a livespec lifecycle status;
2. `bd update ... --claim` (which sets status to `in_progress`);
3. `bd reopen ...` (which sets status back to the non-lifecycle `open`);
4. `bd ready ... --claim` (the advertised "grab work" path, which sets status
   to `in_progress`);
5. `bd defer <id>` (the defer **subcommand**, which sets status to the
   non-lifecycle `deferred`).

Everything else — `create`, `list`, `show`, `close`, `dep`, `config`,
`history`, `--json`, a bare `bd ready` list (or `bd ready --status <x>`
filtering), and every other subcommand/flag — passes through **unchanged**.

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
`status.default` work.

Note the **flag vs subcommand** distinction for defer: `bd update ... --defer
<date>` (the `--defer` **flag**) sets a defer *date*, not a status, so it is
**not** guarded — but the `bd defer <id>` **subcommand** writes
status=`deferred` and **is** guarded (item 5 above), exactly like `bd reopen`.

## Behavior contract

- **Mode** resolved by precedence **`LIVESPEC_BD_GUARD_MODE` env var → host-wide
  mode file → `warn`** (see **Host-wide flip** below), default **`warn`**:
  - `warn` — print a one-line stderr warning naming the violation and the
    correct alternative, then **still exec the real bd** (transparent
    passthrough; nothing breaks). This is the observation phase used to
    enumerate offending callers.
  - `fail` — print the same message as an error and exit non-zero **without**
    execing (block the operation). A `fail`-mode block is **observable in
    telemetry** as `guard.mode=fail` + `guard.warned=1` + `exit_code=3` (see
    **Telemetry**).
  - Any other/unset value is treated as `warn`; the wrapper never blocks unless
    resolved to `fail`, so a misconfiguration cannot brick `bd`.
- **Transparency (load-bearing).** For every passthrough (and warn-mode
  violation) argv is preserved exactly, the real bd's stdin/stdout/stderr +
  exit code are preserved, and warnings go to **stderr only** — stdout is never
  touched, so `--json` stays byte-identical. With telemetry ON (the default),
  bd runs in the **foreground** (TTY + signals preserved) and the span is fired
  **detached and fail-open** afterward, so it can never delay or change bd's
  result; with telemetry `off` the wrapper reverts to a straight `exec`
  passthrough (no fork, no wait). See **Telemetry** below.
- **Locating the real bd.** `LIVESPEC_BD_REAL` if set, else
  `/usr/local/bin/bd-real` (the path the installer relocates the real binary
  to).

Example warnings:

```
livespec bd-guard: 'bd update --status in_progress' is non-lifecycle; use --status active
livespec bd-guard: 'bd update --claim' is non-lifecycle; use --status active
livespec bd-guard: 'bd reopen' is non-lifecycle; use bd update --status <lifecycle> (e.g. backlog)
livespec bd-guard: 'bd ready --claim' is non-lifecycle; use --status active
livespec bd-guard: 'bd defer' is non-lifecycle; use bd update --status <lifecycle> (e.g. backlog)
```

## Telemetry (OTLP `bd.invoke` span — default ON, fail-open)

The guard emits one `bd.invoke` OpenTelemetry span per `bd` invocation to a
local OTLP/HTTP collector, so `bd` usage across the fleet is observable (which
subcommands run, from where, whether the guard warned, exit codes, durations).
This is **on by default** and **fail-open**: the span is fired by a **detached**
helper process *after* bd has already run, so a missing collector, a slow
network, or any emitter error can never delay, alter, or break `bd` — its
stdout/stderr/exit stay byte-identical either way.

A `fail`-mode **block** also emits a span (fired just before the non-zero exit,
so `bd` is never run), which makes enforcement **observable**: a block is
queryable as `guard.mode=fail` + `guard.warned=1` + `exit_code=3`.

- **Enable/disable** via `LIVESPEC_BD_GUARD_OTLP` (default **`on`**). Set
  `LIVESPEC_BD_GUARD_OTLP=off` to revert to a pure `exec` passthrough with zero
  overhead and no emit.
- **Endpoint** via `LIVESPEC_BD_GUARD_OTLP_ENDPOINT`, default
  `http://127.0.0.1:4319/v1/traces` (the local collector, which forwards to
  Honeycomb).
- **Emit helper.** The span is built and POSTed by `bd-guard-emit.py`, a
  stdlib-only (`json`, `os`, `secrets`, `sys`, `time`, `urllib.request`)
  fire-and-forget script that **always exits 0** and never writes to
  stdout/stderr. The guard resolves it as `$(dirname bd)/bd-guard-emit.py` (so
  `install.sh` lays it down beside the wrapper; override with
  `LIVESPEC_BD_GUARD_EMIT`). If `python3` is absent or the helper is missing,
  the guard simply emits nothing.

The `bd.invoke` span (`service.name=bd-guard`) carries these attributes:

| Attribute | Meaning |
|---|---|
| `bd.subcommand` | first non-flag token of argv (e.g. `update`, `list`, `reopen`) |
| `bd.argv` | the full argument vector passed to `bd` |
| `guard.warned` | `true` if the guard flagged a non-lifecycle op on this call |
| `guard.op` | the flagged op summary (`reopen` / `claim` / `status:<value>`), else empty |
| `guard.mode` | the guard mode (`warn` / `fail`) |
| `exit_code` | the real bd's exit code |
| `duration_ms` | wall-clock duration of the bd call |
| `bd.caller.ppid` / `bd.caller.comm` / `bd.caller.cmd` | the calling process (pid, `comm`, cmdline) |
| `bd.cwd` / `bd.repo` | the working directory and its basename |

The span `status` is `OK` for a zero exit and `ERROR` for a nonzero exit.

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

**Observe, then optionally enforce (host-wide flip via the mode file):**

The mode is resolved by precedence **env var → mode file → `warn`**. Prefer the
**mode file** for a host-wide flip: the fleet credential wrapper
(`with-livespec-env.sh`) **scrubs the environment** before `bd` runs, so an
exported `LIVESPEC_BD_GUARD_MODE` never reaches real callers — the file is the
switch that actually takes effect. `install.sh` seeds it to `warn`.

```sh
# warn is the default first rollout — leave it, watch stderr for offenders.
# Once callers are clean, flip the whole host to BLOCK:
echo fail | sudo tee /usr/local/etc/livespec-bd-guard.mode
# ...and revert to observe-only at any time:
echo warn | sudo tee /usr/local/etc/livespec-bd-guard.mode
```

Once flipped to `fail`, a blocked op is **observable in telemetry** (it emits a
`bd.invoke` span BEFORE exiting non-zero): query it as `guard.mode=fail` +
`guard.warned=1` + `exit_code=3`. Overriding the file per-shell is still
possible where the env survives (`LIVESPEC_BD_GUARD_MODE=warn` takes precedence
over a `fail` file), but do not rely on the env var for the host-wide setting —
the credential wrapper strips it.

**Rollback (restore the real bd, remove the guard):**

```sh
sudo bd-guard/rollback.sh
# idempotent: moves /usr/local/bin/bd-real -> /usr/local/bin/bd.
bd --version
# then, if desired, delete this directory entirely:
# rm -rf bd-guard
```

## Tests

Hermetic, no real `bd`, no `/usr/local/bin` mutation:

```sh
just check-bd-guard      # shellcheck (if present) + the hermetic harness
# or directly:
bash bd-guard/test/run-tests.sh
```

The harness points `LIVESPEC_BD_REAL` at a generated stub that records its exact
argv, emits controlled stdout/stderr, and exits with a controlled code, then
asserts warn/fail behavior, exact argv preservation, byte-identical `--json`
passthrough, exit-code passthrough, and every edge argv form (`--status=`, `-s`,
`-s<val>`, `--claim=true|false`, reordered flags, root-level and update-level
`--` terminators, no-args). It also drives `install.sh`/`rollback.sh` end-to-end
against a temporary `BD_GUARD_BIN_DIR` (never `/usr/local/bin`): install relocates
the real bd to `bd-real` and installs the guard **plus `bd-guard-emit.py`**,
rollback restores the original bd byte-identically and removes both `bd-real` and
the emit helper, both are idempotent, and a partial install never relocates the
guard onto `bd-real` (which would exec-loop).

The telemetry section (§9 of the harness) stands up a throwaway stdlib
`http.server` capture on a random loopback port — **never a real collector** —
and asserts: a `bd.invoke` span is emitted with the correct payload shape
(`service.name`, `bd.subcommand`, `guard.warned`, `exit_code`, span status);
that a dead endpoint is fail-open (bd unaffected, returns promptly since the emit
is detached); that `LIVESPEC_BD_GUARD_OTLP=off` emits nothing; and that a nonzero
bd exit code is preserved with telemetry ON while the span reflects it. The rest
of the harness runs with telemetry defaulted OFF so those cases stay pure `exec`
passthroughs and never emit off-box.

Later sections cover the flip-hardening behavior: that `--format json update …
--claim` is **blocked** in `fail` mode (its value is skipped so `update`, not
`json`, is read as the subcommand — the parser bypass is closed) while
`--format json list` still passes through; the host-wide **mode-file** precedence
(env var → file → `warn`, including an env `warn` overriding a `fail` file); and
that a `fail`-mode **block emits a span** (routed to a stub emitter) so
enforcement is observable.

The final sections cover the `ready`/`defer` guards and the mode-file
newline footgun: `bd ready --claim` (and `--claim=true`) is **blocked** in
`fail` mode while a bare `bd ready` list, `bd ready --json`, `bd ready --limit
5`, and — critically — `bd ready --status ready` / `bd ready --status open`
list-filters all **pass through** unblocked (the `ready` phase never scans
`--status`, so no legit list is ever mis-blocked); the `bd defer <id>`
subcommand is **blocked** in `fail` and **warns** in `warn`; and a mode file
containing `fail` with **no trailing newline** still resolves to `fail` and
blocks (proving the `head`/`tr` read does not silently degrade to `warn`).
