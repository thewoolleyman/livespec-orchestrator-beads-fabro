---
topic: incident-authority-cli-usage-errors
author: claude-opus-5-5:expedited-incident-hardening
created_at: 2026-11-13T05:40:58Z
---

## Proposal: The incident authority CLI's reply clause covers parsed actions only, an invocation that fails argument parsing exits 2 with no reply, and Scenario 365's moved-head case asserts exit 78

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two small corrections to the text revise v366 (incident-authority-cli-reply-and-fenced-reads, livespec-orchestrator-beads-fabro#5125) added. (1) In contracts.md §"Expedited incident lifecycle", the reply clause says the CLI "MUST answer every action with exactly one JSON reply object". It becomes "every parsed action", and one sentence states what an invocation that fails argument parsing does instead: it is not an action, writes no reply object to stdout, prints its usage error on stderr, exits 2 and authorizes nothing. That is what shipped argparse handling already does. (2) In Scenario 365, the moved-head case gains the exit-78 observable its sibling refusal case already asserts, and one case is added for a read-current invocation that omits part of the fenced identity. No heading is added, removed or renamed.

### Motivation

legacy-coordinator-agent's ruling on the non-blocking notes of the independent re-review of revise v366 (2026-11-13, livespec-orchestrator-beads-fabro#5125, grade PASS-WITH-FIXES) asked for ONE small follow-up carrying two of them, filed at once so they are not lost.

Note (1): "MUST answer every action with exactly one JSON reply object on stdout" is literally untrue for an argument-parsing failure. `commands/incident_authority.py` `_parse` uses argparse, and `parser.error(...)` (a missing required argument such as `--owner`, an unknown action, a payload flag given to the wrong action, or `_IDENTITY_RULE`) prints usage and the error on stderr and exits 2 before any reply is built. Observed on orchestrator master 2026-11-13 ~05:20Z: `read-current` without `--owner` wrote 0 bytes to stdout, printed `incident-authority: error: the following arguments are required: --owner` on stderr, and exited 2. Such an invocation is not an action, but the clause should say so explicitly, so that nobody writes a test from it that contradicts the shipped code. livespec-dev-tooling's shared client already treats any exit other than 0 or 78 as the named refusal `incident-authority-exit`, so a usage error authorizes nothing in every existing consumer.

Note (3): Scenario 365's case "A head that moves after selection is refused" asserts the refusal and `authorizes_current_effects` false but not the exit code. The reply clause makes every refusal exit 78, and the case "A stale or partial fence is refused and authorizes nothing" already asserts it.

The re-review's note (2), that read-current's other chain-fault refusals are not enumerated, needs nothing: the text makes no exhaustive claim (coordinator ruling).

The added Scenario 365 case gives the new usage-error sentence the Given/When/Then that core revise split (i) requires, using the one input the read-current fence most often meets: an omitted part of the full fenced identity.

This proposal anchors on text that revise v366 adds. It is filed while #5125 awaits merge, and it is revised only after v366 is on master.

### Proposed Changes

### contracts.md

In `SPECIFICATION/contracts.md`, section `## Expedited incident lifecycle`, in the paragraph that begins "The incident authority writer's command-line interface MUST answer every action with exactly one JSON reply object on stdout":

- Replace "MUST answer every action with exactly one JSON reply object on stdout" with "MUST answer every parsed action with exactly one JSON reply object on stdout".
- Immediately after the sentence that ends "every reply that is not refused MUST exit 0.", insert:

> An invocation that fails argument parsing, such as one that omits a required argument, names an unknown action, or gives an action a payload argument it does not take, is not an action: it MUST write no reply object to stdout, MUST print its usage error on stderr, MUST exit 2, and authorizes nothing.

No other sentence of the paragraph changes.

### scenarios.md

In `## Scenario 365 — read-current verifies only the current head's full fenced identity and is the only action that authorizes a side effect`:

- In the case "A head that moves after selection is refused", insert `    And the reply's status is refused and the process exits 78` immediately after `    Then the reply refuses with the named reason incident-authority-changed`.
- Insert this case immediately before the case "No other action authorizes a side effect":

```gherkin
  Scenario: A read-current invocation that omits part of the fenced identity is a usage error, not an action
    Given an incident item with a current head
    When a caller runs read-current with the repository, the item id, the attempt id, the incident phase, the generation and the operation id but no owner
    Then the process exits 2 and prints a usage error on stderr
    And it writes no reply object to stdout, so nothing is authorized
```

No heading is added, removed or renamed in either file.

### Co-edit at revise

The Scenario 365 row of `tests/heading-coverage.json` (owned by bd-ib-txbv7i) gains the moved-head exit 78 and the usage-error observables in its reason. No row or debt entry is added or removed.
