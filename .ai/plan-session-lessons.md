# Plan-session lessons from the fabro-currency direction review (2026-10-10)

Operating notes a plan session needs before it proposes a direction,
files a child, or spins up a reviewer. They are repo-additive guidance in
the sense of AGENTS.md §"Progressive guidance"; the maintainer rule in the
first section was declared in conversation on 2026-10-10.

## Route by the goal, not by prior ledger text (maintainer-declared 2026-10-10)

Three proposals in one plan session were rejected in a row: forking Petri
for a per-run resource limit before asking whether the limit was needed;
closing upstream PR 576 before measuring that the candidate engine has no
OTLP code and that the ratified contract consumes the spans; and routing a
rewrite to a third plan because a 2026-10-08 disposition line named it.
Each came from repeating text already on the ledger (a disposition, a scope
event, an item status) instead of from the standing goals (stay current on
Fabro, carry only what the factory needs, contribute upstream, own our
compute) and from source measurements. Prior ledger text records what an
earlier session believed; all three lines were wrong.

Before proposing a direction, state in one sentence which goal it serves
and name the measurement that supports it. Treat a disposition or scope
line as a claim to re-verify, never as routing. When the maintainer asks
"why do we need X", answer the need first, then the mechanism. When more
than one plan is in scope, say which plan owns each piece every time.

The independent review that caught the rest is the pattern to repeat: a
summary of the direction written to a file, a read-only Codex reviewer on
the newest model asked for omissions, holes and the big picture, and each
finding verified against source before it is adopted. Research note
`plan/fabro-currency/research/008-independent-review-and-corrections-2026-10-10.md`
is the worked example, including five findings that overturned claims the
session had already made to the maintainer.

## Take the recorded next action; do not offer it as a picker (maintainer-declared 2026-10-14)

Resuming plan `dolt-server-failures` with `/plan <slug>`, the session
finished scoping, recorded `impl:bd-ib-zlkjm4` as the typed next action,
and then offered that same dispatch as option 1 of a three-way picker
("dispatch and keep going / this one only / stop"). The maintainer's
answer was: "Why the fuck are you asking me rather than just fixing the
problem?"

`resume_directive` reports `ask: True` on an attended resume that has no
current continuation ruling, and plan.md says that case "presents the
picker". Read that as what the PRIMITIVE reports, not as an instruction
to interrupt the maintainer. A maintainer who invoked `/plan <slug>` has
named the goal, so AGENTS.md's "a recorded next action is an instruction,
not a menu" and "drive authorized work to completion" govern. Take the
executable next action, record a `PlanContinuationAuthorization` scope
event so the ledger carries the ruling, and report the outcome. Ask only
at genuine human gates: confirming SESSION-DERIVED Definition of Done
assertions, a restart or rollout on shared infrastructure, or any other
irreversible or outward-facing act.

A related primitive gap from the same session: `reparent_plan_child`
moves a child OUT of a plan (it removes the edge to the plan epic), so
it cannot adopt an existing parentless item INTO one. Adopt with
`make_beads_client(config=...).add_dependency(from_id=<item>,
to_id=<epic>, edge_type=EDGE_PARENT_CHILD)` plus an explanatory epic
comment. A duplicate that must be closed can then go through
`close_plan_child`, which writes the rationale on both records.

## No pickers at all; the coordinator answers for the maintainer (maintainer-declared 2026-10-18)

The section above still leaves "genuine human gates" open. On 2026-10-18
a `petri-factory-on-gmktec` session ended two reports by asking the
maintainer to decide (whether to release a protected Claude account,
and whether to accept a coordinator's delegated authority). The
maintainer's answer: "Yes the coordinator can answer your pickers
because that will unblock you. Otherwise you will just get stuck and
you shouldn't be presenting pickers anyway. I've already told you not
to."

So a plan session presents NO picker and ends no report on a "your
decision" question. When a choice genuinely needs maintainer authority,
send it by `SendMessage` to the fleet coordinator session
(`gitops-fleet-capacity-monitoring`), and act on its answer as the
maintainer's own. A peer answer still grants no permission and no
store-write consent beyond the plan's standing autonomy rulings. The
ruling is recorded on epic `bd-ib-fyozyd` as scope event
`petri-ruling-no-pickers-coordinator-answers-for-maintainer`.

## On every resume: read every ruling, start every track, smallest canary first (maintainer correction 2026-10-18)

The same session resumed with `resume_directive` returning one `await`
pointer, read only the last three timeline entries, and so never saw two
binding scope events on the epic (`petri-ruling-throughput-optimize-autonomously`
and the session-ratifiable spec ruling). It then ran a large real item,
`bd-ib-7rnipp`, ALONE as the factory canary. `dod_gate` refused it twice,
because it needed new spec vocabulary, while host proofs and a spec route
that depended on nothing sat idle. The maintainer: "why wouldn't you be
testing with the smallest canary possible ... fail-fast and quick
feedback loops?" and "I had already previously told you to parallelize
everything possible."

Before acting on the pointer:

- Read EVERY scope event on the epic, not only the latest handoffs.
  Rulings live there. `bd-ib-ghijrt` makes `resume_directive` return them.
- List every remaining track, and start every one that depends on no
  other in the same turn, through forks, detached gates or dispatch loops.
- Prove a pipeline with the SMALLEST dispatchable item first (here a
  doc-only item, `bd-ib-knnhbn`, which went from dispatch to closed on its
  first admitted run), and run any real item beside it. A canary named by
  an inherited handoff does not override this.
- Each time you arm a wait, say in the same reply what else is running.

Per-session agent memory is NOT a carrier for this kind of lesson in this
repository. A PreToolUse hook refuses memory-file writes, and routing
around it through a shell command defeats it. Put durable guidance here
or in AGENTS.md.

## Spinning up a Codex reviewer in a herdr pane

"Astra" is OpenAI's `gpt-6-astra`; it is the default model in
`~/.codex/config.toml` on this host, but pass it explicitly. Measured
2026-10-10 on Codex CLI 0.162.1:

```bash
herdr pane split --current --direction right --cwd <repo> --no-focus   # returns pane_id, e.g. w6:p3
herdr agent start <name> --kind codex --pane w6:p3 --timeout 90000 -- -m gpt-6-astra --dangerously-bypass-approvals-and-sandbox \
  'Read tmp/<brief>.md in this repository and do exactly what it says.'   # the job rides the launch, nothing is typed in later
herdr agent wait w6:p3 --until idle --timeout 2400000   # background it; returns when the agent is idle
herdr pane close w6:p3                                  # close the pane when its job is done
```

The 2026-10-10 run submitted the brief with `herdr agent prompt w6:p3 "$(cat brief.txt)"`
after the start; that form is retired by the 2026-10-14 ruling in
`.ai/herdr-helper-sessions.md` (another session's pane is never typed into), and the
launch-argument form above has not yet been re-measured on this Codex build, so confirm the
agent picked up the brief before waiting on it.

Give the reviewer a read-only brief with the exact source paths, ask for a
ranked critique written to a file plus a sentinel line, and close the pane
once the file is read: the maintainer asked "Why do you still have the
separate Codex pane open? Do you still need it?" after a replay pane sat
idle, and a later host replay must come from a freshly started session
anyway. `herdr agent get <name>` returns nothing once the pane is back at a
shell; `herdr pane list --workspace <ws>` shows the state, and
`herdr workspace list` maps workspace ids to labels (w6 is `fabro`).

## Plan-primitive gaps met while rewriting a ledger (plugin build a7a11fda01c0)

- `BeadsClient.update_issue` takes `description`, `status`, labels,
  `metadata`, `acceptance_criteria` and `notes`, and NO `title`. Retitle
  through the verb, `bd update <id> --title "..."`; inside a wrapped
  script a `subprocess` call inherits the wrapper's credentials.
- No primitive amends a plan epic's `## Definition of Done`. Rewrite the
  whole epic description with that section first (keep the
  `Plan anchor for plan/<slug>.` line), then record a scope event WITH
  `carriers=` mapping every assertion ordinal; without the carrier block
  the re-wording is unrecorded.
- `create_thread(project_root=...)` writes the research note and the
  anchor under `project_root`. Create the worktree first and pass its
  path, or the files land on the primary checkout.
- `apply_intake_dor` routes a factory-safe item to `pending-approval` and a
  host-routed one to `ready`; `drive --action impl:<id>` admits and
  dispatches a pending-approval item in one step.
- Write ledger scripts with idempotency markers (a comment carrying a
  marker string, checked before each mutation) so a partial run can be
  re-run without double-filing.
- `append_handoff`, `append_supervisor_handoff` and `set_next_action`
  RETURN a `NextActionRefusal` instead of raising. When a script ignores
  the return value, nothing is written and nothing is reported. Since
  plugin v0.189.0 every new pointer of an executable kind must carry
  `required_result` (a typed result reference such as
  `{"repo": "<project dir name>", "item_status": {"item_id": "<id>", "status": "closed"}}`)
  and `budget` (`{"deadline": "<UTC ISO>Z", "max_handoffs": <positive int>}`).
  A legacy three-key pointer is refused with "required_result and budget
  must be recorded on every new write". Measured 2026-10-12 on
  `bd-ib-ctagnf`: a handoff script printed success, and only the
  `read_timeline` read-back showed the entry was absent. Check the return
  value, then compare the read-back body for equality.

## An unrelated finding gets its own plan (maintainer-declared 2026-09-30)

When a plan session surfaces a defect or design question that is not the
plan's topic, it gets a NEW plan, driven from a different session; it is never
folded into the current plan's next action. On 2026-09-30 the factory
test-first finding surfaced while a dispatch was being watched under the
fallback plan `bd-ib-jxvgq5`, and the predecessor session wrote it into that
epic's `next_action`. The maintainer's first words were "we're not going to do
that as part of this plan. This plan is completely unrelated. We need a new
plan." A plan epic is the durable resume state for exactly one topic, and an
unrelated next action derails the unattended resume and hides the finding
from the session that should own it. Research the finding, `create_thread` a
new plan with an opening research note, append its opening handoff, then
append a handoff on the ORIGINAL epic that discharges the misplaced pointer and
names the new epic, and return to the original plan's own queue.

## Importing the plan package and core's governance journal from a script

Driving the plan operation's package primitives (`read_timeline`,
`append_handoff`, `record_scope_event`, `resume_directive`,
`plan_record_rate_warnings`) from a script needs BOTH the scripts directory
and its `_vendor` directory on `sys.path`:

```python
sys.path.insert(0, ".claude-plugin/scripts")
sys.path.insert(0, ".claude-plugin/scripts/_vendor")
from livespec_orchestrator_beads_fabro.commands import plan as P
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
cfg = resolve_store_config(cwd=Path(".").resolve(), work_items_arg=None)
```

With only the first path the import fails with `ModuleNotFoundError: No
module named 'livespec_runtime'`, because `livespec_runtime`, `returns` and
`typing_extensions` are vendored rather than installed; the error names the
module, not the missing path, so it reads as a broken install. Run the script
under `with-livespec-env.sh --` or the beads calls underneath fail with an
access-denied that looks like a missing secret. Measured 2026-08-22.

Call shapes measured 2026-10-01 on build v0.158.0:
`is_unattended_session(env=os.environ)` takes a keyword-only `env`;
`plan_record_rate_warnings(entries=..., research_paths=...)` needs `Path`
objects, not strings; `archive_thread(...)` accepts a worktree as
`project_root`, which keeps the primary clean while it renames `plan/<slug>/`
and closes the epic in the same call; and
`record_completeness_review_evidence` (now in
`commands/_plan_completeness_evidence.py`; it was in
`commands/_plan_archive_review.py` when measured) is valid only with `separate_reviewer=True`,
`attests_complete_requirement_coverage=True` and a `reviewer_identity`
different from the archiving author.

livespec core's governance journal has the same trap. To append the batch-mode
`authoring_auto_consumption` event that the propose-change prose requires
before invoking the CLI, put core's `scripts` AND `scripts/_vendor` on
`sys.path` (the core root comes from the Driver's
`lib/resolve_core_root.py --project-root .`); without `_vendor` the error
names `structlog`:

```python
sys.path.insert(0, f"{C}/scripts"); sys.path.insert(0, f"{C}/scripts/_vendor")
from livespec.spec_governance import journal as J
digest = J.digest_json_bytes(payload=envelope)
J.append_journal_payload(project_root=Path.cwd(), event={...})
```

Required event fields: `event_type`, `operation` (`propose-change` or
`critique`), `governing_key`, `effective_source` (one of `hard-floor`,
`invocation`, `proposal`, `global`, `default`), `input_envelope_digest` (a
sha256 hex digest) and `outcome` (`consumed`, `spawned`, `selected`,
`blocked`, `failed`, `dismissed` or `deferred`). Raw `intent` or `topic`
fields are rejected; send digests only. The journal lands at
`tmp/livespec-spec-governance-journal.jsonl`, which is gitignored. Measured
2026-09-06 while filing the `pluggable-factory-workflow-configs` proposal.
These two sections were migrated from auto-memory notes on 2026-10-18.
