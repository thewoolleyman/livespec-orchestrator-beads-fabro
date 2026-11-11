---
topic: fetch-dispatch-helper-programs-in
author: claude-opus-5-5
created_at: 2026-11-11T00:53:06Z
---

## Proposal: A dispatch's helper programs are fetched in the sandbox from the dispatching build's own commit and digest-verified, never carried in the run configuration

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Dispatcher stops carrying helper programs (the programs it materializes into a dispatch's sandbox from this plugin's own source, such as the commit runner and the gate preview) in the dispatch's rendered run configuration. It writes a helper manifest instead: the orchestrator repository, the commit of the installed plugin build, and one sha256 digest per helper program over that helper's composed bytes as the Dispatcher composes them. A setup step of the dispatched workflow fetches the plugin source at that commit (sparse, shallow), composes every helper from it with the Dispatcher's own composition, writes each to its sandbox path with its file mode, and verifies every digest; a mismatch, an unfetchable commit or a missing source path fails the run before `dod_gate` with the named cause `LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH`. A dispatch whose installed build commit the forge does not have is refused before any claim. The rendered run configuration carries no gzip+base64-packed helper payload; per-dispatch data that is not in the repository may stay inline, packed. The opening of `## Self-contained plugin dispatch` is reworded so that it still says the HOST needs no orchestrator clone, while it no longer says the dispatch path clones nothing but the target. The new paragraph sits beside "A sandbox runs its tools from pinned clones and works in the latest clones", its precedent, and Scenario 336 gains four scenarios. No H2 heading is added, renamed or removed.

### Motivation

The maintainer chose this design ("option D") on 2026-11-10, recorded as scope event `dpp-ruling-option-d-20261110` on plan epic bd-ib-x5ypbf (dispatch-payload-packaging): "Option D is basically putting a new node at the beginning of the workflow so that it will pull the stuff directly rather than jamming it in as a parameter." then "Yes, do that. Make it happen." The Dispatcher refused the implementing work item bd-ib-jrawlp at its spec-change-tier gate (hold reason `unratified-topic`): the spec-stated judgement found the asked-for behaviour unstated and named `## Self-contained plugin dispatch` as the heading to generalize, and held the item for the proposed-change topic `fetch-dispatch-helper-programs-in`. This proposal is that topic.

Measured (plan/dispatch-payload-packaging/research/002-direction-options-2026-11-10.md): the materialized `workflow.toml` grew from 467,910 bytes on 2026-11-02 to 524,343 bytes on 2026-11-10, over the engine's 524,288-byte per-file cap, and 409,951 bytes of a 518,117-byte file were prepare-step payload env values, mostly helper source. The engine never delivers extra workflow-package files into a sandbox (only the `[run.clone]` checkout), so separate package files would need a fork carry. A completed command node's script is pasted into every later agent prompt under the default `compact` fidelity, so the helper bytes cannot move into node scripts. Environment-table values ride on every sandbox exec and are stored twice per run. Gzip+base64 packing (bd-ib-p5e32s) is the live stopgap; at roughly 2-3 KB a day packed growth it reaches the 471,859-byte gate in about 4-6 weeks. A host-measured sparse, blobless, depth-1 fetch of the helper sources at a pinned commit took about 3.3 s. The pinned run-from clones of "A sandbox runs its tools from pinned clones and works in the latest clones" (Scenario 336) are the precedent mechanism.

In-flight survey: no open pull request touches `SPECIFICATION/`. Six remote `spec/*` branches exist (codex-floor-reset-proximity, dod-judgement-at-dispatch-wall, red-turn-changes-no-product-file, reprove-merged-item-v2, revise-attention-item-answer-policy, revise-v330-goal-template-opener-modify); each is a stale leftover dated 2026-09-07 to 2026-11-09 whose revise branches cut history versions long since passed (master is at v342), and none touches this paragraph's subject, so `default-align` applies. The pending proposal `sandbox-setup-runs-as-explicit-command-nodes` moves sandbox setup from a run-config prepare table to `run_prepare_<N>` command nodes; this proposal says "a setup step of the dispatched workflow", which holds under either shape, so the two compose. Linked work item: bd-ib-jrawlp.

### Proposed Changes

No H2 heading is added, renamed or removed in any spec file, so `tests/heading-coverage.json` is unchanged.

1. In `contracts.md` §"Self-contained plugin dispatch", replace the second paragraph, which begins "Because the workflow ships in the payload and resolves from the plugin root, the factory dispatches from the ENABLED PLUGIN ALONE" and ends "the orchestrator's own source is never a dispatch-time prerequisite.", with:

"Because the workflow ships in the payload and resolves from the plugin
root, the factory dispatches from the ENABLED PLUGIN ALONE: no clone of
the orchestrator's own source is required on the dispatching HOST. Fleet
members and adopters therefore consume the orchestrator IDENTICALLY —
enabling the plugin is the whole installation. The only repository clone
the dispatch path makes host-side is of the dispatch TARGET repo (the
work site); the orchestrator's own source is never a host-side
dispatch-time prerequisite. Inside the Fabro sandbox the dispatch path
clones the target again, takes the run-from and work clones of "A
sandbox runs its tools from pinned clones and works in the latest
clones", and fetches the orchestrator's own source at the installed
plugin build's commit solely to compose its helper programs, per
"Helper programs are fetched in the sandbox from the dispatching build's
own commit"."

2. In `contracts.md` §"Self-contained plugin dispatch", immediately after the line "Scenario 336 in `scenarios.md` exercises this paragraph." that closes the paragraph "A sandbox runs its tools from pinned clones and works in the latest clones.", insert this paragraph, separated by one blank line on each side:

"**Helper programs are fetched in the sandbox from the dispatching build's own commit.**
A *helper program* is a program the Dispatcher materializes into a dispatch's
sandbox from this plugin's own source, such as the commit runner and the gate
preview. The Dispatcher MUST NOT carry any helper program's source in a
dispatch's rendered run configuration. It MUST write a *helper manifest* there
instead, naming the orchestrator repository, the commit of the installed plugin
build, and one sha256 digest per helper program, each digest taken over that
helper's composed bytes as the Dispatcher composes them. A setup step of the
dispatched workflow MUST fetch the plugin source at the manifest's commit,
sparse and shallow, MUST compose every helper program from it with the same
composition the Dispatcher uses, MUST write each to its sandbox path with its
file mode, and MUST verify every digest. Because it is a setup step, it re-runs
when a run resumes onto a re-acquired sandbox. A composed helper whose digest
differs from the manifest, a manifest commit that cannot be fetched, or a source
path missing at that commit MUST fail the run before `dod_gate`, with the failure
cause `LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH` followed by `<helper>: <reason>`.
A dispatch whose installed plugin build commit is not reachable on the forge
MUST be refused before any dispatch claim is written, and the journaled refusal
MUST name the commit. The rendered run configuration MUST carry no
gzip+base64-packed helper payload; per-dispatch data that is not in the
repository, namely the `dod_gate` subject and the pull-request body, MAY stay
inline, packed. The setup step's own script MUST stay short and MUST NOT inline
any helper program's source, because the engine renders a completed command
stage's script into the prompt of every later agent stage. The dispatching host
still needs no orchestrator clone, as this section's opening paragraphs state;
the sandbox takes a pinned fetch of the orchestrator for its helper programs the
way it takes run-from clones for its tools.

Scenario 336 in `scenarios.md` exercises this paragraph."

3. In `scenarios.md` §"Scenario 336 — A sandbox checks a tree with the tooling release that tree pins, and works in the latest clones", replace its governing-clause line with:

"Governing clause: `contracts.md` §"Self-contained plugin dispatch" → "A sandbox runs its tools from pinned clones and works in the latest clones." and → "Helper programs are fetched in the sandbox from the dispatching build's own commit.""

The scenario's H2 heading line stays as it is.

4. In `scenarios.md` §"Scenario 336 — A sandbox checks a tree with the tooling release that tree pins, and works in the latest clones", inside its gherkin block, append after the scenario "Work clones are the latest, writable and deep enough to debug" (before the closing fence):

```gherkin
  Scenario: A dispatch's run configuration carries a helper manifest and no helper source
    Given a ready work item dispatched from an installed plugin build at commit C
    When the Dispatcher writes the dispatch's rendered run configuration
    Then it carries a helper manifest naming the orchestrator repository, commit C and one sha256 digest per helper program
    And it carries no helper program's source and no gzip+base64-packed helper payload

  Scenario: The setup step writes every helper program from the pinned commit and verifies its digest
    Given a dispatch whose helper manifest names commit C
    When the helper-fetch setup step runs in the sandbox
    Then each helper program at its sandbox path is byte-identical to the Dispatcher's composition of it at C, with its file mode
    And the step runs again before the next stage when the run resumes onto a re-acquired sandbox

  Scenario Outline: A helper the setup step cannot verify fails the run before dod_gate
    Given a dispatch whose helper manifest names commit C
    And <condition>
    When the helper-fetch setup step runs
    Then the run fails before dod_gate
    And its failure cause is LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH followed by the helper's name and the reason

    Examples:
      | condition                                                              |
      | one helper composed at C has a digest that differs from the manifest   |
      | commit C cannot be fetched                                             |
      | one helper's source path is missing at commit C                        |

  Scenario: A build commit the forge does not have is refused before claim
    Given an installed plugin build whose commit is not reachable on the forge
    When the Dispatcher dispatches a ready work item
    Then the dispatch is refused before any dispatch claim is written
    And the journaled refusal names the commit
```
