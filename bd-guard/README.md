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

Separately, it **normalizes** every qualifying `bd create` (see **Create
normalization** below) to the lifecycle status `backlog`.

Everything else — `list`, `show`, `close`, `dep`, `config`, `history`, `--json`,
a bare `bd ready` list (or `bd ready --status <x>` filtering), and every other
subcommand/flag — passes through **unchanged**.

This is a **STOPGAP** until beads ships the upstream fixes (a `status.default`
and a lifecycle-aware `--claim`/`--status`). It is designed to be **trivially
removable**: run `rollback.sh` and delete the `bd-guard/` directory.

## Create normalization (the sixth channel)

Unlike the five warn/block channels above, this one **rewrites state**: it is a
silent normalization, not a warning. beads v1.0.5 `bd create` **hardcodes**
status `open` (a non-lifecycle status) — there is no `create --status` flag and
no default-status config on v1.0.5 — so every plain create mints an `open` item.
That was the last raw drift channel.

The guard closes it with a **two-step**: it runs the real create, captures the
new id, then (fail-open) issues `bd update <new-id> --status backlog`. A create
is **qualifying** when the subcommand is `create` / `new` / `q` (quick-capture)
**and** it is none of these exclusions:

- `--type event` (audit **event** beads, not work items);
- `--ephemeral` (incl. `--ephemeral=true`; an explicit `--ephemeral=false` still
  creates a real item, so it is still forced);
- `--dry-run` (nothing is created; incl. `--dry-run=true`, same false-value rule);
- `--help` / `-h` (prints help and creates nothing — its help **text** carries
  example ids like `bd-20` that must never be mistaken for a new id);
- a **batch** create (`--file` / `-f` / `--graph`, incl. clustered `-fFILE`) — a
  batch mints **many** ids; forcing a single id is not meaningful, so batch is
  **skipped in this first cut** and left to the store normalizer (documented here
  and in the wrapper, not a silent gap);
- a **tenant / db selector** (`-C` / `--directory` / `--db` / `--global` /
  `--repo`, incl. `=`-forms and clustered `-Cdir`) — detected **whether it
  appears before OR after the subcommand** (bd is cobra: persistent flags are
  valid in both positions, as `bd create … --json` shows). The create mints in
  one tenant/db while the **flag-less** follow-up `update` would target another,
  so forcing would strand the new item `open` or (worse) mutate a same-id item in
  the **wrong** tenant. Such creates pass through unforced (they land `open` and
  the store normalizer catches them). We deliberately do **not** try to propagate
  the selector onto `update` — exclusion is the safe fix. (`--global=false` is
  not a selector, so it does not exclude.);
- a create already carrying a lifecycle `--status <s>` — future-proofing for when
  beads ships create-time `--status`: a lifecycle value is **respected**, a
  non-lifecycle value is still normalized to `backlog`.

The forcing is **fail-open**: if the follow-up `update` fails, the create's own
exit code and output are untouched, and a stranded `open` is caught by the store
normalizer. A create is **never blocked** (even in `fail` mode) — only
normalized. The follow-up is emitted only when the real create **succeeds**
(exit 0). The create's stdout is **replayed only after** the follow-up update
returns, so a consumer that reads the id (e.g. `id=$(bd create --silent)`) and
immediately updates the item cannot race the guard's own backlog update.
Telemetry records the normalization as `guard.op=create-forced-backlog` (with
`guard.warned=false`, since a create is not a violation).

**id extraction is form-anchored, never first-token-anywhere.** beads v1.0.5's
legacy `--json` (the **default** when `BD_JSON_ENVELOPE` is unset) re-marshals
the issue through a map with **alphabetically-sorted keys**, so `assignee` /
`created_by` / `description` / `external_ref` all precede `"id"`. A naive
first-hyphenated-token grep would then grab a **real** id embedded in e.g.
`--description "Discovered from bd-ib-9x9x9x"` and demote the wrong item while
stranding the new one. So the extractor anchors on the output **form**, in order:

1. stdout starts with `{` → the **first** `"id": "<v>"` field (safe in both JSON
   modes — envelope has id first in `data`, legacy sorts metadata after id, and
   JSON escaping guarantees no literal `"id":` inside a string value);
2. else a line containing `Created issue: ` → the token immediately **after** it;
3. else the whole trimmed output is a single id token → use it (`--silent` / `q`);
4. else extract **nothing** and skip the follow-up (the normalizer catches it).

The candidate is then validated against the beads id shape
(`^[a-z][a-z0-9]*(-[a-z0-9]+)+$`); anything else yields empty (fail-safe).

## The lifecycle statuses (authoritative)

```
backlog  pending-approval  ready  active  acceptance  blocked  closed
```

This set is `ALLOWED_BEADS_STATUSES` in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/_store_statuses.py`,
derived from the `WorkItemStatus` Literal (`done` projected to `closed`). Beads'
native `open` / `in_progress` / `deferred` are non-conformant.

## Out of scope (deliberately)

The bare `bd create` → `open` default is **no longer** out of scope: it is now
**normalized** to `backlog` (see **Create normalization** above). The creates
that remain unforced are the documented exclusions listed there — **batch**
creates (`--file` / `-f` / `--graph`, a batch mints many ids, left to the store
normalizer) and creates carrying a **tenant/db selector** (`-C` / `--directory` /
`--db` / `--global` / `--repo`, where a flag-less follow-up `update` would hit the
wrong tenant).

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

The `ready`/`defer` guards and the mode-file newline footgun: `bd ready --claim`
(and `--claim=true`) is **blocked** in `fail` mode while a bare `bd ready` list,
`bd ready --json`, `bd ready --limit 5`, and — critically — `bd ready --status
ready` / `bd ready --status open` list-filters all **pass through** unblocked
(the `ready` phase never scans `--status`, so no legit list is ever mis-blocked);
the `bd defer <id>` subcommand is **blocked** in `fail` and **warns** in `warn`;
and a mode file containing `fail` with **no trailing newline** still resolves to
`fail` and blocks (proving the `head`/`tr` read does not silently degrade to
`warn`).

The **create-normalization** section (§15) uses a stub that appends every
invocation to a call log (`FAKE_BD_LOG`), so the two-step (real create, then the
guard's follow-up `update <id> --status backlog`) is asserted directly. It
proves: a qualifying `create` triggers the follow-up with the id the create
emitted (id extraction covers hyphenated prefixes and the human `✓ Created
issue: <id> — <title>` form even with a hyphenated title); the create's stdout +
exit code are preserved; `--type event`, `--ephemeral`, `--dry-run`, `--file`,
`--graph`, and an existing lifecycle `--status` are **not** forced (a
non-lifecycle `--status` still is); a failed follow-up `update` is **fail-open**
(the create's exit stays 0); a failed create is not forced; `bd q` and `bd new`
are normalized while `bd q --type event` is excluded; and a `--title` value of
`--ephemeral` is not misread as the flag.

The **hardening** section (§16, from a beads-v1.0.5-source adversarial review)
proves the two deploy-blocker fixes and the remaining edge forms: a legacy
`--json` create whose `--description` carries a real-looking id **before** the
sorted `"id"` field → the follow-up targets the **new** id, not the description's
(form-anchored extraction); an envelope-`--json` (id-first) fixture; `bd create
--help` → **no** follow-up (help text carries example ids); `--ephemeral=true` /
`--dry-run=true` excluded while `--dry-run=false` is still forced; clustered
`-fplan.md` batch not forced; `-C <dir>` / `--db <path>` / `--global` / `--repo`
(and clustered `-Cdir`) creates excluded (wrong-tenant); and a `--silent`
single-id create still forced.
