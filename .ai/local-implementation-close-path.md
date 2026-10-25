# Closing a work item implemented in-session, and profiling the attention surface

Recorded 2026-10-25 from the close paths of bd-ib-36d3x5, bd-ib-k3nmbi,
bd-ib-xbll72, bd-ib-m2fb2g and bd-ib-tzbdd3 (epic livespec-dev-tooling-dfixhe),
all implemented in a session because the factory and the operator attention
surface were both down. The factory path writes every proof record and
lifecycle move itself; the local path has to supply each one by hand, and each
refusal below looked like a defect the first time it fired.

## The pull request: `factory-override` reaches CI only on the SECOND event

`check-factory-provenance` refuses a non-factory pull request that touches
product `.py` unless it carries the `factory-override` label and the body
states the reason. The check reads the label from the EVENT PAYLOAD, not from
the pull request:

- `gh run rerun` replays the original payload, so the rerun fails identically.
- `gh pr create --label factory-override` does not help either: `gh` adds the
  label in a second API call AFTER the `opened` event has fired, so the first
  CI run sees no label (PR 3657, 16:10Z).

Create the pull request, then `gh pr close` + `gh pr reopen` it once, and watch
the SECOND run. Put the work-item id in the title so `reconcile-merged`
resolves the pull request unambiguously.

## `reconcile-merged` admits `ready`; the acceptance pass parks at NEEDS_ATTENTION

`_RECONCILE_MERGED_ALLOWED_STATUSES` is acceptance, active, backlog, ready,
blocked and pending-approval. An item a maintainer released with
`resolve-blocked:<id>:ready` therefore reconciles directly; no status workaround
is needed. The acceptance pass then parks the item at `acceptance` with verdict
NEEDS_ATTENTION, which is EXPECTED for in-session work: its proof leg grades a
`verified` record tied to a factory run id, and none exists. With no host or
human leg declared, `drive --action accept:<id>` closes the item. With a
host-captured assertion declared, `.ai/host-captured-proof-replay.md` applies.

## A host-captured assertion that fails on the capturer's run is NOT narrowed

tzbdd3's host-captured assertion (the whole surface within 900 s) did not
reproduce on the released build even though the item's own two assertions held.
Coordinator ruling: do NOT rewrite the assertion to what the change controls —
after a failed capture that reads as moving the goalposts. Leave the item
parked at `acceptance`, link the real blockers with `bd dep add <item>
<blocker>` (a `blocks` edge), record the scoped measurements on the item, and
capture once the blockers release.

## Filing follow-ups through `intake_dor.file_captured_work_item`

- The seam takes about FIVE MINUTES PER ITEM on the live tenant (the intake
  Definition-of-Done wall judges each item). A `timeout 600` on a three-item
  script killed it between item 2's `append_work_item` and its
  `apply_intake_dor`: the item existed at `backlog` with no `intake:triaged`
  label and no routing comment, item 3 was never created, and buffered stdout
  was lost. File one item per script, `python3 -u`, in the background, no
  timeout. Complete a half-filed item by calling `apply_intake_dor(path,
  item_id, checklist)` once — it had not run, so this is not the forbidden
  second routing pass.
- An item intake routes to `pending-approval` under `admission: auto` is held
  by a judgement finding (comment `livespec-dod-judgement`, outcome
  `rests-at-needs-human`), typically "the References line does not name
  `## <governing heading>`". Apply the remedy verbatim with `bd update <id>
  --body-file`. Do NOT reach for `drive --action approve:<id>`: it refuses
  ("approve requires an effective-manual pending-approval item") by design.
  The dispatcher's admission pass re-judges on the new subject digest and
  auto-approves the item to `ready` at dispatch (`plan_admissions`, journal
  disposition `auto-approve`).

## Profiling `needs_attention.py` when it exits 124 at its 900 s budget

A timed-out surface prints NOTHING on stdout; the `bd exited zero with stderr`
lines on stderr are one per guarded `bd` call (429 on 2026-10-25). An `strace`
attributes the time to subprocesses but never names the Python call site. Two
in-process probes do, and both run from the INSTALLED build so they measure
what operators run:

1. Per-gather profile. `sys.path.insert(0, "<build>/scripts/bin")`,
   `from _bootstrap import bootstrap; bootstrap()`, wrap every callable in the
   `commands.needs_attention` module namespace with a timer, and monkeypatch
   `subprocess.run` and `subprocess.Popen.__init__` to log argv and duration;
   attribute each subprocess to the innermost open gather. `subprocess.run`
   also fires `Popen.__init__`, so raw popen counts double the run counts.
   Give the probe its own `SIGALRM` watchdog that dumps the log — the full
   surface exceeded 1500 s on this tenant.
2. Call-site trap. Every `bd show` and `bd comments` argv in the package is
   built in `_beads_client.ShellBeadsClient.show_issue` and `.list_comments`.
   Trap THOSE (not `BeadsClient`, which is a `typing.Protocol` and silently
   un-trappable), print the livespec frames of `traceback.extract_stack()`,
   and raise; run each slow gather on its own.

What the probes found on v0.243.2 (1,649 items, 44 blocked, 33 open epics):
one call site — `acceptance_eligibility -> criteria_wall_variant ->
previewed_workflow_variant -> dispatch_workflow_for` — issued 335 `bd show`
from three gathers (bd-ib-gqrrgq); `held_definition_of_done_items` issued one
`bd comments` per heldable item, 282 of them (bd-ib-hm4obe); `human_valves`
ran one `fabro inspect` per blocked needs-human item (bd-ib-ltfh5p). The
per-item read is the shape to look for: a value already present in the `bd
list --status all` records every gather has loaded, re-read per item through a
guarded `bd` invocation costing 1.4–4.6 s each.
