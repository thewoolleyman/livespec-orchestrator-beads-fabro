# llm-provider-manager consumer integration

This carrier plan owns the livespec-orchestrator-beads-fabro side of the broader livespec-overseer plan `llm-provider-manager`, anchored by `overseer-tm2qtw`.

## Requirement carrier

Replace the Dispatcher's direct dependence on the manually maintained `CLAUDE_CODE_OAUTH_TOKEN` pool with a per-run credential-selection hook that asks the new livespec-overseer `llm-provider-manager` for an Anthropic inference credential and writes the returned real credential into the existing isolated run overlay. The consumer authenticates directly to Anthropic; no manager process is in the request path. The review adapter uses the same run-scoped credential unless its node contract explicitly requests another capability.

The integration must report authentication, rate-limit, provider-outage, and unknown failures back to the manager using the run and credential-record identities from the secret-free receipt. A provisioning refusal leaves the overlay unchanged and refuses dispatch with a typed actionable error.

## Ordering and proof

Implementation is blocked until the livespec-overseer credential-provider proposal is ratified and the manager's atomic provisioning command is present on that repository's master. The code change is factory-safe and lands only in this repository. Host secret provisioning and live account mutation are excluded from the factory item.

The final cross-repository proof belongs to the parent plan: under the explicit spread strategy, two simultaneous factory runs receive distinct validated account identities; once that proof and legacy-pool migration complete, the old `CLAUDE_CODE_OAUTH_TOKEN` pool is deletable. The default production strategy remains consume-first.

## Read first

- `/data/projects/livespec-overseer/plan/llm-provider-manager/research/001-design-intent-and-decisions.md`
- `/data/projects/livespec-overseer/plan/llm-provider-manager/research/002-verbatim-discussion-transcript.md`
- `/data/projects/livespec-overseer/plan/llm-provider-manager/research/003-review-findings-and-revisions.md`
- `/data/projects/livespec-overseer/SPECIFICATION/proposed_changes/llm-provider-manager-credential-provider.md`
- `.ai/cross-tenant-execution-mirror.md`
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_credentials.py`
