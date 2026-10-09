## The maintainer's statement of what done means

For other unrelated stuff, create a new plan that we can work to address them.

## Definition of Done assertions derived from that statement

- Transferring a plan's work item to another repository or plan changes who executes it and leaves the supervising plan live and incomplete; the plan does not archive on the strength of the transfer.
- Every transferred item is represented under the supervising plan epic by one durable pointer child that names the downstream repository, work-item identifier, URL, acceptance authority and evidence state, and that pointer stays undisposed until the downstream item is merged and its linked exit criteria carry current verification evidence.
- The archive gate grades pointer children and the plan's original exit gates as delivery evidence, separately from requirement-carrier coverage, and refuses while either is unmet, naming what is unmet.

# Opening note: transfers become durable pointer children (2026-10-09)

Status of this note: the opening research note of plan `plan-transfer-pointer-children`.
It records why the plan exists, where its one work item came from, and what it is not.

## Why this plan exists

The plan clause says a plan remains live until its work is genuinely complete, and then
permits an archive-time transfer of "any remaining work". The archive machinery and the
completeness reviewer grade direct-child disposition and requirement-carrier coverage, so
a closed bootstrap child plus named-but-open external issues can pass archival even though
the outcome, its exit gates and any recorded maintainer acceptance remain incomplete.
Regression provenance, recorded on the work item: livespec plan `create-agent-cockpit-repo`
(ledger epic livespec-livyxu) was archived while its G-1 to G3 outcomes were unmet and
agent-cockpit-info issues 2 to 12 merely carried the work.

This is a change to the plan LIFECYCLE MODEL (what a transfer means, what a pointer child
is, what the archive gate grades), so it will begin as a proposed change to the
specification's plan clause and only then produce implementing work items.

## Where the work item came from

`bd-ib-e26omv` was filed 2026-09-12 with no parent, adopted on 2026-10-08 into plan
`definition-and-proof-of-done` (epic bd-ib-7sjdzv) by the factory-reliability session's
fleet review, and moved here on 2026-10-09 by the definition-and-proof-of-done session:
that plan owns the archive PROOF leg (a plan proves its own Definition of Done against a
released build before archiving), not the transfer semantics of the plan clause, and its
two other adopted archive-gate repairs (bd-ib-0pf5 recency binding, bd-ib-3xsz reviewer
independence) are conformance fixes to ratified text, which this is not.

The maintainer's statement above is the standing instruction under which this plan was
opened ("For other unrelated stuff, create a new plan that we can work to address them",
2026-10-07). The Definition of Done assertions are SESSION-DERIVED from the work item's
own acceptance criteria, with no maintainer present to confirm them; they are a proposal
to be confirmed at the first resume, not a ruling.

## What this plan is not

It does not change the Proof of Done leg, host-captured proof, or the completeness-review
recency and independence repairs; those stay with definition-and-proof-of-done.

## First actions

1. Confirm or amend the assertions above with the maintainer.
2. File the proposed change against the plan clause (transfer semantics, pointer child
   shape and lifecycle, archive-gate grading of delivery evidence).
3. After ratification, slice bd-ib-e26omv into implementing children with behavioural
   Definitions of Done and dispatch them.
