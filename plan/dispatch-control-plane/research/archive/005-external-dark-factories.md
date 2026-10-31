# 005 — Dark factories and autonomous software production: external research

[Back to index](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/README.md)

**Archived — supporting research, 25 October 2026.** Retained as evidence for the current reports. Observations and source checks describe that date, not a fresh assessment of the running system.

As of **2026-10-25**, autonomous software production is established for bounded work inside well-prepared engineering environments: Stripe reports more than 1,300 agent-written, human-reviewed pull requests merged weekly, while OpenAI reports substantial gains from moving supervision from coding sessions to tracker-managed work. The most transferable architecture combines deterministic admission, resource limits, lifecycle transitions and publication controls with model-driven planning, implementation and diagnosis. Claims of eliminating human code review exist, notably StrongDM’s factory, but carry substantially less published outcome evidence. The newest relevant infrastructure separates durable work and session state from replaceable execution: Factory’s October OpenCompute design records desired and observed computer state in Postgres; Anthropic’s Managed Agents keeps session history outside both harness and sandbox. For this fleet, the evidence supports a deterministic scheduler over shared, durable control state, with an LLM coordinator retaining bounded planning and exception judgment, and the existing needs-attention surface carrying actionable decisions. A published, independently validated solution to allocating expiring account allowances and non-expiring local inference across tenants was not found in the sources examined. Sources: [Stripe, 2026-02-19](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2), [OpenAI, 2026-04-27](https://openai.com/index/open-source-codex-orchestration-symphony/), [StrongDM, 2026-02-06](https://factory.strongdm.ai/), [Factory, 2026-10-14](https://factory.com/news/opencompute), [Anthropic, 2026-04-08](https://www.anthropic.com/research/managed-agents).

## Findings

Research cutoff and access date: **2026-10-25**. Dates below are publication dates unless explicitly described as access dates. An undated documentation page is a current documented contract observed on the access date, not proof of when a feature shipped. “Practitioner report” means an operator describes its own system; its numbers remain self-reported. Vendor benchmarks, product promises, independent observational studies and controlled experiments are identified separately. None of the commercial production numbers below should be read as an independent audit.

Here, a pull request is abbreviated **PR**, continuous integration is **CI**, a virtual machine is **VM**, and a large language model is **LLM**. Finding identifiers F01–F16 link the evidence to the recommendations later in the note.

### F01. Stripe demonstrates a hybrid pipeline at substantial production volume

**Sources and dates:** [Minions, part 1](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents), **2026-02-09**; [part 2](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2), **2026-02-19**. **Evidence:** detailed first-party practitioner architecture and operational throughput report.

Stripe’s Minions start from Slack, an internal application, a command line or a web interface. A run gathers relevant context, implements a task, executes checks and prepares a branch and PR. Humans review the result. Part 1 reports over 1,000 such merged PRs weekly; part 2 reports over 1,300. These are merged changes, rather than merely generated patches, but neither article gives the number of attempted runs or aggregate reviewer time.

The harness is a fork of Block’s goose. Its “blueprints” are code-defined workflows containing both agent nodes and deterministic nodes. Implementation and fixing CI failures use model judgment. Running configured linters and pushing changes are enforced by code. Relevant linked context can be fetched before the model starts; tools come from a curated subset of a central MCP service, Toolshed.

Workers receive prewarmed EC2 development environments, targeting readiness in ten seconds, with code and caches prepared. These environments are isolated from production and unrestricted internet access. Environment isolation enables unattended execution without requiring interactive confirmations for each shell action.

Stripe performs fast local feedback before expensive CI and permits at most two CI rounds in the standard flow. After the second push and CI run, it returns the branch for human scrutiny. This is a concrete bounded-retry policy, not an instruction to keep asking a model to try until it reports success. Published detail is strong on execution and feedback, weaker on fleet admission, account-budget allocation and durable scheduler implementation.

### F02. OpenAI separates managing work from managing sessions, but Symphony is not a distributed budget scheduler

**Sources and dates:** [Harness engineering](https://openai.com/index/harness-engineering/), **2026-02-11**; [Symphony announcement](https://openai.com/index/open-source-codex-orchestration-symphony/), **2026-04-27**; [Symphony specification](https://github.com/openai/symphony/blob/main/SPEC.md), undated living specification accessed **2026-10-25**; [Codex Cloud documentation](https://developers.openai.com/codex/cloud/), undated, accessed **2026-10-25**. **Evidence:** first-party production experience, published normative scheduler contract, and product documentation.

The harness report describes approximately 1,500 opened-and-merged PRs over five months, initially driven by three engineers, with a reported average of 3.5 PRs per engineer per day. Humans supplied priorities and acceptance criteria; agents implemented, tested, reviewed and handled feedback. Worktree-specific application instances and observability let agents check actual behavior. The report describes recurring cleanup PRs often reviewable in under a minute; that is a narrow maintenance-work claim, not a measured human-time average for all changes.

Symphony arose because supervising three to five concurrent sessions already imposed substantial context-switching costs. It watches a tracker, creates per-issue workspaces, starts agents, reconciles issue state and restarts failed or stalled work. The announcement reports a **500% increase in landed PRs on some teams over the first three weeks**. It supplies neither cohort sizes nor a controlled comparison, cost per change or downstream defect series.

The specification assigns polling, eligibility, claims, concurrency, retries and reconciliation to a single orchestrator. It specifies global and per-state concurrency limits, failure backoff, stall detection, and reconciliation before new dispatch. A repository-owned `WORKFLOW.md` holds settings and prompts. Coding-agent actions perform much of the tracker and PR workflow. A successful run can end at a human-review handoff rather than completion.

The crucial limitation is explicit: scheduler state is authoritative **in memory**, and restart recovery uses the tracker and surviving workspaces without restoring exact scheduler state. It explicitly excludes being a general distributed job scheduler. Observing token counters and rate-limit snapshots does not establish an account-budget allocation algorithm. This contract therefore offers admission and recovery patterns, while leaving this fleet’s shared holds, reservations and cross-host authority problem unresolved.

Current Codex Cloud documentation separately describes published environments, per-task workspaces, remote execution while the user’s computer sleeps, and review of changes and test results before commit or PR creation. That product surface should not be conflated with Symphony’s open orchestration specification.

### F03. Factory’s October OpenCompute design directly addresses durable compute intent and heterogeneous hosts

**Sources and dates:** [Environments and sandbox fleets](https://factory.com/news/droids-now-have-a-fleet-of-sandboxes), **2026-10-12**; [Introducing OpenCompute](https://factory.com/news/opencompute), **2026-10-14**; [Missions documentation](https://docs.factory.com/missions/overview), undated, accessed **2026-10-25**. **Evidence:** vendor architecture disclosure, product launch claims and documentation. OpenCompute was announced in **private preview**; the article says open-sourcing is planned, not completed.

An Environment defines repositories, tools and dependencies, built into a reusable image before a Droid starts. Factory says it rebuilds environments every few hours, validates them and promotes only successful builds. Automations start fresh sandboxes from validated builds; Missions organize larger efforts into planned features, milestones, workers and validation.

OpenCompute separates a common compute lifecycle from provider implementations. A self-hosted Go control plane stores **desired and observed computer state in Postgres**. Creating a computer first records durable intent. A reconciler provisions, observes, retries and advances the lifecycle, including after a control-plane restart. Immutable Builds and S3-compatible artifacts/snapshot payloads separate preparation and persistence from machine allocation.

Provider-specific operations live in standalone gRPC drivers. A required Core conformance profile and optional Suspend, Snapshot and Fork profiles expose backend differences. Unsupported operations are rejected before changing durable state. The article describes integrations across several cloud and local infrastructure approaches without claiming every backend has equal maturity.

Connections to Factory and from provisioned sandboxes are outbound. Compute placement, inference routing and session storage remain separate decisions: self-hosting the sandbox alone does not establish local session storage. This is a particularly useful distinction for our multiple hosts and future local models.

The published design covers compute lifecycle durability, not a proven multi-tenant optimizer for purchased model allowances. Missions documentation also acknowledges unresolved correctness, cost and parallelization tradeoffs. Its orchestrator is itself an agent; that is a task-execution choice, not evidence that capacity admission must be model-driven.

### F04. Anthropic’s Managed Agents makes session history independent of the runner and sandbox

**Source and date:** [Scaling Managed Agents: Decoupling the brain from the hands](https://www.anthropic.com/research/managed-agents), **2026-04-08**. **Evidence:** first-party platform engineering report, including internally measured latency improvement.

Anthropic describes three separate interfaces: a **session**, holding an append-only event log; a **harness**, running the model/tool loop; and a **sandbox**, executing code and holding working files. Its earlier design put them in one container, making failure diagnosis difficult and losing sessions when that container failed.

In the revised design, a replacement harness loads the durable session log and resumes from recorded events. A failed sandbox becomes a tool error; it can be reprovisioned without losing the session. The session log retains history independently of whatever subset or summary the model currently receives. Context compaction and durable storage therefore have different responsibilities.

The same separation permits inference to start before a sandbox is provisioned. The authors report approximately **60% lower median time to first token and over 90% lower p95**. Those are startup-latency results, not software throughput or merge-rate results.

Credentials are mediated outside the generated-code sandbox, including through tool proxies and managed Git access. The relevant architectural lesson is that a runnable container, durable conversation, durable work record and credential authority need not share a lifecycle. The article does not establish exactly-once external actions, nor a fleet-wide account scheduler: resuming a log cannot by itself prove whether a remote operation completed before a crash.

### F05. Factory publishes unusually concrete model-routing evidence, including cache effects

**Sources and dates:** [Factory Router launch](https://factory.com/news/factory-router), **2026-06-01**; [Why routing belongs in the harness](https://factory.com/news/model-routing-belongs-in-the-harness), **2026-08-24**; [Inference savings update](https://factory.com/news/factory-router-inference-savings), **2026-09-23**; [Mentlio acquisition](https://factory.com/news/mentlio), **2026-10-09**. **Evidence:** vendor benchmarks, vendor production accounting and architecture arguments; the acquisition is strategic positioning, not a result.

Factory distinguishes provider routing from model selection. A gateway can enforce allowed endpoints, limits and provider failover. The harness additionally sees the task, session history, cache state, subagent assignments, test failures and outcomes. It can choose models for bounded worker and review jobs and escalate when an efficient model struggles. Factory describes using a different model family for its default validator and implementer.

The August article explains why switching purely on per-token price can be expensive: moving a long conversation can lose a warm prompt cache. Its cache-blind cost comparison is a modeled counterfactual holding the observed trajectory constant, not an experiment proving a different agent would follow that same trajectory. Its reported median Mission has 423 turns across ten sessions and about twelve hours; these are vendor workload observations, not guaranteed task sizes.

The September article reports **63% aggregate savings for the week ending September 13**, relative to pricing the workload at published frontier-model rates. For **September 5–18**, it separately reports **60% aggregate savings**, **72.5% median session savings**, and **84% of sessions saving at least half**. These periods and aggregation methods differ. The product page’s rounded 63% headline should not overwrite the dated report’s more specific 60% result for the two-week cohort.

These comparisons establish neither 63% lower fully loaded cost per merged change nor randomized equivalence in production quality. The launch provides same-task benchmark comparisons, but production comparisons face workload selection effects. Dedicated tokens-per-minute capacity, approved provider failover and internally hosted endpoints are documented options. Published material does not expose the full tenant fairness, quota-reset or account-reservation algorithm. Mentlio’s token-allocation framing reinforces that this remains an active product problem.

### F06. StrongDM’s dark factory shifts acceptance to scenarios and behavioral simulation

**Source and date:** [Software Factories and the Agentic Moment](https://factory.strongdm.ai/), **2026-02-06**, Justin McCarthy. **Evidence:** practitioner manifesto and architecture account; no controlled evaluation or published aggregate merge/cost dataset.

StrongDM describes non-interactive development in which specifications and scenarios guide agents through implementation and validation without human code review. Its team formed on July 14, 2025. The important mechanism is the separation between the implementation’s own tests and end-to-end scenarios, often held outside the codebase as a holdout.

Its Digital Twin Universe provides behavioral versions of dependencies including Okta, Jira, Slack and Google services. This supports repeatable failure injection and scenario volumes exceeding practical live-service limits. Acceptance for agentic behavior can involve an LLM judge. StrongDM’s “satisfaction” measures the fraction of observed scenario trajectories judged likely to satisfy users, rather than treating one green test run as the whole acceptance definition.

The account is useful evidence that acceptance engineering can be the main factory product. It is weaker evidence for universal removal of human review: it does not publish an audited escape rate, review-free change denominator, cost per accepted change, or long-term maintenance comparison. Behavioral twins also need independent fidelity evidence before their success can establish real-service correctness; that is an inference about transferring this design, not a fidelity measurement supplied by StrongDM.

Its suggested token expenditure of at least $1,000 per engineer per day is a provocative operating guideline. It is not a measured optimal burn rate and should not become this fleet’s throughput objective.

### F07. Factory tests an independent completion standard, with important experimental qualifications

**Source and date:** [What it takes for coding agents to complete large software tasks](https://factory.com/news/what-it-takes-for-coding-agents-to-complete-large-software-tasks), **2026-08-27**. **Evidence:** vendor-authored experiment on 24 selected ProgramBench tasks; disclosed methodology, rather than production merge statistics.

The experiment compares a single agent, which implements and decides when it is done, with a system containing an implementer, a validator and an orchestrator. Before implementation, the validator constructs an executable account of completion from the reference behavior. Its instrument and raw results stay with the validator; clustered findings reach the implementer. The orchestrator adjudicates findings and decides when to ship.

In the highlighted GDAL comparison, observed behavioral parity rises from approximately **36% to 90%**. This is a selected example, not the average improvement, nor the best-single-agent frontier across all models. The broader lesson is the demonstrated failure class: an agent may stop after locally correct work because its measure of completion omitted much of the required behavior.

The report explicitly states that campaigns were **not compute-matched**, each cell was a **single campaign**, tasks were **hand-selected**, and several cells used a substituted model after safety blocks. Thus, the result supports investigating independent validation and completeness checks; it does not isolate role separation as the sole cause or prove a particular cost/quality advantage.

This bears directly on specification-driven factories: semantic coverage of requirements, a procedure that measures those requirements, and fresh evidence against the shipped artifact are three different things.

### F08. Cursor’s scale experiment supports role separation and exposes coordination failures

**Sources and dates:** [Scaling long-running autonomous coding](https://cursor.com/blog/scaling-agents), **2026-01-14**; [Cloud Agents documentation](https://cursor.com/docs/cloud-agent), undated, accessed **2026-10-25**. **Evidence:** vendor research prototype and current product documentation; the prototype is not a production reliability benchmark.

Cursor first let equal-status agents coordinate through a shared file and locks. Agents held or forgot locks, bypassed coordination, and turned twenty workers into the effective throughput of two or three. Optimistic concurrency improved mechanics but did not fix responsibility: agents avoided difficult work and churned on small changes.

The next design separated planners, workers and a cycle-level judge. Planners explored and generated tasks, workers concentrated on their assignments, and the judge decided whether another cycle was needed. Periodic fresh starts limited drift. An integrator role was removed after it became a bottleneck. Different models performed differently in planning and implementation roles.

The experiment reports hundreds of workers, close to a week building a browser, and more than a million lines across roughly a thousand files. Those demonstrate sustained parallel activity. They do not establish production browser completeness, a merge-success denominator or favorable cost per useful change. The article also reports a specific merged video-rendering improvement, which is a stronger deployment signal than code volume alone.

Current Cloud Agents documentation describes isolated VMs, saved environment builds, separate branches, configurable hooks, screenshots/videos/logs and remote inspection. It identifies Cloud Agents as the current name for Background Agents. It exposes spend controls but does not disclose the internal fleet scheduler or tenant-budget algorithm.

### F09. Anthropic’s long-running and team experiments emphasize handoff state and test decomposition

**Sources and dates:** [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), **2025-11-26**; [Building a C compiler with parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler), **2026-02-05**; [Claude Code agent teams](https://code.claude.com/docs/en/agent-teams), undated, accessed **2026-10-25**. **Evidence:** vendor harness experiments, a disclosed research-project cost, and experimental-feature documentation.

The long-running harness uses an initializer to establish environment setup, a feature inventory and progress records, then incremental coding sessions that leave structured handoffs alongside Git history. Its target failures are unfinished work becoming illegible after context rollover and agents prematurely declaring completion. This is session-continuity scaffolding; it does not establish a distributed control-state service.

The compiler experiment ran **16 agents**, nearly **2,000 sessions**, and consumed about **two billion input and 140 million output tokens** over two weeks, costing **just under $20,000 in API usage**. It produced an approximately 100,000-line compiler with substantial test and Linux-build capability. That is project inference cost, excluding a fully loaded accounting of human and infrastructure effort, and cannot be converted into cost per merged production change.

Coordination used task-lock files synchronized through Git, with no orchestration agent. Parallelism worked when failures were independent; it collapsed when all agents encountered the same Linux-kernel blocker. A known-good GCC oracle and a decomposition-oriented test harness made independent progress possible. The author also observed time blindness and context pollution from excessive test output.

Current Claude Code teams use a lead, independent teammate contexts, messaging, shared tasks, file-locked claiming and enforceable completion hooks. The docs warn of significantly higher token use, early stopping, lagging task state and lack of resumption for in-process teammates. Teams remain experimental. They are useful within-run collaboration machinery, but their documented lifecycle is insufficient as the durable authority for a multi-host factory.

### F10. Commercial background-agent surfaces expose useful run contracts, but hide much fleet scheduling

**Evidence:** the following are first-party product/API contracts, with a separately identified Devin operational claim. Undated documentation was accessed **2026-10-25**.

| System and dated source | Published intake, execution and handoff | Capacity and persistence detail actually exposed |
|---|---|---|
| **Cognition/Devin:** [2025 performance review](https://cognition.ai/blog/devin-annual-performance-review-2025), **2025-11-14**; [current session API](https://docs.devin.ai/api-reference/v3/sessions/post-organizations-sessions), undated | Clear upfront tasks and verifiable outcomes; playbooks, repositories and structured-output requirements are API inputs. Humans remain relevant to ambiguous scope and code-quality review. | API fields include a per-session `max_acu_limit`, platform or customer-machine-pool placement, and `resumable`, which controls whether stopped VM state is retained. These do not reveal a fleet allocation algorithm. |
| **GitHub Copilot coding agent:** [launch architecture](https://github.blog/news-insights/product-news/github-copilot-meet-the-new-coding-agent/), **2025-05-19**; [Agentic Workflows safe outputs](https://github.github.io/gh-aw/reference/safe-outputs/), undated | Issue assignment leads to an Actions-backed coding environment and PR. The launch describes restricted branches, human review and controlled workflow execution. Agentic Workflows separately lets an agent request structured actions that permission-controlled jobs execute. | Actions supplies the execution substrate. Safe-output handlers validate allowed operation types and limits; some current handlers can merge after configured policy gates. Neither source supplies cross-account expiring-token allocation. |
| **Google Jules:** [getting started](https://jules.google/docs/), [scheduled tasks](https://jules.google/docs/scheduled-tasks/), [limits](https://jules.google/docs/usage-limits/), all undated | A repository task runs in a VM, with dependency setup and a plan the user can review before edits. Scheduled tasks support recurring maintenance. | Daily task allowances use a rolling 24-hour window; concurrency is separately limited by plan. Task history remains accessible after an allowance is exhausted. These are product admission constraints, not a disclosed internal scheduling design. |
| **Amp, originally associated with Sourcegraph:** [agent-to-agent capability](https://ampcode.com/news/from-agent-to-agent), **2026-07-17**; [Orbs documentation](https://ampcode.com/docs/orbs), undated | Agents can spawn threads on remote or local machines and exchange messages/files. Orbs provide an isolated machine, reviewable changes, services and evidence in the same thread. | Orbs sleep after inactivity and resume with conversation, files and services. Spawn pacing allows a burst of twenty metered orbs, then one new start every five minutes; later requests wait. This is a concrete queueing contract rather than unlimited instantaneous fan-out. |

Devin’s performance review reports **67% of its PRs merged, versus 34% a year earlier**, alongside faster execution and lower resource consumption. It does not supply a cohort denominator or controlled task-mix comparison. The same review explicitly names ambiguous requirements and mid-task scope changes as weaknesses. These qualifications are more actionable for work intake than an “infinite capacity” marketing description.

Across these products, the exposed unit is a run or task with context, an environment, limits, state and a reviewable result. There is insufficient published detail in these sources to reconstruct their complete internal account schedulers or prove their sessions are portable across arbitrary customer hosts.

### F11. Claude Code routines demonstrate that triggers, quotas and delivery semantics are separate concerns

**Source and date:** [Cloud scheduled tasks, formerly routines](https://code.claude.com/docs/en/routines), undated, accessed **2026-10-25**. **Evidence:** current research-preview product contract, not measured fleet outcomes.

The documented feature stores a prompt, repositories and connectors, then starts work on a schedule, an API call or GitHub events. It executes on managed infrastructure or an organization’s self-hosted environment, independent of a user’s laptop. Each trigger creates a session; GitHub updates do not reuse one session automatically.

The current documentation makes an unusually important distinction: some limits **queue** work, others **reject** an invocation, and excess GitHub events can be **dropped**. Scheduled runs exceeding the documented hourly account limit wait for reset. API/task limits can reject calls; subscription exhaustion rejects additional runs unless enabled metered usage permits continuation. A cron trigger therefore does not establish guaranteed eventual execution.

The feature also separates saved task configuration from run-specific text. API fire payloads are marked as untrusted data and require the saved prompt to opt into acting on them. This is an example of distinguishing authoritative instructions from event evidence.

For our purposes, the transferable contract is explicit trigger identity, run identity, admission outcome and replay/reconciliation behavior. A routine can initiate a bounded worker or investigation; its mere existence should not be mistaken for durable delivery, global fairness, or evidence that an LLM must continuously poll the fleet.

### F12. Gas Town combines durable work tracking with a deterministic governor, while retaining host-local control

**Sources and dates:** [Gas Town repository](https://github.com/gastownhall/gastown), [scheduler design](https://github.com/gastownhall/gastown/blob/main/docs/design/scheduler.md), [escalation design](https://github.com/gastownhall/gastown/blob/main/docs/design/escalation.md), living open-source documentation accessed **2026-10-25**. **Evidence:** inspectable project architecture and documented contracts; no independent throughput or economic evaluation was established here.

Gas Town separates an LLM coordinator, workers, lifecycle supervision and a merge processor. Work history persists outside worker context, including through Beads and Git-backed workspaces. Its documented capacity scheduler is ordinary code: queued dispatch contexts, a concurrency governor, batches, failure counters and a circuit breaker after three dispatch failures. Queue records are separate from the work record.

The scheduler documentation is also a direct warning against over-reading “durable.” Its pause state lives in **`.runtime/scheduler-state.json`**, dispatch serialization uses **`flock`**, and active workers are counted through **tmux sessions**. These are host-scoped observations and controls. Durable work records do not turn them into fleet-wide authority. Its use of native `bd ready` is also not portable into our lifecycle-status store, whose repository instructions explicitly require the plugin’s readiness calculation.

Escalations are structured records with source, severity, acknowledgement and bounded re-escalation. The design distinguishes recoverable failures and ordinary work from decisions requiring attention. It explicitly marks category-based routing as **future** functionality; it should not be described as a shipped general routing solution.

This is strong prior art for separating capacity dispatch and attention records from an LLM coordinator. Its documented local control carrier should be rejected for our cross-host requirements, and its operator commands should not be copied into this repository without adapting to our contracts.

### F13. LangGraph makes waiting for a human durable, but resumption can repeat code

**Sources and dates:** [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers), [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), undated documentation accessed **2026-10-25**. **Evidence:** open-source framework contracts, not evidence of autonomous software-factory throughput.

LangGraph distinguishes per-thread graph checkpoints from cross-thread application stores. Checkpoints support recovering failed work and resuming a paused interaction. Its documentation explicitly warns that in-memory savers lose their contents on restart; persistence requires a durable backend.

An interrupt saves state, returns a structured payload to the caller and waits until an external response resumes the same thread. The runner need not occupy an interactive model session while a human decides. Typed response schemas can validate the answer shape.

Resumption has a significant operational consequence: the interrupted node starts again from its beginning, so code before the interrupt executes again. A checkpoint does not supply exactly-once side effects. This is directly relevant to retrying dispatch, posting evidence, creating PRs and applying a ruling after a lost response.

For our existing Fabro workflow, this is a pattern to adapt rather than a demonstrated reason to replace the engine: durable decision records and explicit resumable states can support the needs-attention console without keeping a coordinator alive as the sole owner of the question.

### F14. Ramp shows why shared context matters and why review remains a throughput constraint

**Source and date:** [Linear customer interview with Ramp](https://linear.app/customers/ramp), undated, accessed **2026-10-25**. **Evidence:** vendor-hosted customer/practitioner interview; no audited dataset or publication date on the retrieved page.

The interview says Inspect writes **three of every four PRs Ramp merges**. That is agents’ share of merged work, not the probability that an attempted agent task succeeds. It must not be compared directly with Devin’s 67% merge-rate claim.

Inspect runs in a sandbox integrated with Ramp’s infrastructure and is accessible through web, Chrome and Slack. Sessions are shareable between roles. Its integration with years of specifications, requests and roadmaps in Linear supplies broader context than a single issue prompt.

The interview explicitly says the bottleneck has moved from writing to reviewing code. This is evidence against treating “agents keep working” as the whole control problem. It supports limiting work in progress against the capacity to accept and integrate outcomes, and preparing evidence so a reviewer can decide efficiently. The source does not quantify review minutes per change or establish that 75% of production code is autonomously accepted.

Ramp’s own builder-site article did not yield usable body text through the available retrieval path in this investigation. Consequently, specific claims about its internal Modal, snapshot or scheduler architecture are not adopted from secondary retellings.

### F15. Anthropic’s October source-control account shows that compute and integration can dominate at scale

**Source and date:** [Redesigning source control at Anthropic](https://www.anthropic.com/research/redesigning-source-control), **2026-10-13**. **Evidence:** first-party infrastructure account and internally reported scale figures; not a breakdown of fully autonomous changes.

Anthropic reports growing from approximately **2,500 code changes merged daily in May to over 30,000 daily in September 2026**, and roughly 25 million daily CI checkouts. These are code-change counts, not equivalent to Stripe’s PR metric, and the article does not isolate the unattended-agent fraction.

Its Scion system moves source-control queries and commit operations to services, stores immutable content and changesets centrally, and uses independently scalable regional and node caches. Working copies can be sparse or unnecessary for metadata-only jobs. It reports much smaller infrastructure use, checkouts in seconds rather than minutes, and a 25% CI CPU capacity gain.

The applicable finding is broader than Git: removing repeated setup and unnecessary data movement can create usable fleet capacity without adding model allowance. It is not a justification for this fleet to build a new version-control system. Measure clone, hydrate, test and integration costs before attributing low throughput to insufficient agents or model tokens.

### F16. Independent evidence supports workload-aware evaluation and cautions against stale productivity claims

**Sources and dates:** [AIDev dataset paper](https://arxiv.org/abs/2602.09185), **2026-02-09**; [task-stratified PR study, revised full text](https://arxiv.org/html/2602.08915v2), submitted **2026-02-09**, revised **2026-05-07**; [METR randomized study](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/), **2025-07-10**; [METR follow-up](https://metr.org/blog/2026-02-24-uplift-update/), **2026-02-24**. **Evidence:** independent public-data research, a randomized controlled experiment, and an explicitly qualified follow-up.

AIDev describes 932,791 agent-authored PRs across 116,211 repositories and five agents. The task-stratified study analyzes a filtered **7,156 PRs**: closed PRs in popular repositories with permissive licenses and at least one external review or comment. It reports **69.3% accepted overall**, **82.1% for documentation** and **66.1% for features**. These are selected historical public contributions, principally covering 2025 activity, not an October 2026 benchmark of the current products.

Acceptance means merged among the selected **closed** PRs. Open PRs, unsuccessful attempts that never created a PR, private enterprise work, human repair effort and post-merge defects fall outside that denominator. Agent populations and observation windows are uneven. The study’s workload stratification is useful; its aggregate agent rankings should not be used as this fleet’s routing policy.

METR’s early-2025 randomized study involved sixteen experienced developers and 246 tasks, finding that AI-enabled work took 19% longer. Its own current page marks that result as outdated. The February 2026 follow-up reports raw estimates consistent with improvement, but explains that participation selection, task selection and overlapping agent work make the updated effect unreliable. It does not provide a clean current causal estimate of fleet productivity.

Together these sources support recording real outcomes by task class, including human effort and failed starts, instead of relying on vendor percentages, developer impressions or obsolete model comparisons. Neither gives a transferable current dollar cost per accepted production change for this fleet.

### Pipeline synthesis: what is deterministic and what remains judgment

The following is a synthesis of F01–F13, not a claim that every vendor implements one common pipeline.

| Stage | Published deterministic mechanisms | Model-driven or human judgment | Important boundary for our fleet |
|---|---|---|---|
| Work intake | Tracker polling, webhooks, schedules, identity and filtering: Symphony, routines, Agentic Workflows. | Interpret a request, discover missing context, propose scope or children. | Receiving an event is separate from admitting work or guaranteeing delivery. |
| Specification and acceptance | Required fields, executable checks, retained evidence and protected validation procedures. | Clarify intent, design scenarios, assess ambiguous user outcomes. | An agent’s own declaration of completeness is insufficient evidence. |
| Admission and placement | Eligibility, claims, concurrency, queueing, provider policy and compute lifecycle: Symphony, Gas Town, OpenCompute, Amp. | Classify a task or recommend an allowed resource/model. | A model suggestion must not bypass capacity, a hold, or dependency semantics. |
| Implementation | Environment setup, tool permissions and mandatory workflow nodes. | Code, investigate, use tools and repair failures. | Prevalidated environments make autonomous work more predictable. |
| Verification and review | Run tests, capture artifacts, preserve versions and enforce required gates. | Review semantics, design independent measurements, adjudicate findings. | More reviewers using the same instrument do not prove independent coverage. |
| Publication and merge | Policy-controlled Git/forge operations, merge procedures and validated output handlers. | Resolve conflicts or explain a change; human disposition where required. | A PR, merged change and accepted production outcome are different lifecycle facts. |
| Recovery and attention | Reconciliation, backoff, bounded retry, durable logs/checkpoints and typed interrupts. | Diagnose a novel failure, propose a remedy, make an authorized ruling. | Process liveness is not proof of progress, and retry is not proof that a side effect did not already land. |

### What the published measurements establish

The numerical claims above deliberately retain their denominators. Stripe provides useful **production volume**; Devin provides a vendor **PR merge fraction**; Ramp provides **agent share of merged work**; OpenAI provides an internal **throughput comparison**; Anthropic’s compiler provides **project API cost**; Factory provides **pricing-relative session cost**; independent PR research provides **selected historical acceptance**. None supplies all of: attempt count, task value, human minutes, complete infrastructure cost, post-merge defect cost and a controlled baseline.

In the production and research sources examined, no sufficiently documented current comparison of **fully loaded cost per accepted change** or **total human minutes per accepted change** was found that can be transferred directly to our task mix. OpenAI’s sub-minute cleanup reviews are a useful narrow example, not a fleet-wide answer. Missing economics should remain missing rather than being estimated by dividing unrelated marketing totals.

## What maps onto our problems

The problem letters follow the brief: **(a)** steady-state throughput across expiring model allowances and non-expiring local capacity; **(b)** shared control state surviving hosts and restarts; **(c)** coordinator judgment versus deterministic scheduling; **(d)** actionable human attention without making the maintainer the bottleneck. The decisions below are **research recommendations dated 2026-10-25**, not specification changes, approved implementation decisions or descriptions of capabilities already present in this repository.

### Disposition of each finding

| Finding | Problems | Adopt, adapt or reject | Reason and concrete implication |
|---|---|---|---|
| F01: Stripe blueprints | a, c, d | **Adopt** hybrid workflow boundaries; **adapt** retry limits. | Enforce predictable steps in code and spend model capacity on uncertain work. Bound recovery by failure class and cost; Stripe’s exact two-CI-round policy is a local choice. |
| F02: Symphony | a, b, c, d | **Adopt** reconciliation and tracker-centered work; **adapt** its state model. | Its deterministic hot path fits the Dispatcher. Its single in-memory authority and workspace-based recovery do not satisfy fleet-wide durable holds and reservations. |
| F03: OpenCompute | a, b, c | **Adapt** durable desired/observed state and provider capabilities. | Persist an intended action before executing it, reconcile after restart, and expose honest backend differences. Private preview and planned open source limit immediate dependency assumptions. |
| F04: Managed Agents | b, c, d | **Adopt** independent lifecycles for sessions, runners and sandboxes. | Replacing a host or model context should not erase the work, decisions or evidence. A conversation transcript alone is not the scheduler’s authority. |
| F05: Factory Router | a, c | **Adapt** policy-bounded, cache-aware routing and outcome feedback. | Account for total job cost and cache migration. Let the harness recommend models within approved routes; retain deterministic provider, quota and spend enforcement. Reject interpreting 63% as savings per merged change. |
| F06: StrongDM | c, d | **Adapt** external scenarios and twins; **reject** token expenditure as the objective and blanket review removal. | Strengthen acceptance coverage and controlled validation. Preserve the maintainer’s existing ruling ownership and validate the cost of each acceptance mechanism. |
| F07: Independent completion standard | a, c, d | **Adapt** a separately constructed validation instrument. | Reduce human discovery of omitted requirements. Keep measurement scope and compute cost visible; the published experiment does not prove a compute-normalized advantage. |
| F08: Cursor | a, c | **Adapt** planner/worker separation and freshness; **reject** model-owned locking and code volume as success. | Use explicit ownership and bounded assignments, with durable coordination outside the worker. Increase concurrency only when measured useful output improves. |
| F09: Claude harnesses/teams | a, b, c | **Adapt** handoff artifacts, test decomposition and bounded teams. | Task independence determines useful parallelism. In-process teammate lifecycle cannot carry durable cross-host authority. |
| F10: Devin/GitHub/Jules/Amp | a, b, d | **Adopt** explicit run contracts; **adapt** individual queue/cap/suspend patterns. | Record allowance exhaustion separately from concurrency and distinguish queued, rejected and sleeping work. Evaluate products against our task mix rather than aggregate vendor rates. |
| F11: Routines | a, b, c, d | **Adapt** event/schedule initiation; **reject** treating a trigger as guaranteed execution. | Record every accepted intent and reconcile it to a run. Make drop, rejection and retry behavior visible. No continuously reasoning coordinator is required to notice a timer firing. |
| F12: Gas Town | a, b, c, d | **Adapt** deterministic governor, dispatch records and structured escalations; **reject** local pause files, tmux counts and host locks as fleet authority. | The documented architecture demonstrates exactly how durable work can coexist with non-portable control. Its native readiness command also conflicts with our store semantics. |
| F13: LangGraph | b, c, d | **Adapt** durable questions, response validation and resumable execution. | A human valve can wait without keeping an LLM active. Make replayed side effects idempotent and verify their external outcomes. A new workflow engine is not established as necessary. |
| F14: Ramp | a, c, d | **Adapt** tracker context, shareable evidence and review backpressure. | Agent output must be limited against acceptance capacity as well as inference capacity. Keep context and decisions discoverable beyond an individual session. |
| F15: Scion | a, b | **Adapt** the measurement lesson; **reject** copying the source-control rewrite. | Measure repeated hydration and CI overhead. Reusable immutable environment artifacts may buy more throughput than additional coding workers. |
| F16: Independent studies | a, c, d | **Adopt** task-stratified measurement and explicit denominators. | Measure completed outcomes, all attempts and human time locally. Historical public PR acceptance and self-reported speedups cannot select today’s optimal fleet policy. |

### Proposed control-plane shape

The goal is higher useful steady-state output with lower supervision burden. The directly supporting observations are Stripe’s hybrid workflow and bounded feedback (F01), Symphony’s attention bottleneck (F02), OpenCompute’s durable reconciliation (F03), and the separation of session and execution state (F04). The following architecture is an inference from those sources and our stated constraints; it has not been implemented or experimentally validated here.

**Keep three responsibilities explicit.** The shared control service owns policy, accepted dispatch intent, reservations and reconciliation. Fabro and its hosts execute attempts and report observations. Plan/coordinator sessions interpret goals, groom work, propose priorities and diagnose novel failures. The console renders the existing needs-attention projection. The LLM coordinator can act within delegated authority through typed operations, with the same policy checks as any other caller.

**Separate policy from observations.** Shared holds, priorities and spending policy need an authoritative, versioned record with actor, reason, scope and effective time. Running attempts, measured usage, provider-limit snapshots and host health are observations with timestamps and freshness. A stale usage reading must not silently overwrite an operator’s hold. A local file can cache policy but cannot own it. Static repository policy and live fleet control also need an explicit precedence rule.

**Require an actual server-side exclusion operation.** The proposed operation is a server-backed conditional reservation transaction that compares the policy version, verifies remaining resource allowance, and creates a unique active reservation for the work and attempt; its conditional write and uniqueness constraints enforce exclusion. This is a required new contract, not a claim that the current public Beads surface already supplies it. Expired owners need fencing so an old dispatcher cannot publish a late transition after ownership has moved.

The local [multi-host ledger-writer guidance](../../../../.ai/ledger-writers-are-multi-host.md), recording the maintainer’s **2026-10-12** ruling and earlier measurements, rules out host-scoped fences and warns that metadata updates are not a safe general compare-and-swap primitive. This note does not re-probe those operations. Fleet coordination must honor the public ledger boundary. Choosing between a new shared control service and an extension of the sanctioned ledger service requires proving the required operations, not merely observing that a database is reachable. If ledger and control state have different transaction authorities, use durable intents and idempotent reconciliation across that seam; do not claim one atomic cross-system write.

**Make restarts reconstruct work, rather than reconstructing intention from chat.** Persist dispatch intent, attempt identity, external run identity when known, reservations, terminal evidence and typed decisions. Preserve an event history sufficient to explain admission and recovery. After restart, reconcile accepted intent against Fabro, ledger and forge observations before admitting replacement work. A timeout after submission is an uncertain outcome to resolve, not proof that no run exists. Durable session logs help diagnosis; they do not replace these domain records.

### Scheduling expiring allowances and local models

F02, F05, F10–F12 provide concrete concurrency, routing and queueing mechanisms. None of them establishes a ready-made optimizer for our whole resource mix. The following is a proposed policy to measure, not a vendor-proven algorithm.

1. **Represent each resource pool by its actual constraints.** For hosted accounts, distinguish requests and tokens per minute, subscription windows, reset times, spend limits, approved model routes and uncertainty in usage observations. For local inference, represent accelerator memory, supported models/context sizes, sustainable throughput and concurrent compute capacity. A zero marginal token price does not make a local pool unconstrained or eliminate power and opportunity cost.
2. **Separate eligibility from allocation.** The existing readiness and dependency semantics decide what may start. A scheduler chooses among eligible items under holds, tenant priorities and available pools. It should not substitute a raw lifecycle-status filter for the domain’s computed readiness.
3. **Use remaining allowance and time to reset as planning signals.** For an expiring pool, estimate an affordable burn rate from remaining allowance after a reserve divided by remaining window time. Apply instantaneous limits and reservations for in-flight attempts as additional constraints. This estimate is not a requirement to exhaust the account: without valuable eligible work or sufficient acceptance capacity, leave headroom.
4. **Give non-expiring pools a service-rate policy.** Local capacity should have no artificial allowance-expiry deadline. Schedule for useful completed work per constrained compute time, accounting for model suitability and expected repair/review. Avoid routing a difficult task to a cheap model merely to keep hardware busy.
5. **Start with an explainable fairness policy.** Weighted tenant shares with aging are a reasonable candidate; reserve capacity for short recovery work and accepted high-priority requests. Tune from observed task costs and outcomes. A sophisticated learned policy is premature before reliable reservations, outcome data and fairness measurements exist.
6. **Include acceptance and recovery in capacity accounting.** Review queues, post-merge verification and recurrent recovery work consume scarce resources. Preserve capacity to finish and verify work already started. F14’s review bottleneck is the reason to include this constraint; it is not evidence that a specific work-in-progress cap is optimal.

Model selection has two cooperating components: the harness can propose a model using task shape, validation history and cache state; the deterministic control plane enforces the approved pool and resource envelope. A coordinator can propose an exception with a reason and expected benefit. An LLM should not be the only process remembering whether a tenant is held or how much capacity has already been promised.

### Attention should be durable, scoped and actionable

F02 and F14 identify human attention as a practical bottleneck. F12 and F13 supply structured escalation and durable-interrupt patterns. Apply those patterns through the existing **needs-attention** abstraction rather than adding a competing stream of coordinator prose.

Each fact should name the affected item, plan, tenant or fleet scope; the observed condition and its freshness; the decision or action required; the owning authority; evidence; and any bounded automatic recovery already attempted. Use a stable identity for the underlying condition so repeated observations update one fact. A shared provider outage should produce a fleet-level cause with affected work linked beneath it, rather than demanding a separate ruling for every run.

Distinguish acknowledgement, deferral and resolution. Acknowledging an incident does not establish that its condition is gone. Re-notify on a material change, an agreed deadline or a severity change; ordinary queued work and expected quota recovery can remain visible without paging. When a human ruling is necessary, present a concrete evidence packet and record its typed disposition so a replacement coordinator can continue.

Bounded recovery should happen before routine escalation, with exceptions for conditions that require immediate authority. The recovery budget should depend on the failure class, not one universal retry count. Token exhaustion, missing acceptance criteria, an unavailable provider and a confirmed implementation regression need different remedies. This classification can use an LLM for diagnosis; the allowed next actions and stopping conditions remain enforceable contracts.

## Open questions and what could not be found

The search covered primary vendor engineering posts, current product/API documentation, the named commercial systems, open-source Symphony and Gas Town designs, GitHub Agentic Workflows, LangGraph contracts and independent PR/productivity research. Search discovery used Google and Bing through Bright Data; several searches failed, returned irrelevant results or hit anti-bot errors, and those outputs were not treated as negative evidence. Substantive findings rely on retrieved source bodies. This is a bounded literature review, not proof that no other system has solved a problem.

1. **Multi-tenant allowance allocation remains under-disclosed.** In the reviewed material, no complete, measured algorithm jointly handled account-level resetting allowances, uncertain usage, per-minute provider constraints, heterogeneous hosts and non-expiring local inference. Factory’s router and compute architecture are the closest complementary disclosures, but routing, provisioning and allowance allocation are different problems.
2. **Where should our live control authority reside?** The literature supports durable intent and transactional reservation, but does not choose our public API or ownership boundary. Required proof includes simultaneous writers from separate hosts, stale-owner fencing, restart after an ambiguous submission, hold changes during admission, and accounting reconciliation. The mere use of shared Dolt does not prove these operations exist.
3. **What is our actual bottleneck?** This research did not inspect live fleet telemetry or read the ledger. We still need time spent waiting for allowance, compute, environment preparation, dependencies, CI, merge, review and human rulings. Recommendations about allocation should be tested against those observations rather than assuming the most visible idle worker identifies the scarce resource.
4. **Current cost per accepted change and human minutes remain unknown.** The examined sources do not supply a transferable, fully loaded answer. Locally, record failed starts, retries, abandoned work, inference and sandbox cost, CI use, human active time and post-merge repair against the accepted work item. Report median and tail behavior by task class, with an observation window and complete denominator.
5. **How much independent validation is enough?** StrongDM’s scenarios and Factory’s separate validator are promising, but the reviewed evidence does not quantify their production escape rate or optimal cost. Different model names alone do not guarantee independent blind spots; different evidence and methods matter. Validate scenario/twin fidelity and retain tests against real integration boundaries where applicable.
6. **Where does autonomous recovery stop paying?** Stripe publishes a specific CI retry bound, but no general retry frontier applies across our failure classes. Measure additional successful outcomes against the cost and delay of each recovery attempt, including cases where repeated retries conceal a systemic defect.
7. **How should routing interact with warm context?** Factory explains cache costs, while the fleet may also have account-bound sessions, subscription accounting and local-model context limits. The reviewed sources do not quantify migration overhead or cross-provider session fidelity for our adapters. Model fallback should require explicit compatibility and acceptance evidence.
8. **Which platform details are still only claims or previews?** OpenCompute’s durability and driver design come from a private-preview engineering article, not an independently exercised deployment here. Claude teams and cloud scheduled tasks have experimental/research-preview contracts. No commercial service was run, no open-source orchestrator was installed, and no claimed capacity or restart behavior was tested in this research.
9. **How general are the reported scale figures?** OpenAI’s selected teams, Stripe’s mature internal tools, Ramp’s customer interview and Anthropic’s unusual monorepo do not establish a typical adopter’s outcome. Public PR studies omit private fleets and failed pre-PR attempts. Long-term maintenance quality, alert burden and the unattended fraction remain inconsistently measured.
10. **What was inaccessible?** Ramp’s builder-site page returned no usable article body through the retrieval path used here, so internal architecture details were left unclaimed. Proprietary fleet databases, account schedulers, raw production cohorts and full routing implementations were outside the public sources examined. GitHub documents and living vendor docs were read as current snapshots, not immutable historical releases.

RESEARCH-NOTE-COMPLETE
