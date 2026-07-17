---
topic: multi-provider-worker-credential-projection
author: claude-opus-4-8
created_at: 2026-07-17T03:50:49Z
---

## Proposal: Realign §"Worker credential projection" + Scenarios 18/19 to the multi-provider worker path

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json (no change — see subsection C)

### Summary

De-drift the worker-credential-projection contract and its two scenarios to
describe the **multi-provider** worker path the implementation already ships. The
existing contract is already provider-agnostic and even names both providers, but
it speaks throughout of **one** host refresh credential and **one** projected
snapshot, implying a single-provider projection. The shipped Dispatcher overlay is
already multi-provider and **additive**: a single worker sandbox's run-scoped
overlay carries **both** the Claude-subscription OAuth env credential **and** the
OpenAI/ChatGPT (Codex) file credential at once, each rendered non-rotatable, so one
worker MAY authenticate more than one coding-agent runtime. This proposal makes
narrow prose realignments: (a) the contract states that the host MAY hold, and the
Dispatcher MAY project into one worker, credentials for **more than one provider at
once**; (b) it scopes the per-credential guarantees to the ones that are genuinely
per-credential (non-rotatability, host-ownership) and separates the
provider-agnostic guarantees from the provider-specific **projection mechanism**
(which stays implementation-owned); (c) it re-arities the freshness gate to the
credentials it covers — leaving WHICH credentials are covered implementation-owned,
because the shipped gate lifetime-gates the Codex credential and only
presence-checks the Claude one; and (d) Scenarios 18/19 are realigned in place —
Scenario 18 shows both providers' credentials projected non-rotatably into the same
sandbox (matching `test_scenario18_dispatch_overlay_projects_dual_credentials`), and
Scenario 19 re-arities the freshness-gate refusal to a host credential covered by
the freshness gate (coverage stays implementation-owned per A.5). No `## ` H2
heading is added, removed, or renamed, so
`tests/heading-coverage.json` is unchanged. The guarantees are preserved in
substance; only their arity (one → one-or-more projected credentials), the
guarantee/mechanism split, and the freshness gate's coverage arity change.

### Motivation

Design record (recorded maintainer intent — the tiebreaker per `contracts.md`
§"Intent preservation"): this repo, `plan/codex-credential-broker/handoff.md`,
§"ACTIVE — `bd-ib-ss7rkr` docs/contract realignment (adopted 2026-07-16)", which
scopes exactly this work ("realign the orchestrator SPECIFICATION to describe the
MULTI-PROVIDER worker credential path — `contracts.md` §'Worker credential
projection' + `scenarios.md` Scenario 18/19"). Work-item `bd-ib-ss7rkr`. The
shipped mechanical difference between the two providers' projections — a Claude
subscription authenticates from an OAuth token carried in the worker environment,
whereas an OpenAI/ChatGPT subscription authenticates from a file-based credential
(the Codex `auth.json`) whose rotating single-use refresh token is replaced by an
inert sentinel — is established by the implementation and the codex-credential-broker
design record; this contract does not fix it.

This is a **spec-lags-impl de-drift, not a new direction.** The shipped behavior
already corroborates the change. The integration acceptance bound to this contract,
`tests.integration.test_worker_credential_projection_scenarios18_19.test_scenario18_dispatch_overlay_projects_dual_credentials`,
proves that the run-scoped overlay carries both the Claude-subscription OAuth env
credential and the OpenAI/ChatGPT (Codex) file credential in the same sandbox (per
the `tests/heading-coverage.json` reasons bound to §"Worker credential projection"
and to Scenario 18). And the freshness gate as shipped lifetime-gates the Codex
credential specifically (`test_scenario19_stale_codex_credential_refuses_before_overlay`;
`_dispatcher_credentials.py` freshness-gates the projected Codex credential while
only presence-checking the Claude OAuth env). The contract §"Worker credential
projection" (landed at v013, unchanged since) already says it "governs
Claude-subscription and OpenAI/ChatGPT-subscription workers identically" and that
the projection mechanism is implementation-owned — this proposal only makes the
multiplicity, the guarantee/mechanism split, and the gate's coverage arity explicit,
so the prose stops implying a single projected credential.

### Proposed Changes

### Scope note — what this proposal does NOT touch

- **`SPECIFICATION/spec.md` and `SPECIFICATION/constraints.md` are DELIBERATELY
  UNCHANGED.** Neither carries any worker-credential-projection prose (verified:
  zero occurrences of "credential projection", "freshness gate", "non-rotatable",
  or "auth.json" in either file). This is a deliberate non-change, not an omitted
  sweep.
- **No new scenario is added and no scenario is renumbered.** Scenarios 18 and 19
  are realigned in place; their `## ` H2 heading strings stay byte-identical, so
  `tests/heading-coverage.json` needs no co-edit (subsection C).
- **The freshness gate stays a single provider-agnostic guarantee; WHICH projected
  credentials it covers is made implementation-owned (A.5), not enumerated.** The
  contract does not assert the Dispatcher lifetime-gates every provider — because the
  shipped gate covers only the Codex credential — nor does it fix which it covers.
- **The deferred `plan/credential-freshness-redesign/` findings are OUT of scope**
  (session-bound JWT, refresh-token rotation, the dead-zone/timer redesign). Those
  are a separate track; nothing here pre-empts that decision.
- **`SPECIFICATION/history/**` is immutable and out of scope.**

Drift sweep — corroborating but untouched: the shipped dual-credential overlay
(`test_scenario18_dispatch_overlay_projects_dual_credentials`) and the Codex-side
freshness gate (`test_scenario19_stale_codex_credential_refuses_before_overlay`)
already implement the multi-provider behavior; this de-drift aligns the prose to
them without changing any guarantee.

---

#### A. `SPECIFICATION/contracts.md`

**A.1 — AMEND §"Worker credential projection", opening paragraph.** Make the
host's multi-provider ownership + the additive projection explicit, scope the
per-credential guarantees to non-rotatability + host-ownership, and separate the
provider-agnostic guarantees from the (MAY-be) provider-specific mechanism.

Replace-target (exists verbatim, currently at contracts.md:2118–2123):

```
The Dispatcher MAY authenticate a worker sandbox's coding-agent runtime from a
**projected provider-subscription credential** (for example a Claude subscription
or an OpenAI/ChatGPT subscription) as an alternative to a provider API key, so
workers MAY spend subscription quota rather than metered API billing. This
contract is provider-agnostic: it governs Claude-subscription and
OpenAI/ChatGPT-subscription workers identically.
```

Replacement:

```
The Dispatcher MAY authenticate a worker sandbox's coding-agent runtime from a
**projected provider-subscription credential** (for example a Claude subscription
or an OpenAI/ChatGPT subscription) as an alternative to a provider API key, so
workers MAY spend subscription quota rather than metered API billing.

The orchestrator host MAY hold provider-subscription credentials for more than one
provider at the same time, and the Dispatcher MAY project more than one of them
into a single worker sandbox — so one worker MAY authenticate more than one
coding-agent runtime (for example a Claude-subscription primary agent alongside an
OpenAI/ChatGPT-subscription runtime). Each projected credential MUST independently
satisfy the non-rotatability and host-ownership guarantees below.

The non-rotatability and host-ownership guarantees are provider-agnostic: they hold
for a Claude-subscription and an OpenAI/ChatGPT-subscription credential alike. The
projection **mechanism**, by contrast, MAY be provider-specific — the shape of each
projected credential MAY differ per provider — and is implementation-owned (see the
final paragraph).
```

**A.2 — AMEND the non-rotatable paragraph** so the guarantee reads per projected
credential rather than for a single one.

Replace-target (exists verbatim, currently at contracts.md:2125–2128):

```
A projected worker credential MUST be **non-rotatable by the worker**: a worker
MUST NOT be able to mint or rotate the shared long-lived refresh credential. No
worker — including one whose run triggers a credential refresh — MAY invalidate
the credential for the orchestrator host or for any peer worker.
```

Replacement:

```
Each projected worker credential MUST be **non-rotatable by the worker**: a worker
MUST NOT be able to mint or rotate any shared long-lived refresh credential. No
worker — including one whose run triggers a credential refresh — MAY invalidate a
credential for the orchestrator host or for any peer worker.
```

**A.3 — AMEND the freshness-gate paragraph** to re-arity the gate to the
credentials it covers (WHICH credentials it covers is implementation-owned per A.5).

Replace-target (exists verbatim, currently at contracts.md:2130–2134):

```
The Dispatcher MUST NOT dispatch a worker unless the projected credential's
usable lifetime exceeds the worker's maximum run budget (the **freshness
gate**). When the freshness gate cannot be satisfied, the Dispatcher MUST refuse
the dispatch and MUST surface that the host credential requires renewal, rather
than projecting a credential that MAY expire mid-run.
```

Replacement:

```
The Dispatcher MUST NOT dispatch a worker unless every projected credential covered
by the **freshness gate** has a usable lifetime that exceeds the worker's maximum
run budget. When the freshness gate cannot be satisfied, the Dispatcher MUST refuse
the dispatch and MUST surface that the host credential requires renewal, rather
than projecting a credential that MAY expire mid-run.
```

**A.4 — AMEND the host-sole-owner paragraph** to own each provider credential.

Replace-target (exists verbatim, currently at contracts.md:2136–2138):

```
The orchestrator **host** MUST be the sole owner and refresher of the long-lived
provider refresh credential; worker sandboxes MUST be read-only consumers of a
projected snapshot.
```

Replacement:

```
The orchestrator **host** MUST be the sole owner and refresher of each long-lived
provider refresh credential; worker sandboxes MUST be read-only consumers of the
projected snapshots.
```

**A.5 — AMEND the implementation-owned paragraph** to name the per-provider
projection shape AND the freshness-gate coverage as implementation-owned degrees of
freedom.

Replace-target (exists verbatim, currently at contracts.md:2140–2143):

```
The projection mechanism — the credential file or field layout, the encoding
that renders the snapshot non-rotatable, and the numeric freshness threshold —
is implementation-owned and MUST NOT be fixed by this contract. The behavior is
exercised by Scenario 18 and Scenario 19 in `scenarios.md`.
```

Replacement:

```
The projection mechanism — the per-provider projection shape, which projected
credentials the freshness gate covers, the credential file or field layout, the
encoding that renders the snapshot non-rotatable, and the numeric freshness
threshold — is implementation-owned and MUST NOT be fixed by this contract. The
behavior is exercised by Scenario 18 and Scenario 19 in `scenarios.md`.
```

#### B. `SPECIFICATION/scenarios.md`

Both scenarios are realigned **in place**; the `## Scenario 18 — …` and
`## Scenario 19 — …` H2 heading strings are left byte-identical (only the gherkin
body between the `` ```gherkin `` fences changes).

**B.1 — AMEND Scenario 18's gherkin body** to show both providers' credentials
projected non-rotatably into the same sandbox (matching the shipped dual-credential
overlay).

Replace-target (the gherkin body, exists verbatim at scenarios.md:333–343):

```
Feature: Dispatcher projects a non-rotatable subscription credential
  As the Dispatcher running a worker on a provider subscription
  I want to project a credential the worker cannot rotate
  So that no worker can invalidate the shared credential for the host or peers

Scenario: A dispatched worker receives a non-rotatable credential snapshot
  Given the orchestrator host holds a valid provider-subscription credential whose usable lifetime exceeds the worker run budget
  When the Dispatcher dispatches a ready work-item to a worker sandbox
  Then the Dispatcher projects a non-rotatable credential snapshot into the sandbox such that the worker cannot rotate the shared refresh credential
  And the worker authenticates its coding-agent runtime from that projected snapshot
  And no refresh performed or attempted inside the sandbox invalidates the host's or any peer worker's credential
```

Replacement:

```
Feature: Dispatcher projects non-rotatable subscription credentials
  As the Dispatcher running a worker on one or more provider subscriptions
  I want to project credentials the worker cannot rotate
  So that no worker can invalidate the shared credential for the host or peers

Scenario: A dispatched worker receives non-rotatable snapshots for every projected provider
  Given the orchestrator host holds a valid Claude-subscription credential and a valid OpenAI/ChatGPT-subscription credential whose usable lifetimes exceed the worker run budget
  When the Dispatcher dispatches a ready work-item to a worker sandbox
  Then the Dispatcher projects each provider's credential as a non-rotatable snapshot into the same sandbox such that the worker cannot rotate any shared refresh credential
  And the worker authenticates its coding-agent runtimes from those projected snapshots
  And no refresh performed or attempted inside the sandbox invalidates the host's or any peer worker's credential for any provider
```

**B.2 — AMEND Scenario 19's gherkin body** to re-arity the freshness-gate refusal
to a gate-covered host credential (so the gate reads correctly when more than one
credential is in play, without asserting coverage of every projected credential,
without inventing a per-work-item requirement relation, and without implying
anything is projected before refusal).

Replace-target (the gherkin body, exists verbatim at scenarios.md:349–358):

```
Feature: Dispatcher freshness-gates subscription-credentialed dispatch
  As the Dispatcher protecting unattended runs
  I want to refuse dispatch when the credential cannot outlive the run
  So that a worker never starts on a credential that may expire mid-run

Scenario: A too-short-lived credential refuses dispatch with a renewal message
  Given the host provider-subscription credential's usable lifetime does NOT exceed the worker run budget
  When the Dispatcher considers dispatching a ready work-item
  Then the Dispatcher refuses the dispatch
  And the Dispatcher surfaces that the host credential requires renewal rather than projecting a credential that may expire mid-run
```

Replacement:

```
Feature: Dispatcher freshness-gates subscription-credentialed dispatch
  As the Dispatcher protecting unattended runs
  I want to refuse dispatch when a covered credential cannot outlive the run
  So that a worker never starts on a credential that may expire mid-run

Scenario: A too-short-lived credential refuses dispatch with a renewal message
  Given a host provider-subscription credential covered by the freshness gate has a usable lifetime that does NOT exceed the worker run budget
  When the Dispatcher considers dispatching a ready work-item
  Then the Dispatcher refuses the dispatch
  And the Dispatcher surfaces that the host credential requires renewal rather than projecting a credential that may expire mid-run
```

#### C. `tests/heading-coverage.json`

**No change.** This proposal adds, removes, and renames no `## ` H2 heading: the
three affected headings — `## Worker credential projection`, `## Scenario 18 —
Dispatcher projects a non-rotatable subscription credential into a worker sandbox`,
and `## Scenario 19 — Dispatcher refuses dispatch when the credential freshness
gate fails` — are all left byte-identical, and only body prose / gherkin bodies
beneath them change. Scenario 18's heading keeps its singular wording ("projects **a**
non-rotatable subscription credential"); read distributively over the multi-provider
body, the singular still holds (each projected credential is a non-rotatable
snapshot), and the heading is deliberately not reworded so the heading-coverage map
needs no co-edit. The existing coverage bindings (both to
`tests.integration.test_worker_credential_projection_scenarios18_19`) remain correct
and are not weakened. The heading-coverage map therefore stays in lockstep with no
edit.

### Review history

- **Round 1 (Fable adversarial review, 2026-07-17).** Independent Fable-model
  reviewer returned 4 BLOCKERS + 3 nits, all accepted and fixed in this revision:
  (B1) A.1 universalized the freshness gate over every projected credential, which
  the shipped impl falsifies (it lifetime-gates only the Codex credential and merely
  presence-checks the Claude one) — fixed by scoping the per-credential universal to
  non-rotatability + host-ownership and making gate coverage implementation-owned;
  (B2) the freshness paragraph's arity was left incoherent and the scope-note defense
  was untrue — fixed by re-aritying the gate (new A.3) and adding "which projected
  credentials the freshness gate covers" to A.5's implementation-owned list; (B3) A.1
  fixed "shapes differ per provider" as declarative fact while disclaiming mechanism
  ownership — fixed with MAY; (B4) Scenario 19's Given invented a per-work-item
  "requires" relation and said "projected" before anything is projected — re-aried
  away from both. Nits N1 (Scenario 18 singular heading read distributively), N2
  (spliced heading-coverage reason quote), N3 (mechanical-difference over-attributed
  to the handoff §ACTIVE section) addressed in subsection C and the Motivation.
- **Round 2 (Fable adversarial review, 2026-07-17).** Confirmed B1–B4 resolved but
  caught NB-1: the Round-1 B4 re-arity ("a host credential the Dispatcher would
  project") re-introduced B1's universal at the scenario level — "would project"
  quantifies over every projected credential, including the presence-checked Claude
  one. Fixed by re-aritying Scenario 19's Given + Feature to "covered by the freshness
  gate", mirroring A.3/A.5 so coverage stays implementation-owned and the bound Codex
  test still instantiates it.
- **Round 3 (Fable adversarial review, 2026-07-17).** Confirmed NB-1 resolved in the
  normative payload (verified against the impl and the bound Codex test) and caught
  NB3-1: the NB-1 wording had not been propagated to the Summary and the B.2
  amendment header, which still described the amendment with the rejected "would
  project" scope — fixed to match the payload. Re-verified the payload clean
  (replace-targets, citations, no change-relative prose in replacements,
  heading-coverage no-op, altitude, post-edit coherence).
- **Round 4 (Fable adversarial review, 2026-07-17).** Confirmed NB3-1 resolved (the
  Summary and B.2 header now match the payload's "covered by the freshness gate"
  scope) and returned a final **NO-BLOCKERS** verdict on a full adversarial sweep
  (replace-targets, impl-falsified universals, change-relative prose, citations,
  heading-coverage no-op, post-edit coherence).
