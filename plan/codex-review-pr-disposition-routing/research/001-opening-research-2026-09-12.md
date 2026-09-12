# Permanent Codex routing for review, PR, and disposition

Date: 2026-09-12
Status: opening research
Maintainer direction: permanent routing policy, not a temporary spend-window override.

## Objective

Change this repository's live Fabro implement-work-item routing while leaving
all implementer-class nodes unchanged:

| Node class | Required provider/model | Required effort |
|---|---|---|
| implement, fix, review_fix | Anthropic Claude Opus 5 | high |
| review | OpenAI gpt-5.6-sol through Codex ACP | xhigh |
| pr | OpenAI gpt-5.6-terra through Codex ACP | high |
| disposition | OpenAI gpt-5.6-terra through Codex ACP | medium |

This is a per-repository live dispatcher configuration change for
livespec-orchestrator-beads-fabro. It does not change fleet-wide workflow
defaults for other repositories.

## Established facts

- .livespec.jsonc currently defines no dispatcher.codex_models or
  dispatcher.acp_nodes override. The committed workflow therefore supplies
  Opus 5/high for implement, fix, and review_fix; Opus 4.8/high for review;
  Haiku 4.5/high for pr; and an unpinned Claude ACP adapter for disposition.
- The repository pins sandbox image
  ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.85.3.
- On 2026-09-10, one real turn apiece completed through that exact image,
  @agentclientprotocol/codex-acp 1.10.0, bundled Codex CLI 0.153.4, and the
  Dispatcher's projected ChatGPT credential for gpt-5.6-sol/high,
  gpt-5.6-terra/high, and gpt-5.6-luna/medium. Codex rollout records named
  provider openai and the requested resolved model. The live catalog exposed
  Sol at xhigh and Terra at medium as well.
- The current host credential is ChatGPT-authenticated with no API key, so these
  ACP turns consume the ChatGPT Codex subscription allowance rather than
  Platform API billing.
- dispatcher.codex_models.pr is the existing safe shorthand for moving pr to
  Codex: its expansion replaces the workflow's Claude environment.
- review and disposition require the general dispatcher.acp_nodes surface.
  That surface replaces command/args but merges environment keys. For review,
  the workflow's ANTHROPIC_MODEL and CLAUDE_CODE_EFFORT_LEVEL therefore survive
  as inert residue beside CODEX_CONFIG unless the current configuration contract
  supplies another safe representation. This known cross-provider ambiguity is
  tracked as bd-ib-5j4b and must be an explicit review subject, not hidden by an
  adapter-string assertion.
- A prior Terra review route was operationally reachable but was removed after
  three non-converging review loops. This plan deliberately selects Sol/xhigh
  for review; the old quality result is not evidence against Terra for the
  mechanical pr or triage-focused disposition nodes.

## Required execution sequence

### 1. Notify the two standing sessions before any routing edit

Append an upcoming-change notification to the ledger epics, without changing
their typed next_action metadata:

- bd-ib-jxvgq5 — factory-configurable-model-fallback-priority
- bd-ib-4hgzyn — factory-monitor

Use the append-only work-item comment seam rather than append_handoff, because a
cross-plan notification must not replace either session's authoritative next
action. Each notification must name this plan epic, the exact three new routes,
the unchanged Opus implementer routes, the intended live validation, and the
rollback trigger. Read both comments back through the comments API and verify
their text bodies before continuing.

### 2. Obtain independent Fable and Sol configuration reviews

Before editing the live config, prepare the exact proposed configuration and its
fully rendered adapter strings in a research review packet. Commission two fresh,
independent, read-only reviewers:

1. Claude Fable 5 at xhigh.
2. OpenAI gpt-5.6-sol at xhigh.

Neither reviewer may implement the change. Both must examine the current
.livespec.jsonc, workflow defaults, _acp_node_repository.py,
_acp_node_adapters.py, _dispatcher_fabro_argv.py, the shell-tokenization tests,
and bd-ib-5j4b. They must verify:

- implement, fix, and review_fix remain byte-identical Opus 5/high routes;
- review resolves to Codex ACP + Sol/xhigh in read-only agent mode;
- PR resolves to Codex ACP + Terra/high in write-capable agent mode;
- disposition resolves to Codex ACP + Terra/medium in read-only agent mode;
- every CODEX_CONFIG value survives POSIX/Fabro tokenization as valid JSON;
- the baked adapter path, credential projection, and model efforts are supported;
- no general acp_nodes environment merge turns the route ambiguous or unsafe;
- named workflow variants are either intentionally covered or explicitly
  unaffected; and
- the rollback restores the exact pre-change configuration.

A blocking finding from either reviewer stops rollout. Revise the proposal and
repeat both reviews until each independently records no blockers. Preserve both
review outputs under this plan's research/reviews directory.

### 3. Implement and roll out the permanent live configuration

After both reviews converge, file a scoped implementation child under this plan
and drive it through the repository's factory workflow. The change is expected
to be a hand-edited .livespec.jsonc routing policy, not a mutation through drive
--action set-config, because that command strips JSONC comments.

Use dispatcher.codex_models.pr where possible. Use dispatcher.acp_nodes.review
and .disposition only in the exact representation approved by both reviewers.
Do not add a codex_models.implementer entry and do not edit the Opus 5 workflow
defaults.

Before merge, mechanically render all six ACP-node inputs and assert the exact
provider, model, effort, agent mode, command path, and supplying layer. Run the
focused adapter/config/tokenization tests and the repository's full check suite.
Land the change through the required worktree -> PR -> green checks ->
rebase-merge path. Refresh the primary checkout to merged origin/master; that
committed primary configuration is the live factory policy. A config-only change
must not be misreported as requiring a plugin release unless execution proves
the installed dispatcher cannot consume it.

### 4. Verify the live factory and roll back on attributable failure

After merge, do not use the implementing run as rollout proof: it was dispatched
before the new configuration existed. Verify from the refreshed primary checkout.

Required proof:

1. Materialize a dispatch and capture the recorded resolved adapters, proving the
   three changed nodes and the three unchanged Opus nodes exactly.
2. Complete one live ACP turn for each changed adapter using the same sandbox
   image, projected ChatGPT credential, and rendered command the factory uses.
   Record Codex's own rollout model/provider evidence rather than only the input
   command.
3. Run a post-merge factory canary whose work produces a real diff and reaches
   the Sol review and Terra PR nodes. Record factory host, run id, image digest,
   node outcomes, resolved-model evidence, PR, CI, merge, and janitor result.
4. Verify factory-monitor sees no new attributable factory degradation. The
   disposition route is additionally proven by its exact live ACP turn; if a
   legitimate review finding naturally traverses disposition, record that graph
   evidence rather than manufacturing a false finding.

Rollback immediately if the new configuration causes a pre-run refusal,
malformed or ambiguous adapter, authentication or model-entitlement failure,
changed-node start or turn failure, publish failure, or post-merge canary
regression attributable to this routing change. Rollback means a narrow PR
restoring the exact prior no-override routing state, followed by primary refresh
and Claude-path verification. Do not conceal unrelated pre-existing failures as
a successful rollback, and do not rollback merely because a reviewer correctly
finds a real code defect.

### 5. Notify both sessions after terminal outcome

After successful live verification, append a completion notification to
bd-ib-jxvgq5 and bd-ib-4hgzyn, again without changing their typed next actions.
Name the merged configuration PR/SHA, factory run id and host, resolved models,
image digest, checks, and the fact that Opus implementer routing remained
unchanged.

If rollback occurs, notify both sessions of the rollback instead, naming the
failed evidence, rollback PR/SHA, and restored-route verification. Read every
notification back through bd comments --json using the text field.

## Scope and deferrals

Requirements carried by this plan are the five ordered steps above, the exact
per-node routing table, the permanent-policy ruling, and fail-safe rollback.

Explicitly deferred:

- Implementing automatic provider/model fallback from
  factory-configurable-model-fallback-priority; this plan only notifies that
  session and must not absorb its work.
- Changing implement, fix, or review_fix away from Opus 5/high.
- Changing fleet defaults for sibling repositories.
- Switching the factory to API-key billing.
- Fixing remote-compaction or general Codex credential-preflight defects unless
  one directly prevents this bounded rollout; such a blocker is reported and
  routed to its existing owner rather than silently expanded here.
- Archiving this plan before live canary evidence and completion or rollback
  notifications are durable.

## Initial next action

Record the plan's scope event, then append and verify the two upcoming-change
notifications before preparing the dual-review packet.
