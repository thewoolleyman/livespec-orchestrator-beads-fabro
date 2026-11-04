## The maintainer's statement of what done means

OK, create a new plan named add-features-from--entire-in-livespec that captures all of this and the proposals of things we could add

## Definition of Done assertions derived from that statement

- A reader can find the Entire comparison in the named plan with existing livespec coverage, remaining gaps and source references.
- A reader can evaluate each proposed addition through its intended observable result, build-or-adopt options, dependencies and qualitative effort.
- A reader can distinguish the managed Entire services from independently implementable capabilities and find the proposed sequence, open decisions and explicit deferrals.

# Entire feature comparison and candidate livespec additions

Created 2026-11-01 from the Entire research and repository inspection performed
in this conversation on 2026-10-30. This preserves that research snapshot;
product availability and licensing must be rechecked before adoption.

## Purpose and authorization

Capture the complete comparison between Entire and the livespec family and
preserve concrete proposals for capabilities we could add. The maintainer
authorized creation of this plan and its research/ledger records. The supplied
name is preserved exactly, including the double hyphen:
`add-features-from--entire-in-livespec`.

This is a research and proposal plan. Candidate features below are not ratified
specification changes, admitted implementation work, or authorization to install
tools, upload transcripts, change hosting, or deploy infrastructure. Subsequent
implementation scope must route through the relevant repository's spec and
work-item lifecycle. The creation request is satisfied by a durable comparison
and actionable proposals; it does not require implementing all candidates.

## Main finding

Livespec already supplies much of the intent-to-merge workflow: governed specs,
durable plans, ledger work, execution, review, proof and acceptance. Entire's
largest additions are automatic session provenance, searchable shared context,
and its integrated managed Git forge. Existing intent records and telemetry are
not equivalent to a complete archive of the discussions behind each commit.

There are four useful dispositions: reuse current livespec behavior, implement
an equivalent, adopt an open-source local tool, or use a managed Entire service.
A capability can have more than one viable disposition. Service-specific means
the particular Entire service requires Entire, not that its general function is
technically impossible to reproduce elsewhere.

## Evidence and limits

The comparison inspected livespec core, this orchestrator's specs and actual
implementation workflow, livespec-runtime, and the console repository. It did
not exercise live acceptance flows or establish performance parity. Coverage
means an existing relevant capability, not identical behavior or interface.

Local evidence, relative to this repository unless a sibling is named:

- `README.md`: skill surface, plan/dispatcher and work-item capabilities.
- `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`:
  Definition-of-Done grading, implementation, hard checks, draft publication,
  proof capture, blocking review/fix, independent proof replay, branch refresh
  and auto-merge sequencing.
- `SPECIFICATION/contracts.md`, Persistent Agent Knowledge realization:
  linked `.ai/` topic files, progressively loaded through instruction files.
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_lessons.py`:
  ratified lessons injected into dispatch briefs.
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_reflector_lessons.py`:
  lesson proposals through the PR path.
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_cost_report.py`:
  token and cost reporting, with explicit observability/model-basis limits.
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_otel_scrub.py`:
  allowlisted scalar telemetry and credential-shape scrubbing.
- `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_command.py`:
  resume a published PR through the remaining workflow.
- Sibling `livespec-runtime/README.md`: shipped cross-repository dependency resolution.
- Sibling `livespec-console-beads-fabro/README.md`: TUI operator view across
  specs, ledger, dispatch journals, Fabro runs, GitHub PRs and checks.

The distinction between factory/run checkpoints and Entire session checkpoints
matters: the former do not establish a portable, per-commit archive of every
prompt, response and tool call. Likewise, heading-coverage gap enumeration is
not a semantic implementation comparator or a complete intent-drift detector.

## Current feature coverage

| Entire feature | Current livespec coverage | Remaining difference |
| --- | --- | --- |
| Intent attached to code changes | Versioned specifications, proposals, plans, work-items, criteria and Proof of Done records. | Capture original conversations and abandoned approaches automatically. |
| Trails from idea through merge | Plans/epics and dispatcher stages organize and deliver work. | A unified object joining branches, discussions, sessions and findings. |
| Automated review and fix loops | Blocking review, bounded fixes, proof capture and independent replay in the shipped workflow. | Configurable named monitors and persistent findings management. |
| Merge requirements and approvals | Checks, review policies, merge holds, admission/acceptance valves and head-integrity checks. | One integrated presentation of satisfied, pending and blocking evidence. |
| Cross-repository changes | Cross-repository dependency resolution and fleet operation. | Unified multi-repository change review, not merely dependency edges. |
| Persistent shared knowledge | Instruction files, linked `.ai/` topics, plans, ledger handoffs and ratified lessons. | Automated indexing, extraction and relevance-based retrieval. |
| Agent usage/operational visibility | Run/session correlation, token/cost telemetry, Honeycomb and the operator console. | Integrated session browsing and activity analytics across the full work history. |
| Resume and agent handoff | Durable planning handoffs, provider-neutral briefs and published-PR resume. | Portable restoration of an earlier agent session and its transcript. |
| Extensibility | Drivers, skills, configurable orchestrator CLI seams and ACP adapter/model configuration. | Entire's specific CLI/plugin and hosted integration ecosystems. |
| CI | Repository check suites, GitHub checks, isolated factory execution and post-merge verification. | Entire-native partner setup and shared Trail presentation; no demonstrated reason to replace current CI. |

## Candidate additions

Effort below is a qualitative engineering estimate, not a measured schedule.
Repository ownership is a proposal to verify during scoping, not a cross-repo
assignment. Each candidate includes an observable result for later acceptance
design; these are not implementation-child Definitions of Done.

### Session capture and commit provenance

- Need: recover original prompts, responses, tool calls, decisions and failed
  approaches instead of reconstructing everything from final diffs.
- Proposal: normalize harness events into a versioned session record; bind
  repository identity, commit SHA, work-item, dispatch, run and session ids;
  support idempotent writes, parallel worktrees and explicit retention/export.
- Build/adopt: compare thin integration with Entire CLI against a native capture
  adapter before writing another multi-harness capture implementation.
- Observable result: an operator opens a shipped commit and finds the originating
  session events, or an explicit unavailable/partial result with its cause.
- Likely homes: harness Drivers for capture and shared runtime/orchestrator
  seams for correlation; decide storage ownership before implementing.
- Dependencies/effort: foundational; medium-large across harnesses.

### Transcript redaction and archive controls

- Need: full transcripts contain much more sensitive material than scalar
  operational telemetry; the existing telemetry scrubber is narrower.
- Proposal: apply secret scanning and configurable redaction before every durable
  archive/export write; specify local-only mode, exclusions, access and deletion
  behavior. Document scanner limitations rather than promising perfect detection.
- Observable result: seeded secrets are absent from stored/exported transcript
  fixtures while usable source locations and causal context remain available.
- Likely home: capture/storage boundary, shared across all harness integrations.
- Dependencies/effort: precedes real transcript retention or sharing; medium.

### Explain a file or line using its originating session

- Proposal: connect blame/history, commit/session links and work-item intent in
  one read-only inspection surface, with exact supporting source references.
- Observable result: an operator asks why a line exists and can inspect the
  relevant commit, prompt/tool evidence and governing intent; unsupported answers
  remain explicit rather than fabricated.
- Build/adopt: evaluate Entire `blame`/`why` against a lightweight native adapter.
- Likely homes: shared runtime query API and console/CLI consumers.
- Dependencies/effort: session provenance; medium after capture exists.

### Search code, commits, sessions and decisions together

- Proposal: index historical sessions, commits, specs, plan research and durable
  decisions with keyword and semantic retrieval. Return small, source-linked
  results with repository scope, revision/freshness and permission boundaries.
- Observable result: a task query retrieves the relevant historic decision and
  source locations across allowed repositories, including an explicit indication
  when a source is unavailable or not yet indexed.
- Build/adopt: compare hosted Entire Search, a local index and an alternative
  shared index. CLI availability does not imply hosted Search runs locally.
- Likely homes: shared runtime service/adapter; console and agent-facing tools.
- Dependencies/effort: capture for session history; large for a reliable shared service.

### Code graph and change-impact retrieval

- Proposal: expose definitions, references, callers, relationships and likely
  change impact as ranked file/line evidence for agents.
- Build/adopt: prefer a bounded evaluation of Entire Graph before building an
  equivalent parser/index. It is MIT-licensed and its built-in analyzer parses
  locally; verify current language coverage and behavior on our repositories.
- Observable result: a task retrieves the relevant symbols and affected callers
  with inspectable locations, reducing discovery reads without missing required context.
- Likely homes: a pluggable context provider, consumed by Drivers and factory briefs.
- Dependencies/effort: independently evaluable; medium integration, large equivalent build.

### Continuous memory and task briefings

- Proposal: retrieve relevant curated lessons, docs, session discoveries and code
  context for each task; retain provenance and separate proposed memories from
  ratified specifications and lessons. Evaluate extraction, deduplication,
  staleness, correction and removal rather than treating memory as new authority.
- Build/adopt: Entire Brain works locally by default and is MIT-licensed; compare
  it with extending current linked knowledge and lesson injection. Its hosted
  synchronization is a separate choice.
- Observable result: a fresh session receives the relevant earlier decision with
  its source and can distinguish it from a binding specification requirement.
- Likely homes: shared context/memory adapters and existing lesson governance.
- Dependencies/effort: local docs/code evaluation can precede capture; medium-large.

### Portable session resume, handoff and history import

- Proposal: provide a common handoff bundle with task, branch/head, session
  evidence and pending obligations; evaluate harness-native restoration versus
  contextual restart in another agent. Import earlier transcripts with their
  provenance and read-only origin explicitly identified.
- Observable result: another supported agent continues a task with the correct
  code state and supporting context, with branch/reset effects made explicit.
- Likely homes: Drivers and shared runtime, with orchestrator continuation rules retained.
- Dependencies/effort: capture/normalization; medium-large. Existing published-PR
  resume remains a distinct feature.

### Review monitors and persistent findings

- Proposal: add configurable security, intent-match and code-quality review
  profiles using existing review/fix infrastructure; preserve severity, location,
  reasoning, finding disposition and reviewed-head identity across pushes.
- Observable result: reviewers can inspect, fix, resolve or dismiss a finding,
  and a later push clearly marks whether it is current, stale or re-evaluated.
- Likely homes: orchestrator review evidence and console; preserve proof requirements.
- Dependencies/effort: existing review loops are the foundation; medium. A score
  is a model judgment, not a measured probability or a substitute for proof.

### Unified work view across repositories

- Proposal: extend the console to join plan intent, dependent changes, PR checks,
  sessions, proofs, approvals and findings across repositories. Add a browser
  surface only if the TUI/backend evaluation establishes a need.
- Observable result: an operator sees what blocks a multi-repository outcome and
  can follow each displayed fact to its owning ledger/run/forge evidence.
- Likely homes: console presentation over existing authoritative stores.
- Dependencies/effort: links/identities first; medium-large for comparable polish.

### Activity summaries and agent-usage analytics

- Proposal: generate source-linked recaps from work/session evidence and extend
  existing telemetry with activity categories such as discovery, implementation,
  checking, review and rework; compare model usage and tokens per accepted change.
- Observable result: a recap points to its supporting changes and an operator can
  explain costly rework without double-counting repeated usage reports.
- Likely homes: current Honeycomb pipeline and console; use existing price/model
  observability semantics rather than introducing a second accounting authority.
- Dependencies/effort: summaries can begin with current records; richer activity
  breakdown depends on session normalization; small-medium integration.

## Managed Entire capabilities and practical alternatives

| Specific Entire service | Requires Entire for that service | Independent alternative |
| --- | --- | --- |
| Distributed regional Git network, managed mirrors and Entire-native branches | Yes. | Operate another forge/mirror network; matching a managed global service is substantial infrastructure work outside livespec's present role. |
| Hosted workspace, Trail interface, accounts/permissions and native integrations | Yes. | Extend the console or use another forge/workspace; equivalent behavior is buildable. |
| Managed cross-repository Search indexes | Yes. | Build or adopt an independently hosted/local index with its own access/freshness rules. |
| Hosted Brain memory synchronization | Yes for Entire's backend. | Use local Brain or another shared-memory backend; local memory is not inherently service-exclusive. |

Entire's performance numbers are vendor benchmark claims, not measured expected
improvements for our fleet. Regional placement, permissions, availability,
retention and billing require their own evaluation if hosting is later proposed.
The current Gates documentation says Trails use a backing GitHub pull request
for CI: a move-past-PR message does not establish full workflow independence.

## Recommended sequencing and evaluation design

Start with a small repository/task sample and compare current livespec, local
Entire-tool integration and a minimal native alternative. Preserve the existing
spec, plan, ledger, proof and PR authorities throughout the experiment.

1. Verify current APIs/licenses and locate existing capture/context work across
   the family before selecting ownership or creating duplicate implementation work.
2. Design the provenance/storage/redaction boundary; evaluate it with synthetic
   transcripts before retaining real sessions.
3. Evaluate local CLI capture and line explanation, and independently evaluate
   Graph/Brain retrieval on code/docs where session history is not yet available.
4. Add indexed history retrieval and portable handoff once provenance is reliable.
5. Join findings, sessions and multi-repository work in the console; add analytics
   and recaps using the same evidence identifiers and telemetry.

Use fixed tasks with known decision/source evidence. Measure answer correctness,
source fidelity, context freshness, input/cache/output tokens, tool calls,
latency, capture overhead, storage growth and tokens per accepted item. Verify
review/proof outcomes and rework do not regress. Treat vendor token-saving
benchmarks as hypotheses; require a repeatable comparison on our workloads.

## Decisions to resolve before implementation

- Native implementation, open-source adapter, hosted service, or a mixture for
  each candidate; adopt only after a reproducible local evaluation.
- Storage location and lifecycle: Git refs versus external storage, local-only
  operation, retention/deletion, worktree concurrency and portability.
- Supported harnesses and capture completeness, including tool calls, subagents,
  compaction and earlier-history imports.
- Ownership across core, runtime, Drivers, orchestrator, dev-tooling and console;
  avoid introducing direct Driver/orchestrator coupling contrary to core contracts.
- Boundaries between retrieved evidence, proposed memories and ratified law.
- Shared search access controls, repository scoping and unobservable/stale results.
- Evaluation budget and success thresholds before any fleet-wide enablement.

## Explicit deferrals

- Implementation children and ratified spec amendments are deferred to scoped
  follow-up work under this plan; the current request captures proposals only.
- Tool installation, transcript backfill/export and hosted sync are deferred to
  a bounded evaluation with an explicit data/spend scope.
- Git-hosting migration and construction of a global forge are deferred unless a
  measured hosting bottleneck motivates a separate infrastructure plan.
- Replacement of existing planning, proof, review and CI is deferred: substantial
  coverage already exists, and this research establishes no need for replacement.
- A browser UI and specific CI/deployment partner integrations are deferred until
  the console/backend evaluation identifies a concrete operator need.
- Final architecture, model choices, benchmark thresholds and cross-repo ownership
  are intentionally unresolved; future scoping records their evidence and decisions.

## Sources from the original research snapshot

- [Entire homepage](https://entire.com/).
- [Trails](https://entire.com/features/trails), [CLI](https://entire.com/features/cli),
  [Sessions](https://entire.com/features/sessions), [Plugins](https://entire.com/features/plugins).
- [Code Hosting](https://entire.com/features/code-hosting) and
  [hosting behavior](https://docs.entire.com/guides/repositories/overview).
- [Trail Agents and Agent Insights](https://docs.entire.com/guides/trails/agents)
  and [merge gates](https://docs.entire.com/guides/trails/gates).
- [CLI and hosted surface](https://docs.entire.com/platforms/cli-and-entire-com),
  [checkpoint storage](https://docs.entire.com/guides/checkpoints/checkpoint-storage),
  [session resume](https://docs.entire.com/guides/sessions/resume-sessions),
  [multi-agent review](https://docs.entire.com/cli-reference/review).
- [Search](https://docs.entire.com/guides/search/overview),
  [Graph](https://docs.entire.com/guides/graph/overview),
  [Brain and optional hosted synchronization](https://docs.entire.com/guides/brain/overview).
- [Security and redaction limits](https://docs.entire.com/security).
- MIT-licensed repositories inspected during the research:
  [CLI](https://github.com/entireio/cli),
  [Graph](https://github.com/entireio/entire-graph),
  [Brain](https://github.com/entireio/entire-brain).
- [Preview pricing](https://entire.com/pricing): the inspected page offered the
  platform features with signup and charged agent token usage; pricing and preview
  terms are time-sensitive and are not an architectural dependency of this plan.
