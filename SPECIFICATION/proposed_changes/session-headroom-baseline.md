---
topic: session-headroom-baseline
author: claude-opus-5-5
created_at: 2026-10-21T11:44:09Z
---

## Proposal: Read the session-headroom baseline from a host-shared, credential-keyed assessment history

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The session-headroom projection currently takes its drain-rate baseline only from the dispatching checkout's own dispatch journal. On a host where many checkouts dispatch against one Claude credential, most assessments therefore find no in-window baseline and fail open, even though the host measured that credential minutes earlier from another checkout. This proposal makes every assessment also land in a host-scoped history keyed by the opaque credential identity. When the checkout's own journal holds no baseline, the baseline is taken from that shared history. The projection stays fail-open only when neither source holds a baseline, when the shared history cannot be read, or after a reset.

### Motivation

Measured 2026-10-21 in livespec-orchestrator-beads-fabro by the fabro-currency plan session d098b5c6 (plan epic bd-ib-6tcjfx), and raised by the coordinator in rulings R450 and R451. Six of the last eight session-headroom assessments in this checkout's dispatch journal recorded the projection as `unavailable` with reason no-baseline. That is how bd-ib-3f79 was admitted at 2026-10-21T11:27:41Z with no projection, while the same credential was being drained by dispatches from other checkouts on the same host. The current clause mandates this outcome: it says the history is per checkout, and it lists the cases where a dispatch runs from a checkout whose journal holds no assessment of the credential as deliberate fail-opens. So this needs a spec change, not a code fix. The coordinator's wording was 'read the drain rate for the same credential from the dispatch journals of every repository registered on the host'. The specification has no registry of the repositories on a host, and a committed list of other repositories' journal paths would be fragile. A host-scoped history keyed by credential identity, appended by every dispatching checkout, delivers the same population without a registry. This proposal complements the pending session-headroom-carried-drain-rate proposal (filed 2026-10-17) and does not supersede it. That proposal covers readings bunched inside one checkout, and this one covers history held by other checkouts. Its carried-rate lookup SHOULD read the same widened population if both are accepted.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Provider spend containment", paragraph "Admission filters candidates by projected Claude session headroom":

1. After the sentence "The journal MUST NOT contain credential values or raw provider responses.", insert:

"Every assessment journaled under this clause MUST ALSO be appended to the host session-headroom history. That is one history per dispatching host, held at an implementation-defined per-user location outside every checkout and worktree, and shared by every checkout that dispatches on that host. Each entry MUST carry the opaque non-secret credential identity, the utilization percentage or the explicit unobservable result, the local observation time, and the repository and checkout that journaled it. It MUST NOT carry credential values or raw provider responses. A failure to append to the host history MUST NOT refuse or delay the dispatch, and the dispatching checkout's journal record MUST name it. Entries older than 90 minutes MAY be pruned."

2. Replace the sentence beginning "The baseline is the EARLIEST assessment carrying a valid reading journaled under this clause for the same opaque credential identity in the dispatching checkout's dispatch journal" with:

"The baseline is the EARLIEST assessment carrying a valid reading journaled under this clause for the same opaque credential identity in the dispatching checkout's dispatch journal, read regardless of the work-item it was journaled for, whose observation time is no less than 15 minutes and no more than 90 minutes earlier. When the dispatching checkout's journal holds no such assessment, the baseline MUST be the EARLIEST entry of the host session-headroom history carrying a valid reading for the same opaque credential identity, journaled from any checkout, whose observation time falls in that same window."

3. Replace "The projection is unavailable when no such baseline exists, or when this reading's utilization is not higher than the baseline's (a window reset or a provider correction occurred between them)." with:

"The projection is unavailable when neither the dispatching checkout's journal nor the host session-headroom history holds such a baseline, when the host history cannot be read and the checkout's journal holds none, or when this reading's utilization is not higher than the baseline's (a window reset or a provider correction occurred between them). An unreadable host history MUST be journaled as its own unavailable reason, distinct from an absent baseline."

4. Replace the three sentences "The assessment history is per checkout, because it is the dispatching checkout's own dispatch journal. A projection is therefore unavailable in at least these cases: the credential was not assessed in that checkout during the preceding 90 minutes, the journal was removed, or the dispatch runs from another checkout or worktree whose journal holds no assessment of that credential. Each such case is a deliberate fail-open of the projection only, and the floor still applies." with:

"The assessment history is the dispatching checkout's own dispatch journal, widened by the host session-headroom history when that journal holds no baseline. A projection is therefore unavailable in at least these cases: the credential was not assessed on the dispatching host during the preceding 90 minutes, both the journal and the host history were removed, or the host history is unreadable and the checkout's journal holds no baseline. Each such case is a deliberate fail-open of the projection only, and the floor still applies. A dispatch from a checkout or worktree whose own journal holds no assessment of that credential MUST NOT, by that fact alone, journal the projection as unavailable while the host history holds a baseline."

5. In the sentence beginning "For each assessed credential, the journal record MUST additionally carry exactly one projection result:", replace "the drain rate, the baseline's observation time," with "the drain rate, the baseline's observation time, the baseline's source (`checkout-journal` or `host-history`) and, for a `host-history` baseline, the repository and checkout that journaled it,". A baseline from the host history MUST have exactly the semantics of one from the checkout's journal. The rate, the horizon, the floor, the skip semantics and the scheduling rule MUST apply to it unchanged.

In SPECIFICATION/scenarios.md, "## Scenario 60 — An observed provider exhaustion refuses admission, and expires" (the heading is unchanged, so tests/heading-coverage.json needs no change):

6. The sub-scenario "A credential with no baseline in this checkout is governed by the floor alone" MUST gain the step "And the host session-headroom history holds no assessment of its credential identity between 15 and 90 minutes earlier" after its existing journal step. It MUST otherwise remain unchanged.

7. Add, directly after it, these sub-scenarios, which MUST be satisfied:

```gherkin
  Scenario: A baseline journaled from another checkout on the host supplies the projection
    Given dispatcher.session_headroom_floor_percent is 20
    And dispatcher.session_headroom_horizon_minutes is 180
    And this checkout's dispatch journal holds no assessment of the primary credential between 15 and 90 minutes earlier
    And the host session-headroom history holds an assessment of that credential identity journaled 40 minutes earlier from another checkout at 45 percent utilization
    And the current reading is 61 percent utilization, so its remaining headroom of 39 percent passes the floor
    When the Dispatcher evaluates admission
    Then the journal records a drain rate of 24 percentage points per hour with baseline source host-history naming the other checkout
    And the projected exhaustion is about 98 minutes after the observation
    And the primary is skipped by projection, not by the floor

  Scenario: An unreadable host history fails open with its own reason
    Given this checkout's dispatch journal holds no assessment of the primary credential between 15 and 90 minutes earlier
    And the host session-headroom history cannot be read
    When admission is evaluated
    Then the projection is journaled as unavailable with the unreadable-host-history reason, distinct from no-baseline
    And no projection skip applies to that candidate
```
