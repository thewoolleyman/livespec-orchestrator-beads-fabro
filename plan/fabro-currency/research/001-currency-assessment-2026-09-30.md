# fabro-currency — currency assessment and seed (2026-09-30)

Written by the `definition-and-proof-of-done` session on 2026-09-30, from
three read-only surveys of the fork checkout at `/data/projects/fabro`,
the upstream repository `fabro-sh/fabro`, this repo's spec and ledger,
and the two factory hosts. Every claim below carries its source; the
ones marked MEASURED were executed in-session, the rest are file reads.

## 1. The maintainer's position, and the ruling this plan corrects

The maintainer's stated intent (2026-09-30): **stay on Fabro, stay
current, and build anything the factory needs on top of it — preferably
by contributing it upstream.**

That intent is what the ratified text already says.
`SPECIFICATION/constraints.md` §"Fabro runtime constraints" (v035) is a
CONDITIONAL ceiling with an explicit exit: "Within that ceiling the base
MAY move forward"; "The prohibition lifts ONLY when the `workflow.fabro`
migration lands … tracked as ledger item `bd-ib-6qu`"; and "When a
carried fix is present in the official upstream release the factory has
moved onto, it MUST be dropped from the branch." Nothing in it says
fork-only, never-modernize, or stable-frozen.

A stronger claim entered the record on 2026-09-06 through the
agent-run backlog sweep `bd-ib-j81s` (whose CHARTER the maintainer ruled
on 2026-09-01, but whose per-item verdicts were the sweep session's own):

- `bd-ib-6qu` was closed with "Modernization past 0.256 is forbidden by
  ratified constraints" — reading the conditional ceiling as a permanent
  ban and closing the very item the spec names as the lift condition.
- `bd-ib-2nq.4` was closed with "Upstream fabro is stable-frozen; fork-only
  posture is ratified in constraints.md" — a phrase that appears nowhere in
  the ratified text.

Both records are also permanently poisoned by a 2026-07-12 comment quoting
a template opener, so neither can carry the correction. AGENTS.md's Host
Fabro server section then inherited the overstatement ("never modernize
the base") and a stale pointer to `bd-ib-6qu` as the live modernization
item. This plan is the clean-text successor; the docs fix is its first
child.

## 2. Upstream state (fabro-sh/fabro)

- **Stable release: still `v0.254.0` (2026-06-04).** `gh release list
  --exclude-pre-releases` shows it as Latest; the 82 tags since are all
  `-nightly.N`. Upstream's own docs say to install and pin nightlies
  (`self-host-docker.mdx`, README).
- **Latest: `v0.371.0-nightly.0`** (2026-09-29, `5879ebf09`), ~1,582
  commits past the pin's merge base `497aaba6f`.
- **Re-platformed 2026-09-17..21.** The workflow engine is now **Petri**
  (`lithoscomputer/petri`, a `branch = "main"` git dependency), the agent
  loop **pebble**, the sandbox layer **sandbox-driver**. `fabro-core`,
  `fabro-validate`, `fabro-acp` and `fabro-sandbox` were DELETED
  (`7eb5ca502`, `a36bea15d`, `d90a5d9cb`, `af38d6894`, `06f9cb836`,
  `60b503322`). The crate tree moved to `lib/apps`, `lib/components`,
  `lib/foundation`. Public docs lag this by weeks: the changelog ends at
  `2026-09-03`, and no doc mentions Petri; the authoritative DOT reference
  is petri's `crates/attractor/FORMAT.md` and `LINTS.md`.
- **Breaking-change cadence:** 17 `<Warning>` breaking notices in the
  changelog between 2026-06-05 and 2026-09-03, plus the un-changelogged
  engine swap. Toolchain is still `nightly-2026-04-14`.

## 3. Fork state (thewoolleyman/fabro)

- **Carrier:** `origin/factory-integration` @ `20bf91e06` (2026-09-12) =
  `v0.254.0` + 24 fork-only commits. The LOCAL `factory-integration` in
  `/data/projects/fabro` is stale at `8de661118` (July).
- **Hosts (MEASURED 2026-09-12, per AGENTS.md):** hp runs build
  `4b8cc85`, vps runs `977cb67`; neither carries S4 (fork PR 9). Deployment
  of S4 is S7 of plan `bd-ib-jxvgq5`.
- **The 24 carried commits, dispositioned against upstream/main**
  (`git cherry -v upstream/main origin/factory-integration`: all 24 `+`):
  - 2 landed upstream and were then deleted with the engine (#568 push
    credential refresh → superseded by #763/#764/`370a6c96d`; #552
    checkpoint `commit_timeout` → accepted-for-compatibility no-op, hooks
    never run on checkpoints now).
  - ~3 partially superseded (cewr.4 ls-remote precondition: upstream
    `011876edd` asks origin only when the tracking ref already matches, so
    the fleet's stale-tracking-ref case is still broken upstream; bb41.2
    docker `init`; js4t57 refuse staging after failed push).
  - 16 obsolete because their host crates no longer exist (Waves A/B/C
    ACP session fixes, timeout evidence, per-tool events, permission
    policy, backgrounded-command containment, checkpoint-budget
    classifier).
  - 6 still needed and fork-only: the OTLP telemetry spine (PR #576 +
    O1/O2/P2/O4, five commits) and the daemon-readiness timeout
    (`FABRO_SERVER_START_READY_TIMEOUT_SECS`).
  - **Three capabilities the fleet relies on have NO upstream equivalent:**
    the S4 `acp.fallback_chain` (now an `attractor.unknown_attribute`
    error; "ACP agents have no plan: the command owns their model"),
    run identity in script nodes (`FABRO_RUN_ID`; Petri offers
    `stdin_source="context.internal.run_id"` instead), and OTLP export.
- **Fork PR #2 (`2c9608653`, "redact environment secrets from inspect",
  2026-08-03) is on the fork's `main`, NOT on the carrier** (MEASURED:
  `git branch -r --contains` → `origin/main` only). Consequence, MEASURED
  2026-09-30 on hp run `01M058955QQ5`: `fabro inspect --server hp` returns
  the projected `CLAUDE_CODE_OAUTH_TOKEN` value in full (108 chars, OAuth
  token shape), zero `REDACTED` markers. On the new engine this fix is not
  separately needed — secrets are `secrets.NAME` tokens resolved in the
  worker and never persisted — so the remedy is currency, not a backport.

### Fork cruft inventory (MEASURED 2026-09-30, `git for-each-ref` on origin)

- 12 merged feature branches still on `origin`: `fix/cewr4-compare-not-push`,
  `factory-wave-c`, `fix/classify-provider-spend-limit-not-transient`,
  `p2-fabro-log-decouple`, `worker-otel-reinject`, `otlp-span-export`,
  `push-credential-refresh-ahead`, `feat/configurable-checkpoint-commit-timeout`,
  `add-patch-cves-workflow`, and the fork's `main` (which diverges from
  the carrier only by PR #2).
- ~20 `fabro/run/<id>` and `fabro/meta/<id>` run-artifact branches from
  2026-06-04..07-02 (Fabro's own run branches from early dogfooding).
- Stale local branches in `/data/projects/fabro`: `trial/factory-rebase`,
  `fork-0254-backport`, `fork-selfhost`, `clone-creds-pull-requests-scope`,
  `factory-wave-b`, `factory-wave-c`, plus the July-stale local
  `factory-integration` and `main`.
- Upstream PRs by the maintainer: **#576 OPEN** (OTLP/HTTP export,
  2026-07-14), **#688 OPEN** (spend-limit not transient, 2026-07-30),
  #568 and #552 merged. Upstream issue **#553 OPEN** (ACP workflow tests
  time out under CI nextest); #508 closed.

## 4. Open fork-side ledger items (this tenant, MEASURED 2026-09-30)

- `bd-ib-afcn3d` READY P2 (filed 2026-09-30): Fabro-owned in-protocol
  model and effort selection for chain candidates — hand-built in the
  fork, builds on S4. Spec commitment `acp-candidate-config-options-fabro`
  (v112). **On the new engine `acp.fallback_chain` does not exist**, so this
  item's design premise must be re-examined before it is built.
- `bd-ib-jxvgq5` plan (factory-configurable-model-fallback-priority):
  S1–S4 landed, S5/S6 drafted 2026-09-30, S7 = deploy to both hosts.
- `bd-ib-2nq` P1 epic (token-TTL fix; record poisoned): "pending
  production rollout"; its remaining children need a currency-era answer
  (upstream now has a cached installation-token source and push retries).
- `bd-ib-j9x` P3: mechanically enforce the `<0.256` ceiling at preflight —
  becomes "enforce the ratified currency window" under this plan.
- `bd-ib-z13s` P2: `run_turn` span never lands for dispatched items (OTLP
  spine).
- `bd-ib-e5xyq2` pending-approval: vps `fabro-server.service` drifted from
  the template (fabro-hosts repo).
- `bd-ib-opvf7x` blocked: run cancel unattributable (shared dev token).
- `livespec-impl-beads-zsl` blocked: UI render bug #508 (closed upstream;
  verify on the new build).
- Plans that touch the credential channel and would consume currency:
  `fabro-token-refresh` (`bd-ib-2nq`), `credential-freshness-redesign`
  (`bd-ib-plhtmx`), `llm-provider-manager-consumer` (`bd-ib-pyr5ys`).
- The proof-of-done plan (to be opened separately) sequences its
  credential slice AFTER this plan lands native secrets projection.

## 5. Migration cost assessment (from the 2026-09-30 upstream survey)

**Effort class: weeks, not days — 3–6 focused weeks. It is a
re-platforming, not a re-pin.**

What must change in this repo:

- `workflow.fabro`: five templated `acp.command` attributes become literal
  `acp.config` JSON with env maps (both #474's de-templating and Petri's
  loss of leading `KEY=value` peeling force it — Petri shlex-splits, so
  `ANTHROPIC_MODEL=… npx …` fails with program `ANTHROPIC_MODEL=…`);
  three `inputs.*` tokens inside edge conditions become literals (a
  templated `outcome=` is an `unsupported.outcome_value` load error);
  `needs_human` moves from `FABRO_RUN_ID` to `stdin_source`; every
  attribute Fabro does not define is now an `attractor.unknown_attribute`
  ERROR except the `x.` namespace.
- Credential channel: from the overlay's literal env table to
  `fabro secret set` + `secrets.NAME` tokens plus a server-managed
  environment (workflow versions are now immutable and server-stored, so
  literal values in the bundle would persist server-side).
- The port (`_fabro_port*.py`): Petri's `inspect` has no `causes`, no
  `signature`, never `transient_infra`; `events --json` is Petri's stream;
  `validate` uses Petri codes; stderr sentinels arrive via
  `conclusion.failure.detail.message` (re-validate `NEEDS_HUMAN_MARKER`
  matching).
- Dispatcher adapter layers (`_acp_node_layers`, `dispatcher.acp_nodes`,
  `codex_models`) re-based onto literal `acp.config` rendering.
- Both hosts re-pinned to an exact nightly tag, mandatory `fabro auth
  login`, one-way SQLite migrations, image rebuilds.

**Semantic gaps that MUST be measured on a real build before design is
frozen** (docs cannot settle them):

1. `context.internal.node_visit_count` — no Petri source populating it was
   found; both loop caps (janitor→fix `< 3`, review cap) depend on it.
2. Docker `resources.cpu/memory` are dropped from bundle environments.
3. `acp.config` `StdioConfig` is `deny_unknown_fields` (`command`/`args`/
   `env` only); fabro's stale `agents.mdx` shows keys Petri rejects.
4. Janitor `script` token quoting: Petri says "one shell-quoted word",
   fabro's 2026-07-27 change says "verbatim".
5. codex-acp is not among Petri's tested ACP products.

**Top 3 risks:** (1) the semantic gaps above; (2) permanent loss of fork
control-plane behaviour (S4 failover, script-node run id, OTLP export, ACP
timeout evidence, backgrounded-process containment) unless re-implemented
Dispatcher-side or contributed to petri/fabro; (3) nightly-only cadence
with weekly breaking notices and docs lagging the engine — any pin is a
moving target.

## 6. Proposed shape (for the scoping event; not yet cut)

Phases, in order, per the maintainer's direction that cleanup comes first
and every open PR / fork item is addressed:

- **P0 — Fork hygiene.** Delete merged feature branches and the
  `fabro/run|meta/*` artifact branches on `origin`; prune stale local
  branches; fast-forward local `factory-integration` and `main`; decide the
  fate of fork `main` (retire, or make it track upstream/main). Record the
  before/after ref lists.
- **P1 — Wrap the open upstream work.** #576: rebase onto the Petri-era
  tree or re-propose; #688: rebase or close with reason; issue #553:
  re-test on current nightly, close or update. Each carried fork commit
  gets a written disposition (upstream PR / re-propose as petri feature /
  drop) — the "every carried fix has an upstream PR or a filed reason"
  rule.
- **P2 — Ratify the currency obligation** (`propose-change`): replace the
  `<0.256` ceiling with a currency window (maximum staleness, exact-tag
  nightly pins, carried-fix disposition rule, `bd-ib-j9x` as the
  mechanical gate), and repoint the `bd-ib-6qu` reference.
- **P3 — Measure the semantic gaps** on a candidate build (a second server
  instance; the Enemy Unit Test suite of `bd-ib-i3zhgk` is the instrument).
- **P4 — Migrate** `workflow.fabro`, the credential channel, the port and
  the adapter layers, behind the seam-equivalence and graph-validity gates.
- **P5 — Contribute** what the factory still needs: OTLP export, script-node
  run identity, cross-candidate ACP failover (re-proposed for petri), daemon
  readiness; re-examine `bd-ib-afcn3d` against the new engine before
  building it.
- **P6 — Re-pin both hosts** on the normal path (fabro-hosts unit,
  rollback artifact, image rebuild, runbook lockstep), then drop every
  carried fix upstream now has.

Dependencies on other plans: `bd-ib-jxvgq5` S7 (deploy S4) is overtaken
if P4–P6 land first — decide at the scoping event whether S7 still ships
on 0.254 or is folded here. The proof-of-done plan consumes P4's secrets
projection.
