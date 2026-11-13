---
topic: the-incident-authority-cli-has
author: claude-opus-5-5
created_at: 2026-11-12T23:50:00Z
---

## Proposal: The incident authority CLI offers an item-only head read that reports an item's current phase and generation and authorizes nothing

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Adds one paragraph to contracts.md, section "Expedited incident lifecycle", immediately after the paragraph that begins "Inspection MUST report the item's attempts". The paragraph requires the incident authority writer's command-line interface to offer `read-head`, an item-only head read served by the canonical head reader `read_incident_head`:
- it takes a repository and an incident item id, and no attempt, phase, generation, operation or owner;
- it reports the item's current incident phase and generation from the canonical authority chain, `drill-closed` included;
- it reports an item as absent only when no incident authority genesis exists for it, and every other chain fault stays a named refusal;
- it refuses with the existing named reason `incident-authority-unavailable` when the authority store cannot be read;
- it authorizes no side effect.

A caller that acts on an attempt keeps `read-current`. A consumer outside this plugin that needs only a phase uses `read-head`, or `read_incident_head` where it calls the package in-process. No heading is added, removed or renamed, so `tests/heading-coverage.json` does not change.

### Motivation

Work item bd-ib-txbv7i was filed 2026-11-12 ~23:25Z as the cross-tenant companion of livespec-dev-tooling-io6hyk (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub; the link is recorded in prose only). Intake held it at the spec-change tier with verdict-kind partial and this linked topic. Its rationale: the ratified text requires standing, provenance, closure and inspection readers to report a `drill-closed` head and to preserve the full incident authority history, but it states no item-only read that needs just a repository and an item id, returns phase and generation, never authorizes a side effect, and reports absent distinctly from unavailable.

The need is measured. livespec-dev-tooling-io6hyk's factory run 01M78HQ4VS6E4PMFH73AFQJQEW ended BLOCKED at review_fix@2 (2026-11-12T23:10:20Z) on its accepted review finding r2. livespec-dev-tooling's incident fleet audit (`incident_fleet_cli.production_environment`) has no production `read_incident_phase`. So in production it cannot honour io6hyk's first assertion: an item the canonical incident reader reports at `drill-closed` is not counted as recovery capability for master. The audit's claims carry only `incident_item`.

The released CLI (`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/incident_authority.py` on master, 2026-11-12 ~23:20Z) offers only `read-current` and `read-history`:
- every action requires `--operation` and `--owner`, and the reads take the fenced identity;
- `read-current` authorizes a side effect.

The package already has the reader this needs. `read_incident_head` in `effects/_incident_authority_reader.py` is exported from `incident_authority.py`. It selects the chain's current generation from the item alone, and it refuses an outage with `incident-authority-unavailable`. The plugin's own merged-PR resolution (`commands/_dispatcher_incident_pr.py:178`) and completion reader (`effects/_incident_completion_reader.py:132`) use it in-process. No CLI action exposes it, so a consumer holding only an item id has no canonical way to read its phase. The alternatives are an always-empty stub or a re-decode of the authority token chain. Both bypass the canonical reader that this section requires every consumer to read through.

This read is the reader-side complement of the `drill-close` action ratified in v349 (bd-ib-z7ckf4). `drill-close` is the only writer of `drill-closed`. `read-head` is how an installed consumer that never acts on an attempt observes that result. Before any `drill-close` write, the requirement that "every incident reader … MUST be released and verified to accept `drill-closed`" covers `read-head` too.

### Fleet scope (rule K)

The incident authority CLI is orchestrator code that every adopter calls through its installed plugin. So an item-only read needs no copy in any adopter: it ships once, here.

Adopter-side callers were swept on 2026-11-12 ~23:45Z in livespec-dev-tooling, livespec, livespec-overseer and livespec-console-beads-fabro. The sweep covered product Python, not tests, for `read-current`, `read-history` and `incident_authority`. Only livespec-dev-tooling calls the CLI.

None of its callers builds the full fenced identity only to read a phase. Each reads the identity of an attempt it then acts on, and so keeps the fenced reads:
- `incident_authority_client.py`, the shared `read-current` wrapper;
- `incident_gate_entry.py:117`, `incident_focused_disposition_entry.py:145` and `incident_focused_evidence_entry.py:241`: `read-current` before a side effect;
- `incident_focused_evidence_entry.py:218`, `_incident_original_run_canonical.py:131` and `incident_conflict_chain.py:92`: `read-history` for a recorded attempt.

The one phase-only consumer is the fleet audit, `incident_fleet_cli.production_environment`. Today it has NO read at all, rather than one built on the fenced identity, and it adopts `read-head` through livespec-dev-tooling-io6hyk once a release carrying this ships.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "Expedited incident lifecycle", insert the following paragraph immediately after the paragraph that begins "Inspection MUST report the item's attempts, owner/generation, current carrier" and ends "developing and adopting this feature MUST use normal gates." No heading is added, removed or renamed in that file.

The incident authority writer's command-line interface MUST offer an item-only head read, `read-head`, that takes the repository and an incident item id and no attempt, phase, generation, operation or owner, and that is served by the canonical head reader `read_incident_head`. It MUST report the item's current incident phase and generation from the canonical incident authority chain, reporting `drill-closed` for a `drill-closed` head. It MUST report the item as absent only when no incident authority genesis exists for that item; every other chain fault, including an ambiguous chain, an invalid genesis, a cycle, an identity mismatch or an item mismatch, MUST remain the named refusal the canonical reader returns, and a failed read MUST NOT be reported as absence. When the authority store cannot be read, it MUST refuse with the named reason `incident-authority-unavailable` and report no phase. Its reply MUST NOT authorize a side effect: a caller that will act on an attempt MUST still take `read-current` with the full fenced identity immediately before that side effect. A consumer outside this plugin that needs only an item's phase, such as an installed consumer's fleet audit, MUST use `read-head`, or `read_incident_head` where it calls the package in-process, rather than reconstruct the fenced identity or decode the authority chain itself.
