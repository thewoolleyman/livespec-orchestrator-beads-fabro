# Governing scenarios and resumed review

Measured on 2026-10-09. This note records specification and recovery evidence;
it is not the plan's final Proof of Done. The five plan assertions and their
carrier map remain unchanged.

## Released renderer and ordinary recovery

Renderer PR 2719 merged as `a4dbd081941ed168bdd55774d591cf0fe7aa9cab`.
The normal release PR 2720 published `v0.180.1` at
`a7a11fda01c06db6b76d9498939aba76f65357b6`; master CI 37945867947 passed.
Its owning `fabro-currency` thread retains the separate released host proof.
This plan does not substitute source validation for that owner's proof.

After normal status-only recovery valves, the `next` operation confirmed the
three ordinary dispatches were eligible. The two published PRs used Dispatcher
`resume`, preserving their published heads and entering `review`; neither used
plain implementation dispatch to recreate its work.

| Item | Detached gate | New factory run | Entry |
| --- | --- | --- | --- |
| `bd-ib-gh5xwq` | `20261009T144758Z-2050641` | `01M4GJ78GW7X4W92RMH40K32VK` | Resume PR 2714 at review. |
| `bd-ib-656k7i` | `20261009T144759Z-2050908` | `01M4GJ6XBF4CZ0Z6XHYJMAMZBX` | Resume PR 2713 at review. |
| `bd-ib-emzxlx` | `20261009T144306Z-1996655` | `01M4GJ52FVZ8PKT4D9V3NC3X6G` | Adopt the preserved unpublished source. |
| `bd-ib-nezrrh` | `20261009T144307Z-1996870` | `01M4GJ54DRDSBHS535GEFM6NR5` | Adopt the preserved source and finish its open Red. |
| `bd-ib-l55d7e` | `20261009T144057Z-1974093` | `01M4GJ5KMVGH4VJEKQBBC4DQ9F` | Fresh normal dispatch. |

The last run stopped at `dod_gate` before implementation: its sole reference,
`Fabro runtime constraints`, governs engine configuration rather than Dispatcher
terminal-result reconciliation. Its structured gate finding supplied the actual
reason; the later `needs_human` script's absent-run-id failure was not mistaken
for the cause. The other four runs continued independently.

## Specification references now govern the existing assertions

The terminal-evidence requirement gained the H2 `Dispatcher successful terminal
evidence` and Scenario 166 through the normal proposal/revision CLI, revision
`v122`. It authenticates the current run, latest checkpoint, successful route,
and matching repository/branch/head, while preserving cancellation, failed-stage,
needs-human, unavailable-evidence and downstream merge/acceptance guards.
The actual incident's final successful stage with next node at exit is explicitly
accepted; an independently completed exit-node entry is not required.

Independent read-only Sonnet review ran in native session
`b47ff1b1-1678-467d-92a2-68226d5ce1c8`, resolved model `claude-sonnet-5-5`,
and returned `NO BLOCKERS` at 14:58:52 UTC for canonical digest
`b00ff4fe2047fe4f93076b0c1f9e06f8e828e5740b85ef48b180d21863123f05`.
The CLI's reviewer identity field is the configured alias `sonnet`; the revision
rationale retains the distinct native session provenance. Its nonblocking
coverage finding was addressed by mapping both new H2s to existing child
`bd-ib-l55d7e` in `tests/heading-coverage.json`.

The queued diagnostic child had the same reference problem: Scenario 145 governs
private retention, not the failed-target attribution. Revision `v123` adds the
`Failed post-merge janitor target attribution` subheading and Scenario 167.
It requires every structured-summary target on outcome/journal surfaces, labelled
stdout/stderr observations when no summary exists, and the existing private
artifact reference. Only extracted target names are exempted from the bounded
excerpt limit; additional raw output is not. The existing retention sibling
`bd-ib-nezrrh` remains the prerequisite of `bd-ib-ma3fvj`.

Independent read-only Sonnet review ran in native session
`7a138771-a3b0-4f8b-906b-9a039a0453c8`, returning `NO BLOCKERS` at
15:02:46 UTC for canonical digest
`76b1ac1245a74198e41139d88a094e43157200b3acc6246c84c251b162ac0738`.
Scenario 167's integration coverage remains owed by existing `bd-ib-ma3fvj`.
Both reviews examined the exact resulting-file delta and each digest was
independently recomputed before the normal revise CLI accepted it.
The two unrelated pending proposals were left untouched.

The post-revision gap detector enumerates whole changed files, rather than only
the new clauses. The new clauses were handed to their existing children with
read-back comments, and the unrelated candidates were skipped. The detection
anchor therefore records attempts and correctly withholds completed coverage:
`the declared scope was covered only partially`. This is not a whole-repository
gap audit or a claim that the other untracked clauses are implemented.

## The resumed review strengthened the proof obligations

The resumed race review reproduced another interleaving: a new run stamp arriving
during artifact export, after the candidate's journal recheck but before cancel,
still allowed that newest run to be cancelled. The normal disposition accepted
that finding and routed it into `review_fix`.

The final-plan probe draft now injects the stamp during export as well as during
inventory. Against the original preserved `gh5xwq` candidate, the inventory case
preserved the new run and the positive control cancelled the older run, but the
export-time case cancelled `01NEW` and failed its assertion. This establishes that
the stronger probe can detect the defect; it does not establish the final repair.
The final released-artifact capture must rerun all three cases successfully.

The resumed credential-isolation review found that a proof helper could print a
selected token value if its refusal regressed. Its disposition accepted the
finding and routed it into the normal fix/recapture loop. Future proof must
report only booleans or counts on that path, including when the control fails.
No credential-bearing output is reproduced here.
