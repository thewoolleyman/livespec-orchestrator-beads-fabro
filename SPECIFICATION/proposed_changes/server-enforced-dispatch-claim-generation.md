---
topic: server-enforced-dispatch-claim-generation
author: claude-opus-5-5
created_at: 2026-10-25T01:22:27Z
---

## Proposal: Narrow the stranded-claim residual race to a bounded lease with a server-enforced, rotating claim token

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The "Residual race" bullet of "### Stranded claim release" accepts that every claim-changing ledger write is a client-side read-modify-write, and says closing the window requires a server-enforced claim generation tracked by bd-ib-jjws2. This proposal ratifies that mechanism. Every work-item names one current, single-use token record; every write that changes the item's status, `fabro` assignee or run stamp must first win `bd close` on that token (the one server-enforced compare-and-swap), read the close reason back, and then name a precommitted successor token in the same item write within a bounded lease. Losers write nothing. A crashed winner's successor is taken over after the lease, and the cutover is a committed configuration key flipped only after a paused, idempotent migration. Because the item write itself stays non-conditional at the server, the proposal states the one remaining residual class exactly: a winner's in-lease write that the server applies only after a takeover of its successor has begun, with no delay bound claimed. No step compares clocks across hosts.

### Motivation

Work-item bd-ib-jjws2 (feature, no owning plan, held for implementation under coordinator ruling R144; R1 bd-ib-j6uvkj batch 13 routed it here as needing a linked proposal). The maintainer ruled on 2026-10-12 that ledger writers may share nothing but the Beads server, so no host lock can fence them (.ai/ledger-writers-are-multi-host.md). That file's measurements fix the design space: `bd update --metadata` loses concurrent keys, `bd comments add` is an insert, a fixed-id `bd create` is an upsert that reopens closed records, `bd update --claim` is refused by the lifecycle guard, and `bd close <id> --reason <r>` is a server-enforced compare-and-swap in which exactly one of N concurrent closers wins while the exit code does NOT name the winner. So the one server-side operation that can enforce exclusion here is closing a fresh, uniquely-identified record and reading its close_reason. The generalization target is the existing "Residual race" bullet, which already names this mechanism as the thing that closes its window; this proposal replaces that bullet rather than adding a section. Filing this proposal does not lift the R144 hold on implementing it. An independent review (gpt-6-luna, read-only) of the first draft found three real holes, all fixed here: writes moving an item INTO ready were unfenced, a winner that crashed between its close and its item write would leave a closed token every later writer loses to forever, and the migration paused only Dispatchers while intake and the valves could still write. The review also correctly observed that no compare-and-swap on a separate record can make a later non-conditional item write indivisible; the lease below bounds that window instead of claiming to remove it.

### Proposed Changes

Two edits, landing in one revision. No `## ` heading changes in `contracts.md`; one scenario is added to `scenarios.md`, so `tests/heading-coverage.json` gains one entry for it.

**1. `contracts.md`, `### Stranded claim release`, the bullet that begins "- **Residual race.**".** Replace the whole bullet with:

```
- **Claim tokens.** No public Beads write is a conditional update; the
  only server-enforced compare-and-swap is closing a record. A *claim
  token* is a ledger record created with a fresh, unique id (never a fixed
  id, because a create with an explicit id is an upsert that reopens a
  closed record), labelled `claim-token`, and never reopened. A token is
  created open by one writer and ends in exactly one of two ways: it
  becomes an item's current token when a won write names it, and is then
  closed exactly once, by the writer that next wins it; or it is
  *discarded*, closed by its own creator without ever being named by any
  item. A discarded token carries no meaning, MUST be ignored by every
  reader, and is not a current token of any item. A successor that a
  winner created but has not yet named stays open until a takeover (step
  5) wins it. While
  `dispatcher.claim_tokens` is `true` (below), every non-closed work-item
  MUST name exactly one token, its *current token*, which is open except
  while a transition is unapplied as step 5 below describes, and every *claim-changing write*
  — any write that changes an item's status, its `fabro` assignee or its
  run stamp, made by intake, a human valve, admission, a Dispatcher
  terminal write, or a recovery effect of this subsection, on any host —
  MUST follow this protocol:
  1. Read the item and its current token T, then create a fresh
     *successor* token S.
  2. Start a reading of its own monotonic clock, run `bd close T
     --reason <r>`, where `<r>` names the writer, its intent, the id of S
     and, for audit only, the UTC instant of the close, and then read
     T's `close_reason` back. The writer WINS only when that reason is its
     own, because the command's exit code does not name the winner.
  3. A writer that does not win MUST write nothing to the item, MUST
     discard S, and MUST report `claim-changed`. A writer that cannot read the
     close reason back MUST write nothing to the item and MUST report
     `claim-unobservable`.
  4. A winner MUST make its item change and name S as the item's current
     token in ONE ledger write, and MUST issue that write only while its
     *lease* holds: 120 seconds of elapsed time on that monotonic clock
     since the reading taken before its close, measured immediately
     before the write. A winner whose lease has passed MUST write nothing and MUST
     report `claim-lease-expired`, leaving S open.
  5. A writer that finds the item naming a token T that is already closed,
     whose close reason names a successor S that the item does not name,
     MUST write nothing and MUST report `claim-transition-pending` until
     it has itself observed that same state, T closed and S not named,
     across at least 180 seconds of elapsed time on its own monotonic
     clock, from its first such observation to a fresh read; only then
     MUST it treat S as the item's current token and apply this protocol
     to S, so a winner that crashed between its close and its
     item write never leaves the item unwritable. A writer that wins S
     this way MUST re-read the item immediately before its item write
     and, when the item now names S, MUST write nothing, MUST discard
     its own successor and MUST report `claim-changed`, because the original
     winner's transition has landed.
  Exactly one writer therefore wins each token, a loser never writes, and
  a writer that reads an earlier, already-closed token loses that token's
  close; the only way an earlier winner's item write can still land after
  a later write is the first residual below. No step compares
  one host's clock with another's: each bound is elapsed time on the
  measuring writer's own clock, and a takeover's first observation
  necessarily follows the close it observes. One residual class remains and is
  accepted: a winner's item write that it issued inside its lease but
  that the server applies only after a takeover of its successor token
  has begun can overwrite the takeover's write, or be overwritten by it
  when it lands between the takeover's re-read and its write; the same
  can recur at each later takeover while such a write is still
  outstanding. The 120-second lease and the
  180-second takeover wait make that ordering require the server to
  apply the write long after it was issued; no bound on that delay has
  been measured, so none is claimed. Apart from that
  residual class, no two claim-changing writes made under this protocol
  can both apply to the item for one token, on any host, which the owning-host rule,
  the canonical recovery lock and the stamp re-read cannot achieve alone.
  Those rules remain, because they decide WHETHER a recovery may act,
  while the token decides WHICH of several concurrent writers acts. A
  write made outside this protocol (for example a hand `bd update`) is
  not fenced by it and remains a second, separate residual: it can race
  with a protocol write in either direction, so the protocol MUST NOT be
  described as preventing one, and every writer named above MUST use the
  protocol. Token records MUST be excluded from `list-work-items`, `next`,
  `needs-attention`'s work-item facts and every child enumeration.
  The cutover is the committed key `dispatcher.claim_tokens`, a boolean
  defaulting to `false`, which joins the committed-configuration-only
  class; while it is `false`, every claim writer keeps the rules of this
  subsection without tokens. Before it is committed `true`, a sanctioned
  migration pass MUST name a fresh current token on every non-closed item
  that names no open token (an item naming a closed or discarded token, or
  none, counts as naming no open token), MUST leave unchanged every item that already
  names an open token, so that an interrupted pass can simply be run again, and
  MUST be run while every claim writer of the tenant — every Dispatcher,
  intake, the human valves and reconciliation — is stopped. Once the key
  is `true`, a claim writer that finds no current token on a non-closed
  item MUST write nothing and MUST report `claim-token-missing`, and
  `needs-attention` MUST surface the item. Under coordinator ruling R144
  this bullet states required behaviour; it does not by itself admit its
  implementation.
```

The replaced bullet's closing sentence about coordinator ruling R144 is carried into the new bullet as its last sentence, reworded for the new content. The rest of the subsection is unchanged; its other references to the residual window now read as references to this bullet.

**2. `scenarios.md`.** Add one scenario after the highest-numbered scenario, numbered by the revise pass:

```gherkin
Feature: Exactly one writer changes a dispatch claim
  Scenario: Two hosts race to change one active claim
    Given claim tokens are enabled and an active item whose current token is T
    And a recovery on host A and a resolve-blocked valve on host B both read the item
    When both close T with their own reasons
    Then exactly one close reason is recorded on T
    And only the writer whose reason was recorded writes to the item, naming its successor token
    And the other writes nothing, discards its own successor and reports claim-changed

  Scenario: Intake and a valve race to move one backlog item to ready
    Given claim tokens are enabled and a backlog item whose current token is T
    When intake and a move valve both try to move it to ready
    Then exactly one of them wins T and writes the item
    And the other writes nothing to the item

  Scenario: A writer that cannot read the close outcome writes nothing
    Given a writer that closed the item's current token but cannot read its close reason back
    When it decides whether to write
    Then it writes nothing to the item and reports claim-unobservable

  Scenario: A crashed winner does not leave the item unwritable
    Given an item naming closed token T whose close reason names successor S, and the item does not name S
    And another claim writer has observed that state for 200 seconds on its own clock
    When that writer reads the item again and the state is unchanged
    Then it treats S as the current token and applies the protocol to S

  Scenario: A recent unapplied transition is waited out, not taken over
    Given an item naming closed token T whose close reason names successor S, and the item does not name S
    And another claim writer first observed that state 30 seconds ago on its own clock
    When that writer reads the item again
    Then it writes nothing and reports claim-transition-pending

  Scenario: A winner past its lease does not write
    Given a writer that won its token 130 seconds of its own elapsed clock time after starting its close
    When it is about to write the item
    Then it writes nothing and reports claim-lease-expired

  Scenario: A takeover stands down when the original transition lands first
    Given a takeover writer that has won successor token S of an item whose closed token T named S
    And the original winner's item write naming S lands before the takeover's re-read
    When the takeover writer re-reads the item immediately before its write
    Then it writes nothing, discards its own successor and reports claim-changed

  Scenario: After cutover, an item with no token is refused, not written blind
    Given dispatcher.claim_tokens is committed true
    And a non-closed item names no current token
    When a claim writer tries to change it
    Then it writes nothing, reports claim-token-missing, and needs-attention surfaces the item

  Scenario: An interrupted migration can be run again
    Given a migration pass that named tokens on half of the tenant's non-closed items and stopped
    When the migration pass is run again with every claim writer stopped
    Then the items already naming an open token are left unchanged
    And every other non-closed item now names one
```
