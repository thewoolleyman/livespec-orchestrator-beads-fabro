# Work-item authoring traps: prior art, criteria, riders and template text

Moved word for word from `AGENTS.md` §"Beads runtime prerequisites" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

**Query the ledger for prior art BEFORE designing a fix — reading the source is
not sufficient.** Scan every item — **including `closed` ones** — for the defect
class you are about to
design for, and read the FULL description of anything that overlaps: maintainer
rulings and explicitly rejected options are recorded there and are binding
context. **Include `acceptance` and `blocked` items, not just `backlog`** —
parked items are where shipped-but-unaccepted work hides, which is precisely what
a source-only reading cannot see. **`closed` items matter just as much**, because
that is where "this was already built" and "the maintainer already ruled on this"
live; a prior-art scan that skips them re-litigates settled work. This means the
scan MUST use `--status all` per the survey note above — the bare `bd list` form
cannot see closed items at all. (Cost of skipping THIS, 2026-08-19: a session
filed a restore-test finding against `dolt-server` reporting "no prior art",
having surveyed 4 of that tenant's 72 items with the bare form. The real prior
art — `dolt-server-ckue2g`, a closed Phase 2 item recording an end-to-end
validated restore pipeline — was invisible to the command it had been told to
use, and the filed item had to be corrected after the fact.) Treat each filed item as a claim with a
timestamp, not as fact; verify its specifics against the forge before relying on
them. (Cost of skipping this, 2026-07-26: the `dispatch-claim-liveness` thread
verified the code exhaustively, published two design recommendations to a durable
handoff on `master`, and had to retract both — `bd-ib-lza6` sat in `acceptance`
having already shipped the `reconcile-merged` valve that one recommendation would
have broken, and a filed item asserted a dispatch produced "no PR" when its PR had
in fact merged.)

**Write acceptance criteria as `- ` bullets, one assertion each, ending in a
period — and verify the parse before filing.** The evaluator grades the
criteria field one gradeable assertion at a time, and `criteria_lines`
(`commands/_dispatcher_acceptance_criteria.py`, since `e4db2e5d`) segments by
CONTENT, not by line: only a blank line, a list marker, or a header starts a
block, and each block is then split into sentences. A flush-left line with no
marker CONTINUES the previous block, so the older advice here — "one unwrapped
assertion per line" — now produces the opposite of what it promises. Measured
2026-08-31 on `bd-ib-6up7oj`: nine plain lines with no markers and no terminal
periods parsed as ONE assertion; the same nine as `- …` bullets each ending in
a period parsed as nine. Keep explanatory prose, rationale, and provenance in
the description or a comment, and do not write negative criteria ("no file
contains X") — the judge passes on literal diff vocabulary and a negative has
none. Check the result with `effective_criteria(item=...).parse_display()` (the
capture and groom front-ends print it) and apply all of this at FILING time,
because the evaluator reads the dispatch-time criteria snapshot, so editing an
item mid-run cannot rescue an in-flight dispatch. The underlying defects and
measurements are tracked in `bd-ib-tfpdya` and `bd-ib-5z0g`.

**And keep every criterion inside the MERGED DIFF'S OWN VOCABULARY — a criterion
naming an artifact the diff never mentions cannot pass, however true it is.**
This is the sibling of the rule above and it defeats that rule's remedy: the line
can be a single, unwrapped, genuine assertion and still fail. `_judge_criterion`
passes a criterion when ANY of its significant terms appears literally in the
normalized merged diff (the mechanism `bd-ib-5z0g` records), so a criterion whose
subject is a `SPECIFICATION/` scenario, a plan file, or a sibling work-item fails
with `insufficient merged diff evidence` — the SAME string a genuinely unmet
assertion produces, which is why it reads as a real defect rather than as a
mis-aimed instrument.

Measured 2026-08-26 on `bd-ib-ujihbw.2`, merged as PR #1867: ten of eleven
criteria passed on merged-diff evidence and the eleventh — "Scenario 83's two
scenarios pass against the implementation." — failed TWICE, burning BOTH
`acceptance_rework_cap` attempts on correct, already-merged work. Rewording it to
drop its cross-item demand changed NOTHING, because it still named the scenario
and so still had no diff vocabulary; only REMOVING the reference works. The
control is clean: `bd-ib-ujihbw.1` and `bd-ib-ujihbw.3` carry ZERO scenario-naming
criteria and both passed acceptance and closed on their first pass.

So never put a `## Scenario NN` reference in the acceptance-criteria field of a
factory-dispatched item. Scenario traceability belongs in the description, and
binding a scenario heading to an exercising test is its own integration-tier
deliverable (`bd-ib-w3if5j` for the v071-v079 range), never a by-product of the
implementing item. Note the second-order trap, because it is the expensive half:
when the item that owns the binding must land LAST — its closing criterion being
that no coverage entry still names it — an implementing item whose criteria demand
that binding is unsatisfiable in BOTH directions, and no re-dispatch can break the
circle. The live defect class is `bd-ib-99a1`.

**Before IMPLEMENTING an item, read its comments — `bd show` does not carry
them.** The rule above is about scanning the ledger for prior art. This one is
narrower and catches a different miss: RIDERS ARRIVE ON A WORK-ITEM AFTER IT IS
FILED, they are binding scope, and NEITHER the description NOR the
`acceptance_criteria` field announces that any exist. `bd show <id>` renders a
`COMMENTS` section, but `bd show <id> --json` carries only `comment_count` (see
the beads-trap catalogue above), so an agent reading an item through the machine
surface sees no sign of them at all. Run `bd comments <id> --json` on the item you
are about to build, not just `bd show`.

*Cost of skipping this, 2026-08-21:* `bd-ib-cfncp5` was implemented and merged
covering THREE traps when three riders — filed at 01:10:09Z, 01:43:27Z and
01:55:34Z, all before the work started — had raised it to FOUR and supplied a
sharper formulation for the fourth. The implementing session read the description
and the criteria, rewrote those criteria with the item open in front of it, and
still never read the comments; its rewrite then encoded "all three traps" as the
bar, locking the omission into the very field acceptance is judged against. It
took a second pull request to finish, and the miss was caught by a peer session
rather than self-announced. Note the shape: the session's own verification grepped
merged `AGENTS.md` for the three trap markers it knew about, found all three, and
passed — an instrument pointed at the wrong population, which is exactly the fourth
trap in the catalogue above.

**Ledger text can permanently destroy an item's dispatchability.** The rendered
run goal is assembled from the item's title, description, acceptance criteria,
notes, lessons and ledger comments. A safety check scoped only to the obvious
title / description / acceptance trio can therefore pass an item whose later
goal render is already poisoned. Run this check before dispatching, and before
commenting on any item that discusses templating:

```bash
python -c 'import json, subprocess, sys; issue=sys.argv[1]; fields=json.loads(subprocess.check_output(["bd","show",issue,"--json"], text=True))[0]; comments=json.loads(subprocess.check_output(["bd","comments",issue,"--json"], text=True)); needles=(chr(123)+chr(123), chr(123)+"%", chr(123)+"#"); hay="\n".join(str(fields.get(k,"")) for k in ("title","description","acceptance_criteria","notes","lessons"))+"\n"+"\n".join(str(c.get("text","")) for c in comments); hits=[n for n in needles if n in hay]; raise SystemExit(("template opener present: "+repr(hits)) if hits else 0)' <item-id>
```

An opener anywhere in that assembled text has two bad outcomes: the dispatch can
die before any Fabro run exists, with an error that names the workflow file and
reports a line number that is really an offset into the generated goal; or, if
the restored token happens to be valid, it can silently rewrite the brief with
no error. Ledger comments make this permanent: `bd comments` offers add and
list, with no edit or delete, so a poisoned comment can only be escaped by
filing a clean-text successor item. The trap fires on prose about itself; quoting
the failing evidence verbatim is good incident filing practice and is exactly
what destroys the record. Three records have already been lost this way.
To write about the token safely, substitute U+27E6 for the literal open
interpolation pair and U+27E7 for the literal close pair, and state on the
record that this substitution is in force. This convention is owned by
`livespec-dev-tooling-9yb4`, so the fleet converges on one form rather than
private notations. It matters most in LEDGER COMMENTS, because a comment cannot
be repaired after the fact.
`bd-ib-ai9a` is the live P1 carrying the mechanism and Fabro-side fix, and
`bd-ib-pgne` is the orchestrator-side pre-flight refusal.
