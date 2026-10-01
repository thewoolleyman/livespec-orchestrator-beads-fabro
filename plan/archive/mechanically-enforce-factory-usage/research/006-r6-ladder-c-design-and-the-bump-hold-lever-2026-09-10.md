# R6 (ladder C) design, and the auto-bump lever grounded in the shared composite (2026-09-10)

Written while the line is stopped on the factory credential (research note 005's
successor entries on the epic timeline carry that incident). Neither piece below
needs the factory: R6 has had no child filed since the scope event, and R2's
first deliverable, the consumer-side auto-bump lever, needed a design the
maintainer can rule on in one reading. Every `file:line` and count was read
from the live repositories and the forge on 2026-09-10 between 19:20Z and
19:45Z.

## 1. R6: the population the wall would gate

Last 100 merged pull requests on this repository, classed by author and by
whether the diff touches product Python (a `.py` under `.claude-plugin/scripts/`
outside a tests directory, the same scope Red-Green-Replay and R1 use):

| Author | Touches product Python | Count |
|---|---|---|
| factory App (`app/thewoolleyman-factory-bot`) | no | 54 |
| maintainer (`thewoolleyman`) | no | 28 |
| factory App | yes | 15 |
| maintainer | yes | 3 |

The three maintainer-authored product PRs are #2331, #2384 and #2403. One of
them, #2403, closed `bd-ib-4132` with the comment "LANDED by hand (not
factory)". Those three are the whole bypass set the wall exists for; the 28
maintainer PRs with no product Python (spec, plan, docs, workflows, config) are
out of scope by construction, exactly as R1's hook scope is. Release-please and
bump PRs are App-authored and carry no product Python, so they need no
exemption rule of their own.

## 2. R6 design

**What it is.** A required status check that FAILS a pull request when all
three hold: the diff touches product Python; the PR author is not the factory
App; and the PR carries no `factory-override` label. Everything else passes.
The App identity comes from the forge, so no local marker can forge it; that is
what makes this the hard wall while R1's trailer stays spoofable-but-audited.

**Where the identity is already gated.** `auto-enable-merge.yml:72-74` already
composes a login gate (`thewoolleyman` allowlist, or
`thewoolleyman-factory-bot[bot]` on a `release-please--` branch). R6 reuses the
same two spellings: the webhook payload says `thewoolleyman-factory-bot[bot]`,
`gh` says `app/thewoolleyman-factory-bot`.

**How it becomes required without touching branch protection.** Master's
protection requires exactly one context, `ci-green` (`enforce_admins: true`,
`strict: false`). `ci-green` is an aggregate job (`ci.yml:977-984`) that fails
when any of its `needs` fails or is cancelled. Adding the R6 job to that
`needs` list makes it required for every merge, admins included, with no
settings change.

**Two children, split by who may land them.**

- **R6a, factory-safe.** A check module in this repository's product tree that
  reads the Actions event payload (`GITHUB_EVENT_PATH`: PR author login, label
  names) plus the changed-file list, applies the three-part rule with the
  product-Python scope taken from `config.derive_source_prefixes`, and exits
  non-zero with a message naming the author, the product files, and the two
  routes out (dispatch through the factory, or apply `factory-override` with a
  reason in the PR body). Unit tests cover the eight author/label/scope
  combinations, both login spellings, and a revert PR.
- **R6b, maintainer-landed.** The `ci.yml` job that runs R6a on `pull_request`
  and its entry in `ci-green`'s `needs`, plus creating the `factory-override`
  label. Factory branches never create or update files under
  `.github/workflows/` (the run goal says so and the sandbox janitor enforces
  it), so this half is a workflow edit the maintainer lands by hand. It is
  filed as a child so the archive gate sees it, held at backlog with a rider
  saying why it is not dispatched.

**What R6 deliberately does not do.** It does not read the ledger (hermetic in
the forge sense: event payload and diff only). It does not gate spec, plan, or
workflow changes. It does not replace R1: a hand-crank is refused at commit
time in warn or fail mode by R1 and at merge time by R6, and the two evidence
trails (the `Factory-Override` trailer, the `factory-override` label) are read
by R3's counter as recorded exceptions. Fleet propagation through the copier
template is deferred with D3 until this repository proves the shape.

## 3. The auto-bump lever, grounded

Research note 005 §2 listed three levers and recommended "a dev-tooling-side
`no_auto_merge` switch". Reading the shared machinery makes that concrete and
smaller than it sounded:

- **Both bump paths already share one composite with the switch built in.**
  `reusable-bump-pin-from-dispatch.yml:216` and `reusable-pin-freshness.yml:371`
  both call `./.livespec-dev-tooling/.github/actions/bump-pin-rewrite`, whose
  `no_auto_merge` input (`action.yml:95-103`) opens the PR without `--auto
  --rebase` when `'true'` (`action.yml:677-681`). The sweep already sets it per
  target for one source, `codex-acp` (`reusable-pin-freshness.yml:189-203, 384`).
- **Consumers run that composite at dev-tooling MASTER, not at their pin.** The
  "Checkout livespec-dev-tooling support modules" step in both reusable
  workflows names the repository and path and NO `ref`
  (`reusable-bump-pin-from-dispatch.yml:148-153`,
  `reusable-pin-freshness.yml:316-321`), so `actions/checkout` takes the default
  branch. A change to the composite on dev-tooling master is live in every
  consumer's next bump run, whatever tag its shim pins.

So the lever is a **hold file committed on dev-tooling master**, read by the
composite: when the source and tag being bumped match an entry, the composite
sets `no_auto_merge` for that PR. Properties: single repository; a diff a
reviewer can see; reversible by a second PR; reaches all ten consumers at once
with no shim edit and no copier re-sync; no secret and no host mutation; and
scoped to the one release that carries R1a, so every other dev-tooling release
keeps auto-merging. The staged rollout then reads: land R1a, cut the release,
let the fan-out open held bump PRs everywhere, and merge each one deliberately
paired with `just install-commit-refuse-hooks` on that primary.

The alternatives are recorded so the ruling does not re-derive them: holding
the release PR with `do-not-merge` (`auto-enable-merge.yml` never re-evaluates
on `labeled`, so it also needs `gh pr merge --disable-auto`) holds every fix in
that release, not just R1a; a payload flag on the `sibling-released` dispatch
would need each consumer's shim to forward it; and a red bump PR, which is what
currently keeps this repository at `v1.70.0`, is not a lever at all.

**This does not change who rules.** The lever choice remains the maintainer's
call at R1a's merge time, per the rider on `livespec-dev-tooling-xzxrm5`; this
note only makes the recommended option concrete enough to file as R2's first
slice the moment it is ruled.

## 4. Sequencing note

R6a is orthogonal to R1 and R2 and factory-safe; it can dispatch as soon as the
factory credential is restored. R6b waits for R6a to merge and is the
maintainer's to land and to switch on. The scope event's Wave 3 wording ("R6
after R1/R2") was about turning the wall ON after the warn census, not about
building it; building it now costs nothing downstream.
