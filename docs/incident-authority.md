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
locates nothing and authorizes nothing. Only a `repair` or `reverting` attempt
whose verification was deferred admits its carrier, and the audit reports that
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

`record-local-gates` accepts the same exact current-identity query plus
`--receipt-json`. This records evidence on that incident item without changing
its authority generation or lifecycle state. A pre-PR snapshot may carry
`pr_number: 0` only during repair and only with no landed commit/tree pairs.
Other phases still require an identified PR. This permits pre-commit evidence
on a previously provisioned chain; it does not create the chain.

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
bytes do not change. A successor of such an attempt may introduce a carrier. This
change models and validates the state only: it neither pushes, observes a forge,
binds a PR nor fences a factory.

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

Not in this slice: wiring `carrier_selection` into the Dispatcher's
reconcile-merged and post-host-record calls, returning ownership for normal
repayment, and the live multi-host proof the contract requires before
enablement.

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
