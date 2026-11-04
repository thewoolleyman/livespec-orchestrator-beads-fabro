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
