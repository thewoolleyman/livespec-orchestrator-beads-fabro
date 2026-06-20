# livespec_impl_beads/

The Python package the shebang wrappers import. This is the
BEADS-backed implementation plugin for livespec; the substrate is a
per-repo beads TENANT DATABASE on the shared `dolt-server` (bd v1.0.5,
server mode), NOT JSONL files. The package name is `livespec_impl_beads`
(NOT `livespec`).

Top-level modules:

- `types.py` — work-item dataclasses, the Spec Reader
  snapshot / diff dataclasses, AND `StoreConfig` (rewritten from the
  plaintext sibling's path pair into the beads CONNECTION descriptor).
  Consumed by every skill and every thin-transport CLI. Dataclasses
  are `kw_only=True`.
- `_beads_client.py` — the backend SEAM. A `BeadsClient` Protocol with
  the verbs the store needs (list / show / children / create / update /
  close / dep-add), and two implementations:
  - `ShellBeadsClient` shells out to the pinned `bd` binary by absolute
    path (NEVER the mise shim) over the §2.1 server-mode FLAGS
    connection and parses `--json` stdout. The single `subprocess.run`
    is `# pragma: no cover`; all argv-construction + JSON-parsing logic
    is pure and covered.
  - `FakeBeadsClient` is a pure in-memory tenant (dict keyed by id) with
    the SAME interface. It is PRODUCT code — the runtime backend when no
    live connection is configured AND the backend the default hermetic
    CI tier runs against — not test scaffolding.
- `store.py` — the public store functions (`read_work_items`,
  `append_work_item`, `materialize_work_items`) — identical signatures
  to the plaintext sibling so the command call sites do not change. The
  `path` keyword is REPURPOSED into the `StoreConfig` connection
  descriptor. `store.py` owns the WorkItem ⇄ beads field map and
  never shells out directly (it talks only to a `BeadsClient`).
- `spec_reader.py` — read-only Spec Reader adapter implementing the
  four required capabilities from `livespec/SPECIFICATION/
  contracts.md` §"Spec Reader required-capability surface". MUST NOT
  mutate the spec tree (§"Spec Reader implementation constraints").
- `errors.py` — the EXPECTED-error exception surface, including the
  beads-specific `BeadsConnectionError` / `BeadsCommandError` /
  `BeadsTenantMissingError` / `BeadsMappingError`.
- `_ids.py` — work-item id generation helpers.

## Backend selection mechanism (Fake vs Shell)

`_beads_client.make_beads_client(*, config)` selects the backend from a
single boolean — `StoreConfig.fake`:

- `fake=True` → a PROCESS-SINGLETON `FakeBeadsClient` (so an
  `append_work_item` followed by a `read_work_items` in the same wrapper
  invocation share one in-memory tenant). Tests reset it with
  `reset_fake_singleton()`.
- `fake=False` → a fresh `ShellBeadsClient` bound to the connection
  descriptor.

`StoreConfig.fake` is resolved by `commands/_config.py` from the
`.livespec.jsonc` `livespec-impl-beads.connection` block, OVERLAID by
the `LIVESPEC_BEADS_FAKE` environment variable (truthy `1`/`true`/`yes`/
`on` forces the fake). The bd binary path comes from the block's
`bd_path`, overridden by `LIVESPEC_BD_PATH`. The default CI tier and the
no-live-connection runtime path set `LIVESPEC_BEADS_FAKE=1`; the opt-in
live tier leaves it false and supplies `BEADS_DOLT_PASSWORD` in the
environment (the password is NEVER a `StoreConfig` field or a config
key).

## Close-via-bd semantics

In the plaintext (JSONL) world a closure was a SECOND appended record
with the same `id` and `status="closed"`. Here that becomes an IN-PLACE
mutation, contained entirely inside `store.py.append_work_item`: when
the incoming item is `status="closed"` and its `id` already exists in
the tenant, the store does `bd close <id> --reason` + `bd update` to add
the `resolution:<enum>` label + write the full `AuditRecord` into the
metadata JSON column (lossless). NO second issue is created. The
command/skill layer is unaffected — it still calls `append_work_item`
with a closed-status WorkItem exactly as the plaintext sibling does.

Module-level rules an agent editing this tree must follow:

- Every module declares `__all__: list[str]` enumerating its public
  surface.
- Records conform exactly to the schema in
  `SPECIFICATION/contracts.md` §"Work-item beads-issue mapping";
  the beads field map (id / type / status /
  priority natives; origin / gap-id / resolution labels; audit in
  metadata JSON; depends_on via `blocks` edges; superseded_by via the
  `supersedes` edge; spec_commitment_hint via native `spec_id`) is
  authoritative in `dev-tooling/implementation/research/
  beads-schema-mapping.md`.
- Domain errors vs bugs: surface EXPECTED errors as the `errors.py`
  exception types (the `Beads*Error` classes for backend failures) and
  catch them at the supervisor (`commands/<cmd>.main()`); raise
  built-in exceptions for bugs and let them propagate.
- No off-substrate persistence: the tenant DB is the single source of
  truth (no sidecar JSON/SQLite, no env-var state beyond the connection
  secret) — per §"Forbidden patterns".
