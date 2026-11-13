# Canonical incident authority reader

The public `scripts/bin/incident_authority.py` process boundary lets installed
consumers use the canonical reader without importing private plugin modules.
Resolve the governed project's registered installed plugin and use its credential
wrapper. Invoke `read-current` or `read-history` with `--repo`, `--repository`,
`--item`, `--attempt`, `--phase`, `--operation`, `--generation`, and `--owner`.

The schema-1 JSON reply carries `status: verified|refused`, `result`,
`authorizes_current_effects`, and `normal_factory_proof: false`. Refusals exit 78
and name their code and detail. Historical lookup never authorizes current
effects. Verified results bind the complete immutable attempt and its committed
and current token identities. Workflow publication authority remains separate.

The reader obtains authority through authenticated Beads reads. One canonical
item carries a genesis comment naming a server-assigned authority token. Retained
conditional-close reasons bind each prior token, its successor, repository, item,
and complete next generation. Conflicting roots, malformed records, bad identities,
cycles, unsupported states, unreadable links and the bounded history limit produce
named refusals. Repeated identical genesis delivery is idempotent. The reader
rechecks the open successor before returning a current-generation observation.

A current read (`read-current`, `read-local-gates`, the incident head read) does not
re-read the chain from genesis. The canonical writer records the token it just closed
under the item's `incident_authority_head` metadata, and the reader starts its walk
there and follows the tokens' own links to the open successor, so the records read
are bounded by that hint's lag and not by the number of generations. The hint is a
start point and never authority: a stale one only lengthens the forward walk, and an
absent one (a chain not yet transitioned by this build), an open-token one or one
naming another item's token reads the whole chain from the genesis root. Historical
lookups, `read-history` and the writer's operation-reuse check always read the whole
retained chain. The reply omits `operation_ids`, the set of operations a read walked,
because that set depends on which of the two reads produced it.

Genesis and transition markers are `livespec-incident-authority-v1` and
`livespec-incident-transition-v1`, followed by a newline and canonical JSON with
sorted keys, compact separators, and schema 1. Tokens carry the title
`livespec incident authority epoch token`. The canonical writer must use
server-assigned creates, server conditional close with winner readback, and retain
committed history. A close command's exit status never establishes the winner.

This slice provides the reader, process protocol, and conditional transition writer
for an already established chain. Exact retries recover their original immutable
receipt; losers delete only their own unlinked candidate, while an unreadable
winning close retains its candidate for later recovery. It does not initialize live
authority, grant writer capability, fence a factory, change lifecycle state, or
enable production incident entrances. Those remain on the
existing carriers. Unarmed items refuse with `incident-authority-missing`; mutable
metadata, labels, flags and caller JSON supply no fallback. During a tenant outage,
only the separately trusted controller recovery boundary can authorize recovery.

Consumers must revalidate current authority immediately before an effect. A read
does not lock arbitrary later effects: a canonical writer must commit its own
server conditional transition. Historical records remain provenance after labels,
environment, owner, or phase have changed, and never become normal factory proof.

The factory-provenance merge gate and the retrospective factory-bypass audit
consume this history through `read_incident_history`. Each locates a candidate
only by an explicit `--incident-item <id>` (repeatable) and binds the exact
repository, pull request number, head and complete landed commit set the retained
attempt recorded; a title mention, label, trailer, marker or environment variable
locates nothing and authorizes nothing. Only a `repair`, `master-observation` or
`reverting` attempt whose verification was deferred admits its carrier, and the audit reports that
exception with its normal repayment outstanding until the chain reaches `closed`.
A carrier the chain records in a repayment phase must earn normal factory
provenance: the gate refuses it the `factory-override` label. A named item whose
chain cannot be read is unobservable to the gate (exit 2) and a reported refusal
in the audit, whose carriers stay flagged. The audit reaches the ledger through
`--project-root`, the checkout whose store configuration names the tenant.

An authenticated installed controller can commit an existing chain through the
same process entrance using `commit-transition`, the complete prior identity
arguments above, and `--successor-json`. The successor is the full immutable
attempt encoded as canonical JSON with sorted keys and compact separators. The
command uses the canonical decoder and server conditional-close writer; it does
not accept comments or mutable metadata as a substitute. Malformed, duplicate-key
or noncanonical payloads, wrong prior identities, stale observations and reused
operations with changed contents return named refusals before a new transition.

`incident_authority.close_drill` is the dedicated drill-close writer. It takes
the current incident reading, re-reads every recorded carrier pull request from
the authenticated forge, and records `drill-closed` only for merged carriers
whose base is `incident-scratch/**` and whose retained landed commits are absent
from master. A missing carrier or master-based carrier is
`incident-not-a-recorded-drill`; unreadable or incomplete forge evidence is
`incident-drill-evidence-unavailable`. Either refusal writes nothing. Success
sets the canonical lifecycle state to `done`, clears the incident claim, leaves
no repayment outstanding, and returns a terminal drill closure; the fixed
generation and operation identity recover a repeated completed invocation.
An exact retry recovers the original committed receipt without another token.

The writer authenticates the prior identity through retained history so a caller
can recover a lost reply after its first successful transition. The canonical
writer still checks current ownership before any new close. A writer response is
a recording receipt and always carries `authorizes_current_effects: false`;
consumers must separately read current authority before effects. The command
preserves the existing authenticated tenant credential boundary. It does not
bootstrap a chain, authorize phase eligibility, update the item's lifecycle state,
cancel factory work, or provision writer credentials. An absent chain remains
`incident-authority-missing`, and a tenant outage remains unavailable.

`record-local-gates` accepts the same exact current-identity query plus exactly
one receipt source: `--receipt-json <receipt>` or `--receipt-stdin`, which reads
the receipt from standard input. The stdin source exists because Linux caps one
argv entry at 131072 bytes, so a receipt between 128 KiB and the authority's own
1 MiB bound cannot travel as an argument; with `--receipt-stdin` the authority's
bound is the only limit, and a larger receipt is refused
`incident-receipt-invalid` with nothing recorded. This records evidence on that incident item without changing
its authority generation or lifecycle state. A pre-PR snapshot may carry
`pr_number: 0` only during repair and only with no landed commit/tree pairs.
Other phases still require an identified PR. This permits pre-commit evidence
on a previously provisioned chain; it does not create the chain.

## Recording the merge

`record-merge` is the named writer of `master-observation`. It takes only the
shared identity arguments, naming the current `repair` attempt with a `pr-bound`
carrier. It reads the PR the chain names through `gh pr view`, refuses one that
has not merged or whose head differs from the carrier, and reads the landed
commits and trees from git over the merge commit's first-parent history. The
successor keeps the attempt, head and carrier; only its phase, operation,
generation and landed pairs change. An exact retry recovers the recorded
generation, with `recovered: true`.

The script that merges runs it right after `POST /bind`. It is never a
precondition of the first-failure revert: the observer acts on its retained arm
with no ledger read, and a required leaf can fail about 90 seconds after the
merge. The action reads the merge commit rather than the tip of master, so it
still records correctly after the revert landed. `reopen-regression`,
`enter-repayment` and original-run `collect` all need this generation, so whoever
runs the first of those runs `record-merge` first if the script did not.

`reopen-regression` accepts a `master-observation` head as well as a repayment
phase or `closed`, so a merged attempt's first master failure reaches
`reverting` and a corrected attempt on the same route as a later regression.

## Carrier state

An attempt may carry an explicit `carrier` record (specification v302,
"Carrier identity before and after PR creation"). It is one of three states:

| `state` | Keys | PR number |
| --- | --- | --- |
| `branch-reserved` | `target_ref`, `input_parent`, `staged_tree` | `0` |
| `head-published` | those keys plus `remote_head` | `0` |
| `pr-bound` | the same keys as `head-published` | positive |

`target_ref` is a fully qualified `refs/heads/...` name; the other values are
full lowercase Git object ids. A pre-PR state also requires a pre-PR phase
(`repair`, or `repayment-admission`, `repayment-ready` and `repayment-active`
before the repayment run's own PR exists) and no landed commit/tree pairs. A PR
number exists exactly when the carrier is `pr-bound`; a placeholder or a
positive number on a pre-PR carrier is invalid.

A transition may advance a carrier (`branch-reserved` to `head-published` to
`pr-bound`) but never regress it, drop it once present, change its target ref, or
rewrite the recorded input parent and staged tree after the reservation was
published. Only a still-reserved carrier may refresh its boundary. Once bound, the
PR number is fixed. The one exception is repayment entry: a `master-observation`
attempt whose expedited carrier is `pr-bound` may be succeeded by a
`repayment-admission` attempt on a fresh `branch-reserved` carrier with a
different target ref, because the repayment run needs its own branch and PR.
A record naming an unknown state, an extra key or a malformed value is refused
as `incident-carrier-unsupported`, never read as normal mode.

## Normal repayment

`livespec_orchestrator_beads_fabro.incident_normal_repayment` carries the
same-item normal factory repayment (specification "Expedited incident
lifecycle", scenario "a successful incident merge reenters normal factory on
the same item"). `plan_repayment` derives ONE repayment operation from the
current `master-observation` attempt and a `MasterCiRun` that is complete,
`success`, and names one of the attempt's landed commits; anything else is a
named refusal (`incident-repayment-not-eligible`,
`incident-repayment-master-ci-outstanding`). The operation id is a digest of
the successful attempt and the master run, so a restart or duplicate delivery
derives the same id. `enter_repayment` records `repayment-admission` as the
next generation and returns the item to `pending-approval` through its claim
token, in the same write releasing the incident holder's `dispatch_claim` stamp
that canonical entry left on the item (the retained `incident_claim` record
stays); `advance_repayment` records `repayment-ready` (only with ordinary
admission complete), `repayment-active` (only once the item rests `active`,
assigned `fabro`, under a factory dispatch claim stamp; an incident holder's
stamp is refused `incident-repayment-claim-missing` like a missing one) and `repayment-acceptance`,
each only against the lifecycle state the contract table pairs with it
(`incident-phase-state-mismatch` otherwise). Repeated delivery of any step
recovers the recorded generation (`recovered: true`) and writes nothing.

`repayment_scope` and `validate_repayment_carrier` name what the repayment
carrier owes beyond marker removal: every remaining
`EXPEDITED_INCIDENT_RESPONSE flag: <item>` marker, every cumulative original
path normal validation did not exercise, and every recorded deferred debt not
repaid. `scrub_incident_flags` removes both `EXPEDITED_INCIDENT_RESPONSE` and
`EXPEDITED_INCIDENT_RESPONSE_REVERT` from a normal dispatch's environment at
the head of `dispatch_preamble`, before provider selection and every sandbox,
hook or pull-request subprocess, and the janitor's scrub set removes them
again from its gate runs. `select_incident_pull_request` selects only the
current attempt's bound PR among merged candidates; an unbound repayment
attempt refuses rather than falling back to the earlier repair PR.

Migration: schema-1 attempts written before this model carry no `carrier` key.
They remain readable with their exact earlier meaning, including the repair-only
`pr_number: 0` case, and they serialize back without the key, so their receipt
bytes do not change. A successor of such an attempt may introduce a carrier. The library
models and validates the state only: it neither pushes, observes a forge,
binds a PR nor fences a factory. The process boundary's lifecycle actions
(section "Lifecycle actions" below) are its operator entrance.

## Regression recovery

`livespec_orchestrator_beads_fabro.incident_regression_recovery` (planning in
`_incident_recovery_plan` and `_incident_recovery_correction`) carries what
happens when an incident change turns out to be wrong after it merged
(specification "Expedited incident lifecycle"; scenarios "an attributable
regression fences repayment and reopens the same incident" and "a
deferred-proof-only finding is repaired without reverting healthy master";
bd-ib-k5teti). A `Finding` names its `surface` (`trunk` for the repository's
default branch, `pull-request`, `consumer` or `deferred-proof`), the subject and failing run it was observed
on, the head that run evaluated, the landed incident commit its change
evidence names, and whether deployed master is healthy.

`reopen_for_regression` takes the current reading of a live repayment
(`repayment-admission` through `repayment-acceptance`) or of a `closed`
incident, the attributed attempt and the finding. The attributed attempt is
re-read from the retained chain, so caller bytes confer nothing
(`incident-reopen-attribution-mismatch`). The finding must be a trunk,
pull-request or consumer failure whose attributed commit is one of that
attempt's landed commits (`incident-regression-unattributed` otherwise). The
same item is reopened as the next generation in phase `reverting`, bound to
the attributed merged carrier and PR, with `repayment_required` kept true. The
transition writer admits that one carrier change at a reopen, and a corrected
repair's fresh branch after the revert receipt; every other carrier rule is
unchanged. The item then returns to `active` under the incident owner through
its claim token, the incident holder's stamp replacing the factory's (the
factory stamp is retained as `prior_claim`), so the superseded run's terminal,
proof or cleanup write answers `claim-changed`. The operation id is a digest
of the superseded generation and the finding, so a repeated delivery recovers
the recorded generation and writes nothing more. A
`livespec-incident-recovery-v1` comment records the recovery request: the
superseded and attributed generations, the attributed PR, the retained
failures and `repayment_owed: true`. The revert itself stays the trusted
controller's.

`require_repayment_current(client, observed, effect)` is the gate a repayment
merge, proof or closure takes immediately before its side effect. A repayment
generation the chain has moved past is refused `incident-repayment-superseded`,
naming the effect. Any other stale observation keeps
`incident-generation-stale`.

A `deferred-proof` finding while master is healthy never reopens
(`incident-finding-deferred-proof-only`). `record_deferred_finding` records it
as `deferred-finding:<run>` debt on the live repayment generation (admission,
ready or active), so `validate_repayment_carrier` names it outstanding until
the repayment pull request repays it. Item lifecycle, claim and master stay
as they are. A deferred finding with master unhealthy is
`incident-finding-not-isolated`, and a trunk, pull-request or consumer finding
is `incident-finding-requires-recovery`.

`record_revert_receipt` reconciles the controller's `RevertReceipt` and moves
`reverting` to `collecting-failures`. `enter_corrected_attempt` then opens a
corrected `repair` attempt on its own `branch-reserved` carrier, only from
`collecting-failures` (`incident-correction-not-eligible`) and only while the
original failures stay retained (`incident-correction-failures-missing`). Its
`Correction` must be fresh. A `repair` whose head is a failed or already
landed head, or any correction that reuses a failing run as its evidence, is
`incident-correction-unchanged-reland`. A `measured-resolution` may keep the
original head when its measurement is new. Any other kind, or empty evidence,
is `incident-correction-evidence-missing`. The corrected attempt keeps its
deferred debt and `repayment_required`, so final normal repayment stays owed,
and its retained record carries the original failures beside the correction.
`retained_failures` and `recovery_attempts` read those records. Recovery is
counted there, apart from ordinary acceptance rework and nonconvergence
budgets.

## Incident completion

`livespec_orchestrator_beads_fabro.incident_completion` carries final normal
proof (specification "Expedited incident lifecycle", scenario "incident
completion requires final normal proof rather than an old repair merge").

`read_incident_standing` locates an incident only by the item's own genesis
comment and walks the chain the genesis names. A `normal` item has no genesis
and closes as before. An `incident` standing carries every obligation the chain
still owes with nothing observed, which is empty only once the chain records
`closed`. An `unreadable` standing (comments unreadable, a malformed or
ambiguous genesis, a chain that refuses) is an obligation too, never a normal
item.

Every closure route reads the standing immediately before it closes and holds
the item while anything is outstanding: the Dispatcher's completion valve
(which `reconcile-merged` and a proof-only resume reach) parks the item instead
of taking its completed or no-change-needed close; `reconcile-merged --regrade`
parks a PASS; the `accept:<id>` valve refuses `incident-obligation-outstanding`;
`close-work-item` refuses every resolution with `IncidentClosureRefusedError`
and exit 5. Each hold is journaled as `incident-obligation-outstanding` with its
route and the named obligations.

Acceptance grades the original expedited carrier PRs together with the current
repayment carrier: the merged-diff leg is every original PR's diff followed by
the current one. A merge the chain does not bind as the current repayment
carrier (the earlier repair PR resumed for proof, or a repayment not yet bound
as `repayment-acceptance`) is ungradeable, so the pass parks at
NEEDS_ATTENTION, and no proof pointer is written for it
(`incident-proof-pointer-refused`). A marker-removal diff alone never grades.

`complete_incident` takes the observed `IncidentCompletionEvidence` and records
`closed` only when nothing is outstanding: the current phase is
`repayment-acceptance` with its PR bound, merged and landed; that PR's normal
master run is complete, `success` and names a repayment landed commit; the head
tree carries no marker; every cumulative original path was validated; every
deferred verification and spec debt was repaid; the manual outcome is recorded;
and no related consumer or PR failure lacks a disposition. Missing, cancelled,
incomplete or unreadable evidence is a named obligation
(`repayment-master-ci-missing`, `repayment-master-ci-cancelled:<run>`,
`marker-removal-unobserved`, ...). A repeated delivery after `closed` recovers
it. The transition writer refuses any `closed` successor that does not follow
`repayment-acceptance`, whoever commits it.

Each standing also carries the chain head it observed, and every effect site
revalidates that generation through `require_repayment_current` (bd-ib-k5teti)
immediately before its side effect: the proof pointer write (effect `proof`),
the completion valve's and the regrade arm's close, the `accept:<id>` valve and
`close-work-item` (effect `closure`), and `complete_incident`'s `closed`
transition. A repayment generation a regression reopen superseded is refused
`incident-repayment-superseded`, any other moved generation
`incident-generation-stale`; the refusal is journaled or reported like any
other outstanding obligation and nothing is written.

The operator entrance that gathers the completion evidence and calls
`complete_incident` is the `complete-incident` action (section "Lifecycle
actions" below), and `bind-repayment-acceptance` binds the merged repayment
PR first. Not in this slice: doing either from the Dispatcher automatically.
Until an operator binds the repayment and runs `complete-incident`, an incident
item parks in acceptance with its obligations named.

## Lifecycle actions

The `incident_authority.py` process boundary exposes repayment, regression
recovery and correction as actions (bd-ib-nabx3u). Each is a thin adapter over
the released function above. Each takes the same `--repo`, `--repository`,
`--item`, `--attempt`, `--phase`, `--operation`, `--generation` and `--owner`
identity as the other actions, naming the CURRENT attempt it acts on, and
prints one schema-1 reply. A success carries the recorded generation under
`result.reading.attempt`; a refusal exits 78 and names the library's code. A
payload argument is valid only for its own action, and a missing one is a
usage error (exit 2).

| Action | Payload | Calls |
| --- | --- | --- |
| `enter-repayment` | `--master-run <run-id> --target-ref <ref>` | `enter_repayment` |
| `advance-repayment` | `--to-phase <phase> [--admission-complete]` | `advance_repayment` |
| `bind-repayment-acceptance` | `--pr <number>` | `bind_repayment_acceptance` |
| `reopen-regression` | `--attributed-json <attempt> --finding-json <finding> --principal <owner>` | `reopen_for_regression` |
| `record-deferred-finding` | `--finding-json <finding>` | `record_deferred_finding` |
| `record-revert-receipt` | `--revert-receipt-json <receipt>` | `record_revert_receipt` |
| `record-rollback-conflict` | `--rollback-conflict-json <conflict>` | `record_rollback_conflict` |
| `resolve-rollback-conflict` | `--rollback-resolution-json <resolution>` | `resolve_rollback_conflict` |
| `correct-attempt` | `--correction-json <correction> --target-ref <ref>` | `enter_corrected_attempt` |
| `correct-unmerged-attempt` | `--failed-run <run-id> --correction-json <correction> --target-ref <ref>` | `enter_unmerged_correction` |
| `complete-incident` | `--master-run <run-id> --completion-json <attestation>` | `complete_incident` |

`enter-repayment` does not take the master result from its caller. It reads
the named run with `gh run view <run-id> --repo <repository> --json
headSha,status,conclusion`, so the run's own completion and conclusion gate
the repayment. A run the forge cannot report is
`incident-repayment-master-ci-unobservable`. A run still in progress, or one
that failed, is `incident-repayment-master-ci-outstanding`, and nothing is
recorded. `--admission-complete` asserts that ordinary admission approved the
unchanged incident Definition of Done; only `advance-repayment` accepts it.
`--principal` names the incident owner a reopened item returns to.
`record-revert-receipt` records the trusted controller's receipt. It is the
step that makes `correct-attempt` eligible.
`correct-unmerged-attempt` is the corrected attempt for a `repair` whose
`pr-bound` expedited PR failed a retained fast check before merge and was then
closed unmerged (bd-ib-elq5ry). Name the current `pr-bound` `repair` attempt;
anything else is `incident-correction-not-eligible`, and the forge is not
read. The action takes no forge result from its caller. It reads the attempt's
own PR with `gh pr view <pr> --repo <repository> --json
number,state,headRefName,headRefOid`, and the run the operator names with
`gh run view <run-id> --repo <repository> --json headSha,status,conclusion`:

- A PR that is not `CLOSED` (open, or merged) is
  `incident-correction-pr-not-closed-unmerged`.
- A PR whose head branch or head commit is not the carrier's is
  `incident-correction-carrier-mismatch`.
- A run that is not completed with conclusion `failure` on the carrier's exact
  head is `incident-correction-run-not-failed-on-head`.
- A PR or run the forge cannot report is `incident-correction-pr-unobservable`
  or `incident-correction-run-unobservable`.
- A `--target-ref` equal to the failed carrier's ref is
  `incident-correction-target-reused`.

The correction is held to the same freshness rule as `correct-attempt`: a
repair whose head equals any retained failed head, or evidence that reuses a
retained failed run, is `incident-correction-unchanged-reland`. On success the
next generation is a new `repair` attempt on a fresh `branch-reserved` carrier
at `--target-ref`; the failed `pr-bound` attempt stays in the history as
recorded. A `corrected-attempt` recovery record with `source:
"unmerged-pull-request"` retains the closed PR and the failed run, and that run
joins the item's retained failures. Readers need no change for this transition:
the attempt schema is unchanged, and only the transition writer validates
successors.
`record-rollback-conflict` records an owned inverse-patch conflict for the
current `reverting` attempt with its release condition, writing the
`rollback-conflict` phase and the `blocked` lifecycle status in one transition;
`resolve-rollback-conflict` releases it by that condition into `reverting` while
the inverse recovery is still owed, or `collecting-failures` once the resolution
carries a revert receipt. An exact retry of either recovers the recorded
transition.

`bind-repayment-acceptance` records `repayment-acceptance` once the factory
run's repayment PR has merged (bd-ib-pqz3nw). `advance-repayment --to-phase
repayment-acceptance` cannot do this. It changes only the phase and generation,
so the transition writer refuses it once the carrier has a PR. Name the current
`repayment-active` attempt while the item rests in `acceptance`
(`incident-repayment-phase-order`, `incident-repayment-stale-observation` or
`incident-phase-state-mismatch` otherwise). The action reads the PR with
`gh pr view <pr> --repo <repository> --json
number,state,headRefName,headRefOid,mergeCommit,commits`:

- A PR that is not `MERGED` is `incident-repayment-pr-unmerged`.
- A PR the forge cannot report is `incident-repayment-pr-unobservable`.
- A head branch that is not the carrier's reserved ref is
  `incident-repayment-carrier-mismatch`.

It then fetches the merge commit and reads its first-parent history with
`git log`. A rebase merge (one commit per PR commit, with the same subjects)
binds every landed commit and its tree, oldest first. A squash or merge commit
binds the merge commit alone. History that cannot be read is
`incident-repayment-landed-unobservable`. The successor binds the PR number,
the PR head and a `pr-bound` carrier whose remote head is that head. It is
committed through the canonical transition writer, and nothing is written on
any refusal.

`complete-incident` is the operator entrance that records `closed` (bd-ib-pqz3nw).
Name the current `repayment-acceptance` attempt. The action gathers what
`complete_incident` needs, and takes none of it from the caller as a result:

- The repayment merge comes from `gh pr view <pr> --repo <repository> --json
  number,state` of the PR the named attempt binds. Only `MERGED` counts as
  observed. A repayment with no bound PR is not read at all.
- The master result comes from the same `gh run view` read that
  `enter-repayment` takes, for `--master-run`. The run must be complete and
  successful, and its head must be one of the repayment's landed commits.
- The marker scan fetches that run head (`git fetch origin <head>` in `--repo`)
  and runs `git grep -l -F` for `incident_marker(<item>)` over its tree. A tree
  that cannot be read stays `marker-removal-unobserved`.
- `--completion-json` is the operator's attestation. It is the canonical
  encoding of exactly `manual_outcome` (a boolean), `repaid_debt`,
  `undisposed_failures` and `validated_paths` (each a list of strings), for
  example `{"manual_outcome":true,"repaid_debt":["normal-factory-proof"],"undisposed_failures":[],"validated_paths":["app.py"]}`.

When anything is still owed, the reply is `incident-completion-outstanding`,
naming the item and every obligation in order (for example
`repayment-master-ci-incomplete:<run>`, `marker-present:<path>`,
`deferred-debt-outstanding:<work>` or `manual-outcome-missing`), and nothing is
written. A PR the forge cannot report is
`incident-completion-repayment-pr-unobservable`, and a run it cannot report is
`incident-repayment-master-ci-unobservable`. On success, `result.recorded` is
true and `result.reading.attempt` is the `closed` generation. Repeating the
action after `closed` returns `recovered: true` with no reading and writes
nothing more.

Every JSON payload must be the canonical encoding (sorted keys, compact
separators) of exactly its record's fields with their types: a `Finding`, a
`RevertReceipt`, a `Correction`, or for `--attributed-json` a complete attempt
record as the chain retains it. Anything else is
`incident-action-invalid-payload`, naming the argument, and nothing is
written.

## Genesis

`publish-genesis --genesis-json <request>` takes the same identity arguments and
one canonical request: `schema` 1, `principal`, `expected_claim` and the complete
initial `attempt` (generation 1, phase `repair`, a `branch-reserved` carrier, and
the named repository, item and operation). `expected_claim` is the item's current
dispatch claim token id (`metadata.dispatch_claim_token`) as the caller observed
it. The request is decoded and bound to its SHA-256 digest; an invalid or
mismatched request is refused as `incident-genesis-invalid-request`.

The exclusion is the claim-token protocol's own server-enforced operation: the
conditional close of that current token. While the committed
`dispatcher.claim_tokens` cutover is not `true`, no all-writer conditional
operation is installed, so the command refuses
`incident-genesis-capability-unavailable` with exit 78, constructs no ledger
client, writes nothing, files no other item and takes no local lock. Once it is `true`, the writer first recovers
an exact retry from the chain (same operation and identical request bytes return
the original root with `recovered: true`; changed bytes under the same operation
refuse `incident-operation-conflict`; another operation's root, or an unfenced
legacy root, refuses `incident-genesis-root-exists`). It then reads the item:
an item naming no open token refuses `incident-genesis-claim-token-missing`; a token other than
`expected_claim` refuses `incident-genesis-claim-mismatch`; an unreadable token
refuses `incident-genesis-claim-unobservable`; a token another writer closed
whose successor the item does not yet name refuses
`incident-genesis-claim-transition-pending` and is never taken over.

To publish, the writer mints the root and its open successor (server-assigned
incident epoch tokens), closes the root privately with the generation-1
transition, mints a successor claim token, and closes the current claim token
with a claim-token transition reason (`kind: claim-token-transition`, `intent:
incident-genesis`, the successor) whose `incident` block binds the repository,
item, operation, principal, request digest, root token, expected claim and
`prior_claim` (the item's status, assignee and whole `dispatch_claim` stamp as
entry found them; a fence written before this key is still decoded). The
read-back reason decides: a foreign reason is `incident-genesis-lost-race` and
the loser deletes its unlinked root and successor and discards its claim token;
an open token after the close is `incident-genesis-outcome-unknown` and every
candidate is kept. A winner past the protocol's 120 s lease refuses
`incident-genesis-lease-expired` and leaves its successor open. Inside the
lease the winner appends the genesis comment, which now also names
`claim_token_id`, then writes the item ONCE: the successor as its current token,
status `active`, the incident owner as assignee, and the takeover record
described under "Canonical entry" below. A won close whose publication never
landed is completed by the exact retry: the comment is appended once, and the
lost takeover is remade through `change_claim` itself, which reports
`incident-genesis-claim-transition-pending` until the protocol's takeover wait
has elapsed on this writer's clock, then takes over the stranded successor
conditioned on the retained `prior_claim`; a row that moved meanwhile refuses
`incident-genesis-fence-lost` and the host must not proceed. The one-shot
command waits that wait once and retries once. Tenant failures are
`incident-genesis-unavailable`.

The reply is a `GenesisReceipt`: `request_digest`, `root_token_id`,
`claim_token_id`, `successor_claim_token_id`, the committed and current token
ids, the verified generation-1 `attempt` read back through the canonical reader,
and `recovered`. It never authorizes current effects; consumers read current
authority before acting. The reader verifies a genesis record that names
`claim_token_id` against that token's retained close: the token must be closed
and its fence must name the same root, item, repository and token, or the record
is `incident-authority-invalid-genesis`. Records without `claim_token_id` keep
their earlier meaning.

## Canonical entry

Entry keeps one canonical item (contracts "Expedited incident lifecycle",
"Factory transfer and recovery of the initial operation"; bd-ib-dzbwaq).

`file-incident --filing-json <filing>` is the path for a scope no item covers.
It takes `--repo`, `--repository`, `--operation` and `--owner` and no item
identity; the filing is canonical JSON with `schema` 1, `repository`,
`principal`, `operation_id`, `title`, `impact`, `scope` and `behavioral_intent`,
and must name the same repository, operation and principal as the arguments
(`incident-filing-invalid-request` otherwise). One `bd create` under a fresh
tenant-prefixed id names the item's first claim token in the creating write;
the item rests at `backlog` with label `incident:entry`, metadata
`incident_filing` (operation id, principal, request digest) and a retained
`livespec-incident-entry-v1` comment recording `deferred_to_repayment:
["ordinary-admission", "spec-debt"]`: no model-backed judgement runs at entry,
and both are owed before normal repayment. The reply is a `FilingReceipt`
(`item_id`, `claim_token_id`, `request_digest`, `recovered`). An identical retry
recovers the same item (`recovered: true`); changed bytes under the same
operation refuse `incident-operation-conflict`; a filed item that names no open
token refuses `incident-filing-claim-token-missing`; without the committed
cutover the command refuses `incident-genesis-capability-unavailable` and files
nothing. Entry then runs `publish-genesis` over the filed item with its first
token as `expected_claim`. An identified existing item skips the filing.

`publish-genesis` is the sanctioned transition that takes host ownership, for
an item at rest and for one with queued or live factory work alike. Winning the
item's current claim token is the fence: it is the same server-enforced
compare-and-swap every admission, run-stamp, terminal and recovery writer
serializes on. The winner's one item write moves the item to `active` under the
incident owner, replaces the whole `dispatch_claim` stamp with the incident
holder's (`dispatch_id: incident:<operation>`, `dispatching_host: <principal>`,
`run_id: incident:<root token>`, no factory) so no factory predicate reads the
row as unstamped, pending or its own, and lands `incident_claim`: `schema`,
`operation_id`, `generation`, `owner`, `prior_claim` (the retained status,
assignee and stamp), `factory_cancel: "unobserved"` and the same
`deferred_to_repayment`. A queued admission (`ready` decided), a late run
stamp, a terminal write or a stranded-claim recovery of the old generation then
answers `claim-changed` and lands nothing. No run is reported cancelled: the
cancellation result is retained as unobserved until a reader observes it.

Every later incident effect binds the exact current identity. An incident claim
writer hands `change_claim` the predicate `incident_claim_decided(operation_id,
generation, owner)`, which holds only while that entry still owns the item.
`carrier_selection(client, reading)` re-reads the chain and returns the exact
`target_ref`, `remote_head` (once `head-published`) and real positive
`pr_number` (once `pr-bound`) of the current attempt; it is the explicit
pull-request selector reconcile-merged and post-host-record take, never a
branch match or a title mention. `require_current_generation(client, observed)`
is the gate taken immediately before a proof write, a claim consumption or a
completion: an observation the head has moved past, or one that is not the
exact current reading, is refused as `incident-generation-stale`, and
`commit-transition` applies the same gate before any close. A legacy attempt
without a carrier cannot select one (`incident-carrier-unsupported`).

The Dispatcher's two merge-resolving valves take that selector. For an item
that carries a genesis record, `reconcile-merged` resolves the repository
through the forge, reads the chain's current generation (`read_incident_head`),
selects through `carrier_selection`, and resolves the merge of THAT pull
request with the carrier's head branch as the plan branch, so the forge view
that validates the selection identifies the merge by the incident carrier
itself; an operator `--pr` naming another pull request is refused.
`post-host-record` publishes its record on the pull request the chain names.
Both refuse, with exit 3 and no effect, a superseded reading as
`incident-carrier-stale`, a carrier that is not yet `pr-bound` as
`incident-carrier-unbound`, and an unresolvable repository as
`incident-repository-unresolved`. An item with no genesis record makes no chain
or forge read here and resolves exactly as before.

Not in this slice: returning ownership for normal repayment, and the live
multi-host proof the contract requires before enablement.

The canonical JSON receipt contains `receipt_id`, `hook` (`pre-commit`,
`commit-msg`, or `pre-push`), the exact Git `tree`, `mode`,
`evidence_kind: expedited-local-partial`, `exit_status`, and a nonempty `results`
array. Every gate result names its status, reason, actual return code or null,
elapsed seconds and captured output. Passed work must finish below sixty seconds;
an actual failure remains recorded failure even when cleanup crosses the budget.
Deferred work has no passing code, and a timeout has no completed verdict.
An empty inventory must explicitly record a no-applicable-work disposition.

The producer appends `livespec-incident-local-gates-v1` plus canonical JSON
binding the full immutable attempt, committed/current token ids and receipt.
Exact retries return the same checksum. Reusing a receipt id with different
contents refuses without replacing earlier evidence; concurrent identical
appends represent one logical receipt. The producer verifies readback and reads
current authority again after appending. If ownership changed, the partial
record survives but the command refuses. A receipt reply always has
`authorizes_current_effects: false` and `normal_factory_proof: false`.
It cannot satisfy normal validation or supply current authorization by itself.

Before repeating local gates after a lost reply, invoke `read-local-gates` with
the same current-identity arguments and `--receipt-id`. A verified result names
`status: recorded|absent`, the exact receipt id and committed/current token ids.
A recorded result includes its complete original receipt and the SHA256 checksum
of the canonical retained comment; an absent result carries null receipt and
checksum after a successful canonical read. The command checks current authority
before and after reading evidence. Conflicting records, foreign envelopes, stale
ownership and tenant outages refuse instead of reporting absence. It never
appends, reruns gates, changes durations, grants current effect authority or
supplies normal factory proof. Consumers preserve an original failure on retry.
