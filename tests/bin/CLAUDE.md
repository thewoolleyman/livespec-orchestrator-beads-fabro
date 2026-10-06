# tests/bin/

Tests for the shebang wrappers under `.claude-plugin/scripts/bin/`.

- `conftest.py` provides the `wrapper_runner` fixture: it
  `runpy.run_path()`'s a wrapper file with a `monkeypatch`-stubbed
  `_bootstrap` (so the runtime version check is a no-op) and a
  stubbed `livespec_orchestrator_beads_fabro.<module>.main` (so the wrapper's
  plumbing is exercised without invoking the real command), then
  asserts the wrapper raises `SystemExit` with the expected exit
  code. It also carries `apply_hermetic_github_app_env` plus an autouse
  fixture that sets NON-SECRET `GITHUB_APP_ID` /
  `GITHUB_PRIVATE_KEY` placeholders for the two credential-coupled
  regressions named in `CREDENTIAL_COUPLED_MODULES`, and ONLY those:
  `bin/dispatcher.py` requires the App env beside the tenant secret, so
  a child driving that real entry point refuses before importing
  anything under test wherever the names are absent. The factory
  projects them; CI does not, which is why those two files passed in
  the factory and failed in CI on their own guard assertions. The
  placeholders ALWAYS win and no ambient value is consulted — the
  applier takes no `environ` parameter, so the rule is enforced by its
  signature. Deferring to an ambient value would leave the two files
  running against a real credential in the factory and a stand-in in
  CI, so the legs would stop measuring the same thing and whichever
  failed would be the one nobody could reproduce. Scope is the measured
  population: with both names unset, exactly these two of all 174
  `tests/bin` tests' files fail, and every other credential-refusal
  test keeps observing a genuinely absent credential.
- `test_hermetic_github_app_env.py` — contract coverage for that
  applier, driven as the total function of a module name and an
  injected `setenv` that it is. Pins the two properties no green run
  reports: that the placeholders always win (the case plants a
  DIFFERENT ambient value first, so an environment-consulting
  regression fails in CI as well as in the factory, not only where the
  names happen to be absent), and that the scope stays exactly the two
  measured modules — a silently widened allowlist would hand another
  refusal test a credential, and it would still pass while no longer
  testing the refusal it exists for. Both mutation controls bite:
  reading `os.environ` fails the first case, adding a third module
  fails the other two. Asserts nothing about `_payload.py` and spawns
  no child — test-support robustness, like the two harness files below.
  NOT a Red, and not evidence for any assertion.
- `test_<cmd>.py` — one per wrapper (`detect_impl_gaps`,
  `list_work_items`, `next`, `orchestrator`). Each
  uses `wrapper_runner` to assert the wrapper threads `main()`'s
  return value into `raise SystemExit(...)`. Required for 100% line
  + branch coverage of the wrappers.
- `test_bootstrap.py` — covers `_bootstrap.bootstrap()`. Both
  branches of the `sys.version_info < (3, 10)` check are exercised
  via `monkeypatch.setattr(sys, "version_info", ...)`; the exit-127
  path is reached by monkeypatching rather than a coverage pragma
  (pragma exclusions on `bin/*.py` are forbidden).
- `test_bootstrap_unattended_marker_forwarding.py` — covers
  `_bootstrap._marker_forwarded_argv`, which splices `env
  LIVESPEC_PLAN_UNATTENDED=<value>` in after the credential wrapper's
  `--` separator so the overseer's unattended-resume marker survives
  the wrapper's `sudo` env rebuild. Its two end-to-end cases drive the
  real re-exec against a wrapper DOUBLE that `unset`s the marker, so a
  forwarding that only worked by environment inheritance fails them.
  Like the file below, the real modules are imported only inside that
  spawned child.
- `test_payload.py` — unit coverage for `_payload.py`, the
  payload-retention step `bootstrap()` runs before any packaged
  import: which plugin roots are harness-managed, that each
  invocation gets a payload no other invocation shares, that no
  pre-existing tree (including a symlink under the launcher's own
  holder prefix) is ever adopted as an executable payload, and how a
  release label degrades when the manifest cannot be read.
- `test_payload_retention_after_eviction.py` — the end-to-end
  counterpart of `test_payload.py`, and the regression guard for the
  `bd-ib-mtuqxb` host incident. It copies the real plugin root into a
  disposable fixture installation, launches a real child through the
  real `bootstrap()`, DELETES that installation once the launcher has
  finished, and only then releases the child to import the packaged
  drive and Dispatcher routes, read a packaged asset and spawn a
  `scripts/bin/` helper. No in-process `main()` can stand in: the
  question is what a second process sees after its own source tree is
  gone. Listed in `subprocess_spawn_allowlist`. Its bytes are FROZEN
  across its Red->Green pair — cover anything it leaves unexercised in
  the harness file below rather than editing it.
- `test_payload_retention_harness.py` — coverage for the frozen
  regression's own scaffolding, which this repo measures like any other
  `tests/` file: `_wait_for`'s early-child-exit and bounded-timeout
  arms, and the test body's `finally` reaping a wedged probe. It loads
  the frozen module BY PATH and drives those arms against real
  disposable children, so the frozen file never has to change. It
  asserts nothing about `_payload.py` — harness robustness, not product
  Red. Listed in `subprocess_spawn_allowlist`.
- `test_payload_concurrent_release_isolation.py` — two concurrent
  invocations launched from two distinguishable installs that carry
  the SAME manifest version, with the older install deleted between
  launch and use. Each must report its own marker from a packaged
  module (deferred code) and from the bundled workflow manifest (a
  packaged asset), which is what forces an invocation-private payload
  rather than one keyed by version text. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_provisioning_refusal.py` — drives the real packaged
  Dispatcher entry point against an incomplete source, and against a
  source whose copy breaks part-way, and observes that the refusal is
  actionable AND that nothing irreversible happened: `bd` and `fabro`
  are replaced on `PATH` by recorders that must never be called, the
  dispatch journal must not exist, and `TMPDIR` must be left empty so
  no partial payload survives for a later invocation to adopt. Listed
  in `subprocess_spawn_allowlist`.
- `test_payload_lifetime_release.py` — both ends of the retention's
  lifetime, with two concurrent children and a grandchild: a helper
  launched from the payload must REUSE it rather than copy the copy, a
  completed invocation must release its private tree, and that cleanup
  must leave a still-parked invocation's payload and the
  harness-managed installation usable (proven by a fresh invocation
  from it afterwards). Listed in `subprocess_spawn_allowlist`.
- `test_payload_candidate_and_credential_boundary.py` — the two things
  retention must NOT change. `plugin_root()` must keep naming the
  INSTALLED tree (so the self-update canary, the minimum-release floor
  and the registered-install currency finding can still see a newer
  build land there) while the bundled workflow manifest nevertheless
  resolves inside the payload; and the credential re-exec must still
  invoke the wrapper AND still run, against a wrapper double that
  evicts the installation and scrubs the payload environment variable
  the way `sudo` does. Listed in `subprocess_spawn_allowlist`.
- `test_payload_public_cli_routes_after_eviction.py` — the two entry
  points `bd-ib-mtuqxb`'s first assertion NAMES, driven as the shipped
  executables an operator actually invokes: `bin/dispatcher.py
  ledger-check` and `bin/drive.py --action impl:<id>`, each with its
  installation evicted mid-invocation through the credential-wrapper
  seam. Side-effect-free by construction (in-memory fake ledger,
  read-only check, nonexistent item). NOT a Red — it was authored after
  the pairs that implement the behaviour; its docstring records the
  control that shows it fails against the pre-fix tree. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_provisioning_interruption.py` — the two literal cases
  the refusal file above does NOT reach, plus the cleanup assertion it
  omits: a source deleted while the real `copytree` walks it, a
  provision INTERRUPTED mid-copy (which arrives as `KeyboardInterrupt`,
  not `OSError`, so an error-enumerating handler never sees it), and an
  incomplete source creating no private directory at all. Each drives
  the real Dispatcher entry point and observes the same zero-claim
  evidence. The disappearance and interruption each need ONE narrow
  control on the product's own seam inside the child, because a
  wall-clock race would pass or fail on load. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_release_provenance.py` — a `plugin.json` that is
  PRESENT but unusable (unreadable, malformed, not an object, no usable
  `version`) must be REFUSED, not degraded to an `unknown-release`
  label and provisioned anyway: the release is the payload's
  provenance, which the minimum-release floor and the build-currency
  findings compare against other builds. Carries its own control — a
  usable release must still provision — so the suite cannot pass
  against a launcher that refuses unconditionally. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_completeness.py` — completeness as USABLE and
  SAME-RELEASE rather than "these paths exist": a required tree present
  but EMPTY, a required path of the wrong FILE TYPE, and a copy that
  landed SHORT of its source (the literal incident — `_dispatcher_cost_wave`,
  a module no fixed list names). Same-release is established by
  comparing the copy against the tree it was made from, which needs no
  file manifest; `cache-manifest.json` cannot serve here, its
  `required_paths` being top-level and omitting `scripts/_vendor` and
  `.fabro/` entirely. Carries its own control. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_provisioning_boundary.py` — the normal boundary: an
  unusable temporary DESTINATION must refuse rather than raise
  (`tempfile` falls back past an unusable `TMPDIR`, so the destination is
  pinned through `tempfile.tempdir`, the seam an embedder sets); a
  path-like release version must never reach the holder's path as path
  SYNTAX; and an installed tree beside a STRANGER's project file must
  still retain — proven by evicting the installation and requiring the
  deferred import to succeed, not by asking the predicate. Its closing
  control keeps this repository's own checkout exempt, so the
  source-checkout, currency and canary policies are preserved. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_parent_reads_asset_after_helper_exit.py` — the real
  LIFETIME ORDERING, supplied natively. NOT a Red: it supplements an
  evidence gap a read-only review raised against cycle 11's accepted
  Red, whose fourth case calls `release_payload(helper)` synchronously
  in ONE process — sufficient for the OWNERSHIP rule it claims, but no
  proof that a parent still reads its assets after a genuine child has
  terminated, because no child ever started. Here a real parent retains
  a payload, its installation is EVICTED, it spawns a real helper
  through the packaged launcher and waits for that helper to EXIT, and
  only then reads an actual packaged asset's content — the bundled
  33KB `workflow.toml` plus the release manifest — before releasing its
  own payload. The ordering is RECORDED as an `events` list the parent
  emits, so the assertion reads the sequence performed rather than
  trusting statement order. The helper's `source_root` is the retained
  PAYLOAD path, the real shape cycle 4 has spawned since the start and
  the case `_payload_serves`'s second clause exists for. Measured
  2026-10-06: 33,521 characters read (33,658 bytes in the source; the
  gap is UTF-8 multibyte decoding, not truncation), and a mutation
  control with an impossible token FAILS, so the asset assertion is
  live. Listed in `subprocess_spawn_allowlist`.
- `test_payload_candidate_root_without_claude_env.py` — the
  candidate-boundary case `test_payload_candidate_and_credential_boundary.py`
  cannot reach, because that file sets `CLAUDE_PLUGIN_ROOT` on every
  child and so only ever exercises the Claude path. Normal Codex
  exports no such variable, and there `plugin_root()` fell through to
  `parents[3]` — which, after retention, is the PAYLOAD. Measured with a
  real child and no `CLAUDE_PLUGIN_ROOT`: both roots reported the same
  payload directory while the installation was named by neither, so the
  candidate root and the execution path collapsed and every currency
  comparison became the running build against itself. The launcher now
  records the installation it copied aside and `plugin_root()` consults
  that record between the harness export and the `__file__` fall-through.
  Carries three controls the fix must not disturb: an exported
  `CLAUDE_PLUGIN_ROOT` still wins, the constructed packaged-asset PATH
  still sits inside the payload (a path assertion — it does not call the
  asset accessor, read an asset, or observe a canary outcome), and this
  project's own checkout still resolves to itself.
  Listed in `subprocess_spawn_allowlist`.
- `test_payload_source_copy_coherence.py` — same-release coherence at the
  PROVISIONING BOUNDARY. The provisioning path graded the copy with a
  post-copy walk of the source comparing SIZES, and two cases get
  through: a member present when the copy STARTED but omitted from the
  copy and then gone from the source before the walk (invisible to a
  live-source walk — the `bd-ib-3ftj` deferred-module shape), and a file
  copied with WRONG BYTES at the SAME LENGTH (invisible to size
  equality). Both measured as provisioning SUCCEEDING with a defective
  payload, through a depth-counted seam on the product's own `copytree`
  (the depth counter is load-bearing: `copytree` recurses through the
  patched name and inner calls return FIRST, so a "first call wins"
  guard mutates a subdirectory and measures nothing). Fixed by taking a
  pre-copy digest inventory and grading the copy against it. Its THIRD
  case is the control that forbids the stronger invented rule: a
  coherent copy whose source is mutated AFTERWARDS must still provision
  carrying its ORIGINAL bytes — a payload surviving later source change
  is the success case, which is why the release is copied aside at all.
  Scope is copy-vs-its-own-source coherence, NOT integrity or
  tamper-resistance.
- `test_payload_canary_decision_leaves_execution.py` — a canary DECISION,
  passing or failing, must not move the running Dispatcher. Cycle 12's
  control asserted where a CONSTRUCTED path sits, and a path is not a
  decision. Drives `canary_verdict` at both exit codes and requires the
  verdicts to differ while `executing_payload_root()` AND the loaded
  module's own resolved `__file__` are both unchanged — two observables,
  because the root is derived from the module, so either alone could
  agree with itself while the module came from elsewhere. NOT a Red:
  measured correct and passing on first write. Observes no update
  applied, no install promoted and no restart; the running Dispatcher is
  read-only about its own artifact by contract.

  **SCOPE, corrected 2026-10-06 — this is a PURE MAPPING control, not
  candidate canary proof.** An earlier revision of this entry called it
  "the half of the fifth assertion that had no evidence", which reads as
  though it discharges that half; it does not, and that phrasing is
  withdrawn. `canary_verdict` is a one-line total function of one
  integer, and this test calls it with the literal constants `0` and `1`,
  so it launches no candidate process, observes no actual candidate
  result, and drives no self-update journal decision — the exit codes it
  maps were written by the test. What it does establish is the
  decision-to-execution relationship, which is real and worth keeping.
  The fifth assertion's candidate-canary leg is discharged only by
  driving the exported `self_update_after_release` boundary with a real
  bounded subprocess and a recording journal; that capture belongs to the
  downstream `proof_capture` node and its independent `proof_verify`
  replay. Full statement, including the two expected journal outcomes:
  `plan/dispatcher-cache-lifetime/research/003-red-provenance-cycles-9-to-11-2026-10-06.md`
  §"CORRECTION, 2026-10-06". No product defect is inferred from this gap.

  **That last sentence was FALSIFIED on 2026-10-06, and the correction is
  the point.** The capture was taken, and the gap was hiding a real defect:
  the canary's subject was the RUNNING build, not the candidate, so a broken
  candidate reported PASS. The entry above is otherwise accurate and stands;
  only "no product defect is inferred" is withdrawn — it described what was
  known before the measurement, and a mapping control was structurally
  incapable of discovering what the measurement found. The regression and
  the fix are the file below; the full account is that research document's
  §"FOLLOW-UP, 2026-10-06".
- `test_payload_canary_subject_is_the_candidate.py` — the candidate canary's
  SUBJECT must be the candidate. The canary launches the candidate by
  pathname and the child inherits the launcher's
  `LIVESPEC_RETAINED_PAYLOAD_ROOT` hand-down, which `retain_payload` adopts
  whenever the selected source equals the holder's recorded source — a PATH
  comparison, so once a newer build has landed at the installation path the
  path still matches and the candidate executes the RUNNING build's code.
  Measured at the exported `self_update_after_release` boundary with a
  candidate broken by removing one module `ledger-check` imports, which still
  passes the launcher's completeness grade so it is a candidate REGRESSION
  rather than an incomplete payload: before the fix, exit 0 and
  `self-update-restart-due` — a restart recommended onto a build that cannot
  start; after, exit 1 with that module's `ModuleNotFoundError` raised from a
  payload at the CANDIDATE's own release, `self-update-kept-last-known-good`
  and a `self-update-canary-failed` alarm. The fix is at the CALL SITE: the
  stage passes an overlay neutralising the hand-down, and the launcher's
  adoption rule is deliberately UNCHANGED, because `_inherited_payload` runs
  before the completeness grade precisely so an evicted-installation child
  still adopts its parent's payload — the child
  `test_payload_public_cli_routes_after_eviction.py` pins. Uses the REAL
  `ShellCommandRunner` behind a recording decorator, because the production
  merge (`{**os.environ, **env}`) is load-bearing: a double that passes `env`
  straight to `Popen` makes the overlay the child's whole environment and
  grades an environment collapse as a canary failure. Carries its own control
  — a HEALTHY candidate at the same newer release must still record
  `self-update-restart-due`, which passed pre-fix too — so the fix cannot be
  satisfied by failing every canary. Listed in `subprocess_spawn_allowlist`.
- `test_payload_inventory_boundaries.py` — the refusal/cleanup/fail-closed
  semantics of the pre-copy inventory's own NEW code, both faults being
  regressions against contracts this module had already established. The
  inventory call landed between the `mkdtemp` that allocates the holder
  and the `try/finally` that removes an unpublished one, so a
  `KeyboardInterrupt` during it leaked a half-built holder nothing could
  later tell from a finished payload; the inventory now runs BEFORE
  `mkdtemp`, beside the release identity, for the same reason that one
  does. And `_digest`'s unreadable sentinel compared EQUAL to itself, so
  a member unreadable on both sides passed as faithful while its actual
  bytes differed — an `UNREADABLE` reading on either side is now a gap.
  Carries a control requiring an ordinary complete source to still
  provision and still release its holder, so neither fix can be
  satisfied by refusing everything or cleaning up unconditionally.
  Records the aiming trap: a nonexistent copy path trips the `is_file`
  arm and reports a gap before `_digest` runs, hiding the branch.
- `test_payload_candidate_provenance_on_reselection.py` — where the two
  cycles above MEET, which neither of their accepted Reds covers.
  Cycle 11 lets an explicitly selected source win over an inherited
  payload, so the right CODE runs; cycle 12 gives `plugin_root()` a
  launcher record, so the CANDIDATE is the installation. But the record
  was published with `setdefault`, a no-op on an inherited key, and the
  checkout arm returns BEFORE the publication line. Measured with
  install A at 7.1.0 inherited: selecting explicit newer B executed
  9.9.9 while the candidate still named A, and selecting this project's
  own checkout executed 5.5.5 with the candidate still naming A — one
  build running while another is named as the installation present, so a
  floor refusal would send the operator to the wrong install. The fix
  separates ADOPTION from SELECTION: an inherited payload returns before
  publication and keeps its parent's record, while a fresh provision and
  a checkout each publish themselves. Two controls guard the half a
  careless fix breaks — an adopted payload keeps the original install's
  candidacy, and a helper whose own `source_root` IS the payload still
  resolves the candidate to the installation, never the payload.
- `test_payload_candidate_provenance_harness.py` — coverage for the frozen
  file above, whose bytes are frozen across its Red-Green pair while this
  repository measures `tests/` like any other tree. Its `_candidate`
  helper has a no-launcher-record arm its four cases cannot reach, every
  one of them resolving from an environment that carries a record. Loads
  the frozen module BY PATH and drives that arm, exactly as
  `test_payload_retention_harness.py` does for the frozen retention
  regression's `_wait_for`. Asserts nothing about `_payload.py` — harness
  robustness, not product Red, and not evidence for any assertion.
- `test_payload_public_route_exact_outcomes.py` — the EXACT-outcome
  counterpart of the file above, which accepts any `int` helper exit code
  and any `failed` envelope and reaches no `.fabro/` asset. Both public
  routes are driven into a committed `dispatcher.minimum_release` floor
  refusal, so one line is at once deferred-import, packaged-asset-CONTENT
  (the release STRING read from the retained `plugin.json`, against a
  DISTINGUISHABLE `7.1.0`) and helper-subprocess evidence. Zero side
  effects are MEASURED: `dispatcher.fabro_bin` is a recorder whose log
  must not exist. Carries an intact-installation read-only control. NOT a
  Red; its docstring records the pre-fix control, where the floor could
  not be evaluated and dispatch PROCEEDED — and notes that the exit code
  was 3 either way, so only the exact text discriminates. Its install
  root is deliberately outside `tmp_path`, because a `.git` at the pytest
  basetemp root makes every `tmp_path` resolve as a checkout and silently
  take the gate's checkout exemption; the fixture asserts the install is
  not a checkout so that cannot recur unnoticed. Listed in
  `subprocess_spawn_allowlist`.
- `test_payload_inherited_source_identity.py` — `PAYLOAD_ROOT_ENV` is
  ordinary inherited environment, so it also reaches a process pointed at
  a DIFFERENT installation on purpose. Adoption was unconditional, so the
  inherited tree won and the explicitly selected release was silently
  ignored (measured: 7.1.0 executing where 9.9.9 was named, and an
  inherited payload displacing this project's own source checkout). The
  payload now carries a holder-level record of the source it was copied
  from, and an inherited tree is reused only when the selected source IS
  that origin or IS the payload itself — the second being how a
  `scripts/bin/` helper spawned from inside the payload names its own
  root. Carries both hand-down cases as controls, so the suite cannot
  pass against a launcher that stops reusing anything.
- `test_payload_grading.py` — structural guard for the `_payload_grading`
  cut, plus the grading cases whose only caller is now across a module
  boundary. NOT a Red: every function in that module was MOVED verbatim
  out of `_payload.py` and is already covered through the names `_payload`
  re-exports. It asserts the module stays cut, that the names which had
  to become PUBLIC to cross the boundary are public while the private
  spellings are gone, and that `IGNORED_NAMES` is one shared constant
  rather than two that could drift.
- `test_host_side_self_contained_import.py` — the end-to-end
  counterpart of `test_bootstrap.py`: it spawns a `-S` (no-site)
  subprocess that runs the real bootstrap and imports the host-side
  dispatcher surface, asserting the path the bootstrap builds
  (`scripts/` + `scripts/_vendor/`, no site-packages) resolves every
  import. It guards plugin self-containment from the flattened cache —
  an unvendored host-side dependency (e.g. `typing_extensions`) trips
  it. The real modules are imported only inside the isolated
  subprocess, never in-process, so the structural rule below holds.

Rules: keep these tests purely structural — they assert the
wrapper's no-logic supervisor shape and exit-code threading, never
the real command behavior (that is covered under
`tests/livespec_orchestrator_beads_fabro/`). Do NOT import the real
`commands`/`migration` `main` into a wrapper test; always stub it.
(`test_host_side_self_contained_import.py` is the one exception that
imports real modules — but only inside an isolated `-S` subprocess,
to verify import *resolution* from the vendored tree, not behavior.)
