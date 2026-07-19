---
topic: reconcile-merged-dispatch-lock
author: claude-fable-5
created_at: 2026-07-19T10:35:00Z
---

## Proposal: Reconcile-merged dispatch lock and checkout ownership

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Replace the heartbeat-based `reconcile-merged` liveness contract with a
dispatch-scoped ownership lock and a reconcile-specific janitor checkout. The
heartbeat is produced only while Fabro is running and is silent during the
post-merge janitor window, so it is not a valid guard for the race this valve
exists to avoid.

### Proposed Changes

In `SPECIFICATION/contracts.md`, replace the `reconcile-merged` paragraph that
requires a heartbeat refusal and shared janitor checkout lock with the following
contract text:

```markdown
The Dispatcher's guarded recovery surface for an already-merged item is
`reconcile-merged --repo <path> --item <work-item-id> [--json]` and, only after
an operator has confirmed the original dispatcher process is dead,
`reconcile-merged --repo <path> --item <work-item-id> --force [--json]`. It MUST
refuse unless the named item is currently `active`, because this valve exists
only for a dispatch whose merged PR did not complete post-run disposition.

A live dispatch MUST hold a dispatch-scoped ownership lock for the whole
dispatch, including the post-merge janitor and disposition window. The lock
content MUST include at least the dispatcher process id, a start timestamp, the
work-item id, and the dispatch id when one is available. Before resolving the PR
or provisioning any janitor checkout, `reconcile-merged` MUST read that lock and
refuse by default when the lock exists and its process id is alive. The refusal
message MUST report the lock age and tell the operator to confirm liveness with
`fabro ps`, wait for the janitor window to close, or use `--force` only after
confirming the original dispatcher process is dead. A stale lock whose process
id is no longer alive MUST NOT block reconciliation, because that is the
stranded-dispatch case this valve exists to recover. `--force` bypasses only the
live-lock refusal; it MUST NOT bypass source lane checks, merged-PR resolution,
post-merge janitor execution, or acceptance journaling.

The reconcile valve MUST use a janitor checkout path that is distinct from the
normal dispatch loop's `janitor-<work-item-id>` path, such as
`janitor-reconcile-<work-item-id>`. This path ownership rule is independent of
the liveness lock: even if a guard is stale, absent, or bypassed with `--force`,
a reconcile run MUST NOT preclean or remove the live dispatch's janitor
checkout. The post-merge janitor MAY still hold a per-checkout lock before
precleaning or provisioning, and that lock MUST continue to block concurrent
callers that target the same checkout path.

The valve MUST resolve the PR number and merge SHA from GitHub, by the expected
`feat/<work-item-id>` branch first or a merged PR title/search match carrying the
work-item id only when that fallback is unambiguous on the default branch. The
fallback search MUST include a default-branch base filter. If multiple merged PR
candidates survive filtering, the valve MUST refuse with a clear ambiguous-PR
error listing the candidates rather than silently choosing the first result. The
valve MUST NOT require or trust ledger audit metadata for that resolution. After
a merged PR resolves, the valve MUST NOT launch Fabro and MUST NOT rebuild the
change; it reruns the same post-merge janitor used by the dispatch engine
against a fresh checkout of the merged ref. A green janitor MUST enter the
existing post-merge acceptance path unchanged, including the `active ->
acceptance` ledger-complete write, acceptance journal records, and
policy-governed `acceptance -> done` auto-accept when applicable. A red janitor,
missing merged PR, wrong source lane, ambiguous merged PR, or held janitor
checkout lock MUST leave the item `active` and report the failed guarded
precondition or janitor stage. This is a distinct guarded entry path and does
not widen the `drive move` target set; `acceptance`, `done`, and
`pending-approval` remain forbidden `move` targets.
```

### Motivation

The heartbeat signal is absent during the contested post-merge janitor window. A
dispatch-scoped lock is present across the whole dispatch lifecycle, while a
separate reconcile checkout removes the destructive half of the race even when a
lock is stale or bypassed. Explicit PR ambiguity refusal prevents the recovery
valve from journaling completion evidence for the wrong merged PR.
