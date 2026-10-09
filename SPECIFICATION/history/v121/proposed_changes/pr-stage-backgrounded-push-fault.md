---
topic: pr-stage-backgrounded-push-fault
author: OpenAI Codex
created_at: 2026-10-09T10:28:43Z
---

## Proposal: Scripted publication with exact-head proof after refresh

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replace ACP publication with deterministic command stages while preserving proof freshness, branch provenance, gates, merge holds and resume.

### Motivation

Plan bd-ib-ctagnf measured BackgroundedTool turn failures during slow post-rebase pushes; the maintainer authorized completing the plan, including Definition of Done, proof and archive.

### Proposed Changes

Publication MUST use pr_refresh and pr command stages. The exact contract and scenarios proposed are shown in this diff; legacy pr adapter overrides MUST refuse with a removal remedy.

```diff
--- contracts.md
+++ contracts.md
@@ -2727,9 +2727,9 @@
 clause of §"Repository integration contract" — applies to every
 registered variant exactly as it applies to the reserved workflow, and
 each such clause's refusals fire for a variant on the same conditions. A
-registered variant MUST declare the same nine ACP nodes — `dod_gate`,
+registered variant MUST declare the same eight ACP nodes — `dod_gate`,
 `implement`, `fix`, `review_fix`, `proof_capture`, `review`,
-`disposition`, `proof_verify`, `pr` — so that the per-repository adapter
+`disposition`, `proof_verify` — so that the per-repository adapter
 layer and the per-node timeout table resolve against it without naming an
 absent node; a variant differs from the reserved workflow in its graph
 edges, retry and review discipline, prompts, run configuration and sandbox
@@ -2809,18 +2809,15 @@
 **The stages.** The reserved `implement-work-item` workflow MUST carry
 three additional ACP nodes with these names and positions: `dod_gate`,
 the first node after `start` and before `implement`; `proof_capture`,
-entered only from `publish_draft` and exiting only to `review`; and
-`proof_verify`, entered from `review` and exiting to `pr` on success. It
+entered from `publish_draft` or a changed-head `pr_refresh` and exiting only to `review`; and
+`proof_verify`, entered from `review` and exiting to `pr_refresh` on success. It
 MUST also carry the command node `publish_draft`, entered only from a
 green janitor outcome and exiting to `proof_capture`, which MUST push the
 item's publish branch and, when no pull request for that branch exists,
 open one as a DRAFT; it MUST be idempotent across janitor re-entries and
-MUST fail closed to `needs_human` when origin cannot be reached. The `pr`
-node MUST mark that pull request ready and arm auto-merge rather than
-create it, MAY rewrite the run's own publish branch with a lease-guarded
-force push when it rebases (the branch is consumed by no one before it is
-marked ready) and MUST NOT rewrite any other ref; the publish breaker
-(`verify_pr`) is unchanged. Each of the three ACP nodes selects its
+MUST fail closed to `needs_human` when origin cannot be reached. The command stages `pr_refresh` and `pr` MUST perform publication as specified
+below; the publish breaker (`verify_pr`) retains its existing obligations.
+Each of the three ACP nodes selects its
 adapter through exactly the mechanism the existing ACP nodes use, with
 its own adapter input (`dod_gate_adapter`, `proof_capture_adapter`,
 `proof_verify_adapter`), and migrates with them when that mechanism
@@ -2829,6 +2826,42 @@
 configuration", the defaults table of §"Built-in ACP node defaults", and
 the success-critical enumeration of §"Factory-configurable ACP fallback
 priority".
+
+**Scripted publication and proof-head integrity.** `pr_refresh` and `pr`
+MUST be command stages with their own resolved timeouts, not agent turns.
+`pr_refresh` MUST fetch the authoritative default branch and query the publish
+branch on origin. It MUST establish the run's previously published head from
+its recorded publication or validated resume provenance, never from a stale
+local tracking ref. A missing or unobservable remote, a foreign or unexpectedly
+changed publish head, or a conflicted rebase MUST fail closed with a named
+cause and recovery artifact pointer. A previously completed refresh may be
+recognized idempotently from durable run provenance and matching remote state.
+
+When the default branch has advanced beyond the current base, `pr_refresh`
+MUST rebase, run the existing repository-declared `sandbox_check_suite` as a
+foreground command with its own timeout, and push only after that gate passes.
+A rewrite MUST use an explicit lease against the recorded remote head of this
+run's own publish branch. Hooks MUST run normally. It MUST NOT use bare force,
+`--no-verify`, or rewrite another ref. A changed head MUST return to
+`proof_capture`, then `review` and `proof_verify`; only proof for the new head
+can reach final publication. Repeated default-branch movement is bounded to
+three refreshes per run, after which the run terminates with an explicit
+non-convergence cause and preserved work. An unchanged head proceeds to `pr`.
+All touched nodes MUST retain an unconditional outgoing edge accepted by the
+supported engine, and command nonzero exits MUST take their failure edge.
+
+`pr` MUST query the exact pull request for the recorded branch, verify its
+current head against the head whose proof was verified, apply the Dispatcher-
+rendered title and body, mark the draft ready and arm auto-merge with the
+resolved merge method unless the item's merge hold is active. It MUST retain
+existing `PR_NUMBER` and merge-hold result markers. A pull request already
+merged is a recorded success; one closed without merging or carrying an
+unexpected head MUST fail closed. Publication metadata MUST be passed as data,
+not interpolated as shell syntax. A merge hold MUST preserve the ready pull
+request and leave auto-merge unarmed. Resume from an earlier verified head
+MUST enter `pr_refresh` before `pr`, preserving the existing exact-head and
+run-attribution refusals. A later head change requires fresh proof; publication
+MUST NOT reuse a verified record from before that change.
 
 **`dod_gate`.** The node MUST verify, against the rendered goal, that the
 Definition of Done section exists and parses per §"Effective acceptance
@@ -3642,7 +3675,7 @@
 from the earlier run's record on the factory the earlier dispatch names;
 when that factory answers that it no longer holds the run, the Dispatcher
 MUST derive the stage from the verdict of the latest record carrying the
-earlier run's identifier — `verified`: `pr`; `captured`: `review`;
+earlier run's identifier — `verified`: `pr_refresh`; `captured`: `review`;
 `not_captured` or `not_reproduced`: `fix`; no such record:
 `proof_capture` — and the resume record MUST name which source decided
 it. An authoritative not-found answer from the factory observes the run
@@ -4413,7 +4446,7 @@
 parent selector on a merge commit) — so admitting `merge` is a separate
 obligation that must ratify those changes. The resolved value projects, per
 "Resolve once, project everywhere", into BOTH the Dispatcher's auto-merge argv
-(the `gh pr merge` method flag) and the `pr.md` prompt variable the in-run agent
+(the `gh pr merge` method flag) and the scripted publication command that
 uses to arm auto-merge — two seams of one resolved object, neither authoritative,
 kept in agreement by the seam-equivalence check — and it is one of the fields
 that check ranges over. Only the merge-METHOD flag is projected; the branch
@@ -5891,7 +5924,7 @@
 factory emits. Raw env values MUST NOT ride that trace.
 
 **Defaults are per node and structured.** The workflow's own declared inputs
-(`acp_adapter`, `pr_adapter`, `review_adapter`, `disposition_adapter`,
+(`acp_adapter`, `review_adapter`, `disposition_adapter`,
 `dod_gate_adapter`, `proof_capture_adapter`, `proof_verify_adapter`) MUST
 express the built-in defaults as structured entries in the grammar of §"ACP node
 adapter configuration", never as class-shaped tiers:
@@ -5899,32 +5932,27 @@
 | node | built-in default entry |
 |---|---|
 | `implement`, `fix`, `review_fix`, `proof_capture` | `{"agent": "claude-acp", "model": "claude-opus-5", "effort": "high"}` |
-| `pr` | `{"agent": "claude-acp", "model": "claude-haiku-4-5", "effort": "high"}` |
 | `review`, `disposition` | the entries the workflow declares for its review and disposition inputs |
 | `dod_gate`, `proof_verify` | the entry the workflow declares for its review input |
 
 The implementer nodes carry design judgement and default to the strongest
-available model; the `pr` node executes a fixed `git`/`gh` recipe with no design
-judgement in it and defaults to a cheap model. Rendered through the `claude-acp`
-entry of the agent catalog, whose mechanism at this ratification is the
-ENVIRONMENT mapping (`ANTHROPIC_MODEL`, `CLAUDE_CODE_EFFORT_LEVEL`), these
-defaults MUST render, literally:
+available model. Rendered through the `claude-acp` catalog's environment
+mechanism, their defaults MUST render literally:
 
     ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high npx -y @agentclientprotocol/claude-agent-acp
 
-for the implementer nodes and
-
-    ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high npx -y @agentclientprotocol/claude-agent-acp
-
-for `pr` — the v107 bytes, byte for byte. The model and effort ride the
-adapter's own environment as leading `KEY=value` assignments because Fabro
-rejects `model` and `reasoning_effort` as ACP node attributes. Switching the
-`claude-acp` entry to the `protocol` mechanism of §"Factory-configurable ACP
-fallback priority" → "In-protocol model and effort selection" is a committed
-catalog change that alters those bytes and MUST be treated as a default change
-under the verification rule below. The Dispatcher MUST NOT apply a
-context-window suffix such as `[1m]` to a default model name; whether a model
-accepts one is established from a run transcript, never assumed in a default.
+The `pr` publish stage is a command stage and MUST NOT launch an ACP adapter.
+The retired `pr_adapter` input MUST NOT be rendered or consumed by the reserved
+workflow or a registered variant. An explicit `dispatcher.acp_nodes.pr` or
+per-dispatch adapter override naming `pr` MUST refuse before claim, naming the
+retired entry and directing its removal; a `node_timeouts.pr` override remains
+valid for the command stage. The retired `dispatcher.codex_models` setting
+continues to refuse, with a diagnostic explaining that its `pr` class has no
+ACP replacement. Other node defaults and their rendering remain unchanged.
+
+Model and effort ride the selected catalog mechanism; changing that mechanism
+is a committed default change under the verification rule below. The Dispatcher
+MUST NOT append a context-window suffix such as `[1m]` to a default model name.
 
 The Dispatcher SHOULD treat the first dispatch after a change to any built-in
 default — the entry itself or the catalog rendering behind it — as a
@@ -5939,8 +5967,8 @@
 `dispatcher.codex_models` MUST refuse before claim, and the refusal MUST print
 the equivalent `dispatcher.acp_nodes` entries — `{"agent": "codex-acp",
 "model": <model>, "effort": <reasoning_effort>}` under each node the retired
-class covered (`implement`, `fix` and `review_fix` for `implementer`; `pr` for
-`pr`) — so the migration is a copy. Measured at ratification, no fleet
+class covered (`implement`, `fix` and `review_fix` for `implementer`); the
+retired `pr` class directs removal because publication is scripted. Measured at ratification, no fleet
 repository set the key.
 
 **Every Codex candidate is pinned.** A candidate whose `agent` is `codex-acp`,
@@ -6056,7 +6084,7 @@
 
 Every ACP node of the `implement-work-item` workflow — `dod_gate`,
 `implement`, `fix`, `review_fix`, `proof_capture`, `review`, `disposition`,
-`proof_verify`, `pr` — runs an adapter the Dispatcher
+`proof_verify` — runs an adapter the Dispatcher
 RESOLVES FROM CONFIGURATION, never from a code-level provider choice.
 Switching any node to any model behind any provider protocol, open-weight and
 local models included, MUST be a configuration change with no code change.
@@ -6111,7 +6139,7 @@
 **Three resolution layers, most specific wins.** Each node's value MUST
 resolve through, in ascending precedence: (1) the WORKFLOW DEFAULTS — the
 declared inputs and their defaults in the workflow's own `workflow.toml`
-(`acp_adapter`, `pr_adapter`, `review_adapter`, `disposition_adapter` today),
+(`acp_adapter`, `review_adapter`, `disposition_adapter` today),
 so a vendored workflow carries its own defaults and the built-in fleet
 defaults of §"Built-in ACP node defaults" are expressed there; (2) the
 PER-REPOSITORY LAYER — the `dispatcher.acp_nodes` table in the dispatch
@@ -6230,9 +6258,9 @@
 adapter a single point of failure. This is an additive configuration feature:
 when no fallback metadata is present, or `fallbacks` is an empty array, adapter
 resolution and rendered command bytes MUST remain byte-identical to §"ACP node
-adapter configuration". In particular, the unconfigured `pr` node remains the
-Claude Haiku 4.5 default ratified in v107, and an explicit structured `pr`
-entry (§"Built-in ACP node defaults") remains candidate zero.
+adapter configuration". In particular, an unconfigured `review_fix` node retains its workflow
+default, and an explicit structured `review_fix` entry remains candidate zero.
+The command stages `pr_refresh` and `pr` have no candidate chains.
 
 **Resolve the primary before attaching the chain.** The Dispatcher MUST first
 resolve candidate zero through the existing workflow-default, explicit
@@ -6424,7 +6452,7 @@
 The workflow MUST expose the ACP nodes that dominate every green terminal path.
 Those success-critical nodes are admission-required; for the reserved
 workflow they are `dod_gate`, `implement`, `proof_capture`, `review`,
-`proof_verify`, and `pr`, each of which dominates every green terminal path;
+`proof_verify`, each of which dominates every green terminal path;
 for a registered variant the success-critical set is the ACP nodes
 dominating that variant's own green terminal paths. Admission and rework admission refuse before
 claim only when at least one such chain has no candidate. A conditional repair
@@ -6482,11 +6510,10 @@
 missing, incomplete, or unknown evidence is fail-closed and terminates without
 fallback. Transition after onset additionally requires declared durable
 idempotent/resumable semantics plus the idempotency key, resume identity, and
-observed remote state. The current `pr` node MUST NOT fall back after push,
-publication, or auto-merge arming begins until those guarantees exist. For the
-current `pr` node, a publish branch or its pull request present on the remote at
-takeover proves onset; inability to make that observation is treated as already
-past onset.
+observed remote state. The scripted publication stages have no adapter fallback. For any ACP node
+performing external effects, missing or unreadable remote evidence MUST be
+treated as already past onset; converting publication to commands does not
+relax this rule for agent stages.
 
 **In-protocol model and effort selection.** For a candidate whose agent catalog
 entry declares the `protocol` mechanism, the rendered chain candidate MUST carry
@@ -6583,7 +6610,7 @@
 
 **Keys.** `dispatcher.node_timeouts` is a table keyed by node name
 (`dod_gate`, `implement`, `fix`, `review_fix`, `proof_capture`, `review`,
-`disposition`, `proof_verify`, `pr`, `janitor`) whose values are positive
+`disposition`, `proof_verify`, `pr_refresh`, `pr`, `janitor`) whose values are positive
 integers of seconds; `dispatcher.stall_timeout_seconds`
 is a positive integer of seconds for the run-level stall watchdog. A node with
 no configured value MUST resolve to **1800** seconds; the stall watchdog with
--- scenarios.md
+++ scenarios.md
@@ -2132,12 +2132,13 @@
   Given a dispatch target whose "dispatcher.acp_nodes" table sets the implement node to agent codex-acp with a model and an effort
   When the Dispatcher renders the acp_adapter input
   Then the rendered adapter is the Codex adapter carrying that model and its reasoning effort
-  And the publish adapter is unchanged by the implement entry
-
-Scenario: The publish class is unaffected by the implementer default
-  Given a dispatch target whose "dispatcher.acp_nodes" table carries no entry for the pr node
-  When the Dispatcher renders the pr_adapter input
-  Then the rendered adapter is the Claude publish default adapter pinned to Claude Haiku 4.5
+  And the review_fix adapter is unchanged by the implement entry
+
+Scenario: Publication is independent of the implementer adapter
+  Given a dispatch target with no retired pr adapter override
+  When the Dispatcher renders the workflow
+  Then pr_refresh and pr are command stages with no ACP adapter
+  And an explicit ACP override for pr refuses before claim with a removal remedy
 ```
 
 ## Scenario 87 — A node's adapter resolves through three layers and the record names the supplying layer
@@ -2192,8 +2193,8 @@
   And no orchestrator code names the endpoint or the model
 
 Scenario: A Codex-adapter node with a provider definition renders its args
-  Given a dispatch target whose "dispatcher.acp_nodes" table sets the pr node's args to a model_provider definition and a model
-  When the Dispatcher renders the pr node's adapter
+  Given a dispatch target whose "dispatcher.acp_nodes" table sets the review_fix node's args to a model_provider definition and a model
+  When the Dispatcher renders the review_fix node's adapter
   Then the rendered adapter is the Codex adapter command followed by those args in order
 
 Scenario: The rendering is proven hermetically
@@ -2243,18 +2244,18 @@
   I want the Codex adapter identified by a baked path and pinned through its environment
   So that the rendered string cannot name one package while executing another
 
-Scenario: A Codex-pinned publish dispatch renders both adapters in their ratified forms
-  Given a dispatch whose "dispatcher.acp_nodes" table sets the pr node to agent codex-acp with a model and an effort and whose implementer node resolves to the Claude default
+Scenario: A Codex-pinned review_fix dispatch renders both adapters in their ratified forms
+  Given a dispatch whose "dispatcher.acp_nodes" table sets the review_fix node to agent codex-acp with a model and an effort and whose implementer node resolves to the Claude default
   When the Dispatcher renders both adapters
-  Then the publish adapter is its environment assignments in sorted key order followed by the baked codex-acp path
-  And the publish adapter carries model and model_reasoning_effort inside CODEX_CONFIG
-  And the publish adapter carries no "-c model" argument
-  And the publish adapter's CODEX_CONFIG value parses as JSON after POSIX shell tokenization
+  Then the review_fix adapter is its environment assignments in sorted key order followed by the baked codex-acp path
+  And the review_fix adapter carries model and model_reasoning_effort inside CODEX_CONFIG
+  And the review_fix adapter carries no "-c model" argument
+  And the review_fix adapter's CODEX_CONFIG value parses as JSON after POSIX shell tokenization
   And the implementer adapter is byte-identical to the ratified Claude default string
 
-Scenario: The publish adapter declares its agent mode
-  Given a dispatch whose "dispatcher.acp_nodes" table sets the pr node to agent codex-acp with a model and an effort
-  When the Dispatcher renders the publish adapter
+Scenario: The review_fix adapter declares its agent mode
+  Given a dispatch whose "dispatcher.acp_nodes" table sets the review_fix node to agent codex-acp with a model and an effort
+  When the Dispatcher renders the review_fix adapter
   Then the rendered adapter carries INITIAL_AGENT_MODE set to agent-full-access
 
 Scenario: A node that performs no writes is rendered read-only
@@ -2797,7 +2798,7 @@
     When the Dispatcher resolves the integration contract at plan build
     Then the resolved merge strategy is squash
     And the projected gh pr merge argv names the squash method
-    And the pr.md prompt variable for the merge method is squash
+    And the scripted publication command uses the squash merge method
 
   Scenario: A fleet member declares nothing
     Given a governed repository whose declaration omits dispatcher.merge_mode
@@ -3545,11 +3546,11 @@
   So that a removed model or exhausted allowance does not replay a long workflow or silently change its failure
 
   Scenario: v107 primary bytes survive absent and fallback-only configuration
-    Given the pr node has no acp_nodes entry and no new-grammar metadata
+    Given the review_fix node has no acp_nodes entry and no new-grammar metadata
     When the Dispatcher resolves its adapter
-    Then candidate zero is byte-identically the Claude Haiku 4.5 workflow default rendered from the structured built-in default
+    Then candidate zero is byte-identically the Claude Opus 5 workflow default rendered from the structured built-in default
     And `fallbacks: []` alone produces the same bytes
-    And when the pr node carries an explicit structured entry, identity-only or fallback-only fields attach after that primary renders
+    And when the review_fix node carries an explicit structured entry, identity-only or fallback-only fields attach after that primary renders
 
   Scenario: New grammar is version-gated against the resolved factory
     Given a node carries identity, signature, pricing, or a non-empty fallback field
@@ -3580,12 +3581,12 @@
     And an identity-less arbitrary legacy adapter is covered by every live legacy record and continues to mint legacy records
 
   Scenario: Only an exhausted success-critical chain refuses admission
-    Given implement, review, and pr each retain an unheld candidate
+    Given implement, review, and proof_verify each retain an unheld candidate
     And a conditional fix node retains none
     When the Dispatcher evaluates admission
     Then it admits the item
     And if fix is later reached it terminates typed before any adapter without traversing janitor, non-convergence, or needs_human
-    And when instead implement, review, or pr retains none, admission refuses before claim
+    And when instead implement, review, or proof_verify retains none, admission refuses before claim
 
   Scenario: The recorded removed-model diagnostic falls back but a generic 400 does not
     Given the pinned Codex adapter returns the measured ChatGPT-account HTTP 400 diagnostic naming the exact requested model as unsupported
@@ -3610,7 +3611,7 @@
     Given an attempt may have issued an external mutation and absence of onset cannot be proved durably
     When it reports an otherwise eligible failure
     Then reactive fallback does not occur
-    And for the pr node a remote publish branch or pull request proves onset while an unreadable remote is treated as past onset
+    And for any externally mutating ACP node unreadable remote effect evidence is treated as past onset
 
   Scenario: One deadline and post-transition state prevent replay
     Given a node with several candidates and one configured timeout
@@ -3852,7 +3853,7 @@
   Scenario: Verify replays after review
     Given review approved the tree and the captured record exists
     When the proof_verify node replays the steps on an adapter distinct from the implementer's
-    Then it posts one new Proof of Done verified comment and routes to pr
+    Then it posts one new Proof of Done verified comment and routes to pr_refresh
     And the pr node marks the pull request ready and arms auto-merge
   Scenario: A non-reproducible proof routes to fix
     Given the proof_verify replay fails to reproduce one assertion
@@ -3872,6 +3873,31 @@
     Given an item whose Proof of Done pointer names a run id that is not the latest verified record on its pull request
     When needs-attention composes hygiene facts
     Then exactly one fact names the item and the pull request as carrying a stale proof pointer
+  Scenario: Slow hooks after a post-draft rebase are command work
+    Given a draft and verified proof on the run's own recorded head
+    And the default branch advanced after publish_draft
+    And the sandbox pre-push aggregate takes longer than the agent foreground timeout
+    When pr_refresh rebases the branch
+    Then the declared sandbox check suite completes as a foreground command
+    And the branch is pushed with an explicit lease on the recorded prior remote head
+    And capture, review and replay run for the changed head before scripted pr marks it ready
+    And the item's merge hold determines whether auto-merge is armed
+  Scenario: Publication refuses unverifiable provenance and conflicts
+    Given the remote publish head differs from the run's recorded publication head or the rebase conflicts
+    When pr_refresh runs
+    Then it fails closed with a named cause and preserved recovery evidence
+    And it neither force-pushes an unknown head nor resolves the conflict by choosing one side
+  Scenario: Refresh is idempotent and bounded
+    Given a refresh already pushed a new head with durable run provenance
+    When the same refresh is retried against the matching remote
+    Then it resumes from that head and requires proof naming it
+    And three completed refreshes followed by more base movement end with an explicit non-convergence cause
+  Scenario: Publication renders metadata as data and verifies the exact pull request
+    Given the title and body contain shell metacharacters
+    When pr executes the deterministic publication recipe
+    Then the forge receives those literal strings
+    And a matching already-merged pull request is reported as success
+    And a closed-unmerged or unexpected-head pull request fails closed
 ```
 
 ## Scenario 133 — A mixed item is refused ai-only from every entry path, parks for its human-attested leg, and the accept valve refuses until the record exists
@@ -4308,7 +4334,7 @@
     When the operator drives resume for the item
     Then the item is admitted through the ordinary admission valve and a new run of the earlier run's recorded workflow starts
     And the new run's sandbox is a checkout of the publish branch at that head
-    And the new run enters the workflow at the pr stage
+    And the new run enters the workflow at the pr_refresh command stage before pr
     And the new run's record shows no visit to dod_gate, implement, janitor, publish_draft, proof_capture, review or proof_verify
     And the dispatch journal carries one resume record naming the earlier run's identifiers, the pull request number, the head, the resumed-at stage and the source that decided it
     And the item's dispatch_workflow metadata is what it was before the resume

```
