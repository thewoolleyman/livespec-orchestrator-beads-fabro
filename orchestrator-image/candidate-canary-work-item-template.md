# Candidate-canary fixture work-item template

This file is the committed FIXTURE a candidate canary is filed from. A canary
exists to measure the ENGINE — a candidate Fabro build, a re-pinned carrier, a
restarted factory host — so the brief it carries must be one whose Definition of
Done is already known to pass. Canaries 5 and 6 of plan `fabro-currency` (runs
`01M4NWARSD8T` and `01M4PBFW4MP8` on hp-candidate, 2026-10-11) reached the
`dod_gate` node and were refused, because the canary reused a real backlog item
whose `References` line named a heading that governs something else. That is an
item-quality failure that reads exactly like an engine failure, and the second
canary repeated it. A fixture removes the whole class.

The runbook section `### Taking a candidate canary` of
`orchestrator-image/README.md` names the recipe that files and dispatches a
canary from this template, and the recipe is the only sanctioned way to take
one: filing by hand is how a canary acquires an unreviewed brief again.

## How this file is read

`livespec_orchestrator_beads_fabro.commands.take_candidate_canary` reads two
field markers, each matched as a line of its own so that a mention of either in
prose — always written in backticks, as here — cannot be mistaken for the
marker:

| Marker | Meaning |
|---|---|
| a line beginning `TITLE:` | the rest of that line is the work-item title |
| a line that is exactly `DESCRIPTION:` | every line after it, to end of file, is the work-item description |

Two placeholders are substituted at filing time. They are deliberately NOT
doubled-brace template tokens: such a token anywhere in a work-item's own text
makes the item undispatchable, because graph construction then fails on a
template variable that appears only in the record.

| Placeholder | Substituted with |
|---|---|
| `@@CANARY_ID@@` | the minted work-item id |
| `@@CANARY_FACTORY@@` | the configured factory name the canary dispatches to |

The description below carries NO heading before its `## Definition of Done`
heading, which is load-bearing: the ratified parse reads the section only when
it is the description's FIRST heading, so a heading added above it would make
the item carry no Definition of Done at all.

TITLE: Record candidate canary @@CANARY_ID@@ in the candidate-canary log

DESCRIPTION:
This work item is a FIXTURE, filed mechanically by the candidate-canary recipe.
It is not a backlog item and it carries no product change: it exists so that a
candidate engine, a re-pinned carrier build or a restarted factory host can be
exercised end to end — Definition-of-Done gate, implement, janitor, review,
publish, merge — against a brief that is known to be gradeable.

The whole change is ONE appended line in the candidate-canary log at
`orchestrator-image/candidate-canary-log.md`, which is the factory-ops record of
which candidate canaries have been taken. Append exactly the entry named in the
assertion below as that file's LAST line. Leave every entry already in the file
as it stands, and change nothing else anywhere in the repository: a canary whose
diff carries unrelated edits measures those edits rather than the engine.

The log's entry format is enforced by the repository's own check suite, so an
appended line that does not match the format fails the janitor gate rather than
merging quietly.

## Definition of Done

- The file `orchestrator-image/candidate-canary-log.md` carries, as its last line, the entry `- @@CANARY_ID@@ candidate canary dispatched to factory @@CANARY_FACTORY@@`.

References: ## Fabro runtime constraints
