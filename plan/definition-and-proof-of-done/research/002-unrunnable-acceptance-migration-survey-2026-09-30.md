# S9 migration — the affected already-filed population, and how to enumerate it (2026-09-30)

Written by the `bd-ib-3nq2tn` factory run (S9 of plan
`definition-and-proof-of-done`, epic `bd-ib-7sjdzv`) alongside the code
change that excludes an unrunnable `ready` row from every
dispatch-candidate enumeration.

## 1. What S9 changed, so the survey's subject is unambiguous

S2 (`bd-ib-uczggw`) landed the shared variant-aware acceptance-eligibility
decision, the host-side Definition-of-Done wall, and the
`hygiene:unrunnable-acceptance:<work-item-id>` fact. What it did NOT land is
the other half of the ratified migration posture — that an affected physical
`ready` row "stays in place, is excluded from every dispatch-candidate
enumeration, and is surfaced by the … fact until repaired". Before S9 three
enumerations still advertised such a row:

| Surface | Before S9 | After S9 |
| --- | --- | --- |
| `next` | ranked it, and counted it in `pagination.total` | absent from both |
| the needs-attention implementation item composed from `next` | handed the operator `impl:<id>` | composes nothing for it |
| the idle-factory handoff | counted it, and advertised the first ranked such id | reads all three subjects off the filtered set |
| the Dispatcher drain (autonomous pass) | selected it, then the wall refused the WHOLE WAVE with exit 5 | never selects it |

The drain row is the operationally significant one. A wave-level exit-5
refusal means ONE unrepaired legacy row sitting at the top of the ready queue
stops every conforming item behind it — the queue reports a factory failure
rather than an item needing repair. The wall is unchanged for a NAMED id
(`dispatch --item`, and `loop --item`), which is the clause's own
"an explicit hand-picked dispatch remains protected by this refusal even when
candidate enumerations filtered the item earlier".

## 2. The survey instrument

The affected set is, by definition, every item the shared decision refuses
while it physically rests in `ready`. That is exactly the population the
`hygiene:unrunnable-acceptance:` fact enumerates, so the survey reads the
fact lane rather than re-deriving the condition:

```bash
with-livespec-env.sh -- python3 \
  /data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/needs_attention.py \
  --project-root /data/projects/livespec-orchestrator-beads-fabro --json \
  | jq -r '.items[]
           | select(.id | startswith("hygiene:unrunnable-acceptance:"))
           | [.source_ref.work_item, .summary] | @tsv'
```

**Do NOT hand-roll this as a `bd list --json` filter.** A filter would have to
re-implement the section parse, the reference resolution and the
workflow-variant preview, and the effective-acceptance-criteria clause forbids
a second composition of exactly those three for exactly this reason: the survey
would then disagree with the wall, and the disagreement would look like a clean
answer. The command above consumes the ONE decision, so its output is the same
verdict the dispatcher acts on.

### An independent second reading

The instrument above and the wall share one decision by design, so agreement
between them is not corroboration — it is one measurement taken twice. A
genuinely independent count comes from a DIFFERENT surface and a different
population:

```bash
# physically `ready`, counted off the raw ledger:
with-livespec-env.sh -- bd list --status all --limit 0 --json \
  | jq '[.[] | select(.status == "ready")] | length'
# what `next` will advertise, counted off the ranked envelope:
with-livespec-env.sh -- python3 .../bin/next.py \
  --project-root /data/projects/livespec-orchestrator-beads-fabro \
  --json --limit 1 | jq '.pagination.total'
```

The DIFFERENCE between those two numbers is the affected count as computed by
a surface that never touches the fact lane. It is not identical to the fact
count in general — `next` also excludes a row whose `depends_on` resolves to
`OPEN`, and the fact lane does not — so read a divergence as blocker
exclusions to be listed, not as an instrument fault. Note `--status all` is
load-bearing in the first command; without it `bd list` silently hides every
closed row.

## 3. The enumeration is HOST-ONLY, and this run measured that

The id list below is EMPTY because this run could not produce it, not because
the affected set is empty. The factory sandbox has no route to the tenant, by
deliberate design (the plan's own capability survey records the three blocks:
no `bd`, no `BEADS_DOLT_PASSWORD`, and `127.0.0.1` is the container). Measured
inside this run's sandbox on 2026-09-30:

- `which bd` → exit 1, nothing on `PATH`; `/usr/local/bin` holds only
  `livespec-step-timer`, `sccache`, `sccache-or-rustc`.
- `printenv BEADS_DOLT_PASSWORD | wc -c` → `0`.
- Invoking the survey command's own entry point,
  `python3 .claude-plugin/scripts/bin/needs_attention.py --project-root "$PWD"
  --json`, printed `livespec: required credential env absent; re-invoking under
  credential_wrapper` and then died with
  `FileNotFoundError: [Errno 2] No such file or directory:
  '/usr/local/bin/with-livespec-env.sh'` — the wrapper the prerequisites
  require is not provisioned in the sandbox.
- A TCP probe of `127.0.0.1:3307` raised `ConnectionRefusedError`, and
  `host.docker.internal` did not resolve.
- The nine sibling clones under `/workspace/siblings` are source checkouts and
  carry no ledger export.

Each of those is a clean, unambiguous negative rather than an empty result that
could be read as "nothing affected" — which is the distinction this repository's
own verification discipline turns on.

## 4. The affected items

**NOT YET ENUMERATED — owed by one host-side run of the §2 command.**

Paste its output into the table below, one row per id, and record the date of
the run. The `summary` each row carries already states the resolved
effective-criteria source and the gradeable-assertion count, which is what says
WHICH repair applies: a row resolved from `criteria-field` or
`description-exit-criteria` has criteria in a legacy place and needs them MOVED
into a `## Definition of Done` section, while a row resolved from
`description-definition-of-done` that is still refused has a section whose
reference line is missing or does not resolve.

| Work-item id | Resolved criteria source | Gradeable assertions | Repair |
| --- | --- | --- | --- |
| _(pending the host run)_ | | | |

This section is the one part of S9's Definition of Done that a factory run
structurally cannot discharge, and it is recorded as outstanding rather than
reported as empty.

## 5. Why there is no backfill and no exemption list

The clause is explicit that affected rows "are not backfilled or exempted", and
the implementation honours that by consulting nothing but the item and the
repository: there is no cutoff instant, no `captured_at` comparison, and no
per-id allowlist anywhere in the decision or in the filter S9 added. So an item
filed months before the wall existed is excluded exactly like one filed today,
and the ONLY exit is authoring the section — at which point the fact clears and
all four surfaces restore the row in the same pass. Both halves are asserted in
`tests/livespec_orchestrator_beads_fabro/commands/test_acceptance_eligibility_candidate_wiring.py`,
with the clearing case reusing the same id as every exclusion case so it
discriminates against a filter that would exclude an id permanently.

The grooming consequence for the maintainer: the affected rows do not need a
migration pass, they need editing, and until they are edited they cost nothing
but a hygiene row each — the queue moves past them.
