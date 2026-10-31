# Livespec coordination across hosts, containers and agent tools

## Related reports and planning documents

Latest versions on GitHub:

- [Plan charter](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/001-charter-dispatch-control-plane.md)
- [Interactive and headless plan sessions](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/010-interactive-and-headless-plan-sessions.md)
- [Coordinator responsibilities: current and proposed roles](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/011-coordinator-responsibility-mapping.md)
- [Spec-side obligations and autonomy follow-up](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/blob/master/plan/dispatch-control-plane/research/012-spec-side-obligations-and-autonomy-followup.md)

Research summary and proposed direction · 26 October 2026; corrected 27 October 2026

Plan: **Dispatch control plane and durable dispatcher state** (`bd-ib-k6dqwc`)

## What we are trying to achieve

You should be able to open one place, see which work needs your attention, answer
its questions, and leave. The appropriate worker should receive the answer even
if its original session has ended. Other work should continue while a question
waits for you.

The same arrangement should work with Claude, Codex and pi, on an ordinary host
or in a temporary Kubernetes worker pod. A *harness* here means the agent tool
running the session. Changing that tool or replacing the worker must not lose a
question, an answer, or responsibility for finishing the work.

Deployment is part of the goal: package coordination services as containers,
deploy them through version-controlled configuration, and support both Kubernetes
and ordinary hosts, such as through Docker Compose. GitOps means that deployed
configuration comes from Git and is applied through the established deployment
process. Compose is a supported host deployment and a way to test the services
without a Kubernetes cluster.

This report combines earlier research with independent investigations by Astra
and FABle. It includes objections to the direction and corrections to the
researchers' own recommendations. It is a design report, not a claim that these
services have been built or that the specification has changed.

## Where the work stands

The first phase addressed repeated reads of the dispatch journal and unnecessary
growth in successful audit records. Four targeted fixes shipped. The two
performance children of this plan are closed. The maintainer accepted enough
confidence in those fixes to proceed; there is no completed end-to-end speedup
measurement, and another broad benchmark campaign is not a prerequisite.

The second phase has reached research and design. The new direction and previous
review are recorded in the plan ledger. No new coordination service, shared
database, role worker, or deployment was installed by this research.

There is useful infrastructure to build on: `needs-attention` describes work that
needs action; Beads stores work items and plan decisions; Fabro stores factory
runs; the overseer supervises sessions; and the console already sends some human
answers through published orchestrator commands. What is missing is a dependable
way to use these capabilities across machines without terminal panes or files on
the original host.

## What the research supports

### One shared way to ask and answer questions

Both researchers recommend a small network API, with a command-line client that
Claude, Codex, pi and the console can all use. The API is the common interface;
HTTP and JSON are the proposed transport and data format. Each agent tool can
present questions in its own way while using the same records and commands.

A question needs an identity, the work it concerns, the facts shown to the person
answering, the actions allowed, and who may answer. If the facts change, an old
answer must not authorize something new. If the same problem disappears and
later returns, it needs a new occurrence identity even when its wording matches.

For example, a worker asks whether to retry a failed run. Before the answer
arrives, another worker fixes the problem and starts a replacement. The old
“retry” answer must be rejected or presented for reconsideration, not start a
second replacement. This check belongs where the action is applied, as well as
where the answer is accepted: circumstances can change between those steps.

The operator view should distinguish these events:

| What the system reports | What it actually establishes |
| --- | --- |
| Seen | Someone acknowledged the question. |
| Answer recorded | An authorized answer was saved against the relevant version of the question. |
| Action applied | The requested change happened in the owning system. |
| Work completed | The original required result was observed. |

A delivered message is not proof of completion. Nor is a question missing from
a failed or incomplete `needs-attention` read. An unavailable source must remain
visibly unavailable.

### Focused roles, with ordinary code doing the repetitive work

Separating responsibility for plan progress, cross-plan conflicts, broader
incidents and human decisions is useful. The research does not establish that
all four require continuously active LLM sessions.

The proposed arrangement is persistent responsibility with occasional model
execution. Ordinary code checks for changed facts and schedules work. It starts
an agent when judgment is needed. The agent uses its assigned instructions and
authority, records its result, and can finish. A question awaiting a human remains
saved without occupying a worker.

This reduces repeated context loading and token use. Restarting a failed process
is normally a service task; deciding what to do about an unfamiliar fleet-wide
incident may require an agent. Neither should freeze unrelated roles.

### Containers on Kubernetes and ordinary hosts

Use the same released service builds and application contracts in both places.
The initial candidates are an attention API, periodic checks, and processes that
compare recorded work with actual outcomes and repair known inconsistencies.
They may share an image with separate commands; the image split remains a
packaging choice, especially where agent tools have different dependencies.

Kubernetes can run the API as a service and short-lived workers as Jobs. Compose
can run corresponding services on a normal host. Scheduling, secrets, networking
and storage differ, but the meaning of an answer or completed action must not.

This requires replacing real host dependencies: pane coordinates, process IDs,
local locks, local gate-result files, journal-based decisions and host-only
credential injection. Putting the current process in a container leaves those
assumptions intact. Temporary scratch space is fine; irreplaceable decisions and
recovery records are not.

## Where the direction deserves pushback

These are substantive objections, including where a literal reading of the
requested direction would make the system harder to operate.

**Four permanent model processes may be the wrong implementation.** They can
multiply polling, context reloads, costs and conflicting actions. Start with one
useful role and expand when the separation demonstrates a benefit. Roles can be
long-lived even when their workers are short-lived.

**A single shared store should not become a copy of everything.** Beads remains
responsible for work items and plan rulings; Fabro remains responsible for runs.
A unified view can combine them without copying their authority. The dedicated non-Beads Dolt database owns cross-tenant coordination, including
pending decisions and unfinished requests to perform an action. It should reference
existing work items and runs rather than duplicate their state. Multiple
copies of the same truth create another reconciliation problem.

**Not every conversation byte needs the new communication system.** Questions,
answers, assignments, holds and action outcomes must survive worker loss. Debug
logs, streamed model output and incidental conversation need not become
coordination records unless later decisions depend on them. Otherwise we risk
recreating the oversized journal in a database.

**Kubernetes must not become a hidden application dependency.** If only a
Kubernetes Lease, pod annotation or cluster-local file explains who owns work,
Compose is not an equivalent fallback. Shared application records must govern
work ownership and outcomes. The Kubernetes client library warns that leader
election does not guarantee only one client is acting as leader. A replacement
leader cannot by itself prevent the old process from making a late write.

**Docker-in-Docker does not automatically make testing easy.** Most coordination
tests need containers talking to services, not a Docker daemon inside another
container. Nested engines add privilege, networking and cleanup problems. Use
Compose for service tests, a remote factory for real factory execution where
appropriate, and a separately identified nested-engine test only when that
behavior is under test. Building images and running a nested factory are also
different requirements.

**A broker or workflow engine should not be the price of the first useful
feature.** NATS JetStream and Temporal are credible options, but each adds an
operated service and another recovery boundary. Neither alone prevents duplicate
external actions. Start with saved pending work, an API, polling and recovery.
Reconsider a broker when measured delivery volume or latency demands it, or a
workflow engine when coordinating many durable steps warrants it.

**A common API does not prove equal support for all three tools.** Login, trust,
tool discovery and lifecycle behavior differ. Each needs a thin integration and
a real exercise of the intended flow. This repository's pi guidance specifically
requires interactive discoverability evidence; a successful one-shot command
alone does not establish support.

**Non-Kubernetes tests cannot prove the Kubernetes deployment.** They should prove
shared application behavior cheaply. Pod replacement, node loss, network policy,
secret rotation, quota and rollout failures still need deployment-specific checks.
Maintaining two deployment paths costs effort. Running the same contract tests
and released images in both helps keep that cost bounded.

## Where shared coordination belongs — correction of the first report

The chosen home is a **dedicated non-Beads Dolt database**. This was already
approved on 25 October and reaffirmed by the maintainer on 27 October. Beads
itself uses Dolt, but a repository's Beads ledger and the shared coordination
database have different purposes and ownership boundaries.

| State | Owner |
| --- | --- |
| A plan or work item's status, rulings and history | Its repository's Beads ledger |
| Factory run facts | Fabro |
| Cross-tenant questions, answers, delivery, action requests, ownership, holds and reservations | The dedicated coordination database, referencing the owning systems |

A cross-tenant question may concern a particular plan without belonging in that
plan's ledger as operational communication. Workers from any supported harness
or host need a common network interface and durable shared records. Saving this
architectural ruling in the plan ledger is appropriate; making that ledger carry
the fleet's live coordination is not.

FABle proposed using ledger comments for the initial answer flow and introducing
the database later. **That proposal conflicts with the approved boundary and is
not adopted.** The first version of this summary mistakenly made the database
conditional on existing public ledger operations proving insufficient. That was
a synthesis error: the earlier ruling was available and had been read, but the
reviewer's alternative was not checked against it. A reviewer may challenge a
settled choice; its recommendation does not change that choice without a new
maintainer ruling.

The objection is about ownership across tenants, not only transaction strength.
Even perfect comment ordering would not make one repository's plan ledger the
right home for fleet communication. Existing experiments also found that comment
read order does not establish commit order and some concurrent metadata updates
lose changes. Those findings reinforce the need for deliberate concurrency
controls; they are not the reason to choose between Beads and shared Dolt.

The database choice does not establish its implementation guarantees. Prove
provisioning, scoped access from hosts and pods, backup and restore, concurrent
writes and stale-owner fencing against the deployed version. Dolt's optimistic
transactions require conflict handling; do not assume PostgreSQL-style locking.
Competing reservations must contend on shared state, with whole-transaction
retries where required. Failed transactions and ambiguous responses need tests.

These are prerequisites to automatic mutations, not permission to fall back to
Beads. If a required guarantee fails, report the failed assumption and revise
the implementation explicitly while preserving the cross-tenant boundary. A
read-only attention view can arrive while that proof is underway.

## How work survives a crash

An earlier review suggested writing an action marker and skipping the action on
restart. That is wrong: a crash after the marker but before the action loses the
work. Writing the marker afterward instead allows a retry to repeat the action.

The replacement is a saved request with a stable identity, followed by execution
and a check of the actual result. A replacement worker finds unfinished requests.
Before repeating an uncertain action, it asks the owning system whether that
specific action already happened. Where supported, retrying the same identity
returns the original result instead of doing the work twice. That property is
called *idempotency*.

If the result cannot be determined, the request stays unresolved. It must not be
reported complete or retried under a fresh identity just to make progress. Not
every existing command supports this yet. Each automatically executed action needs
its own retry and stale-state rules. A database transaction cannot atomically
include an arbitrary later command to Beads, Fabro or GitHub.

“Exactly once” is therefore not a promise to make for arbitrary shell commands.
Prove the effects of each supported operation instead.

## The proposed first delivery

Build a complete, narrow user flow before expanding the role set or scheduler:

1. Show questions from multiple repositories in one attention view, with evidence
   and available actions.
2. Save one kind of plan question in the dedicated coordination database and accept
   an authorized answer through the same API from Claude, Codex or pi, including
   on another host.
3. Safely apply that supported action, reject stale answers, and recover if the
   worker dies during the operation.
4. Let one focused plan-progress role continue from the observed result while
   unrelated work proceeds.
5. Run the flow under Compose and Kubernetes using the same released services.

Start the storage/concurrency proof alongside this work. A read-only attention
view can arrive before automatic execution. Migrate journal readers incrementally
in parallel, moving each decision to its proper owner and comparing behavior
before switching over.

The wider plan retains the deterministic fleet scheduler, distinct subscription,
metered, local-model and factory-slot capacity rules, one fleet-supply schedule,
queryable per-dispatch model-selection evidence, retirement of obsolete launch
scripts, and updated component and repository-dependency diagrams. A smaller
first delivery does not discard those outcomes.

## Coexisting with the current coordinator

The first delivery supports `gitops-fleet-capacity-monitoring`
(`livespec-dev-tooling-dfixhe`). Its existing long-lived session becomes the first
client of the new services. Its current obligations include factory migration,
Kubernetes observability and fleet stability, beyond the original capacity
charter. Those obligations and its current grants remain in force.

Move responsibility in four stages:

1. **Observe.** The incumbent continues its work. New services assemble facts and
   compare their results without taking actions.
2. **Route questions.** The incumbent uses the common API and durable question and
   answer records. It answers within its existing delegation or asks the human,
   without depending on another session's terminal picker.
3. **Delegate one responsibility.** Explicitly transfer a narrow action class.
   The incumbent stops independently performing that class, and the focused worker
   uses the shared ownership and target-state checks.
4. **Expand what works.** Transfer further repetitive responsibilities after proof.
   The incumbent continues broader judgment, incidents and human conversation.

There must not be two independent paths executing the same responsibility.
Until handover, the new service can propose actions only. If the legacy path
cannot be constrained, automatic execution for that class remains disabled.
Restarting or replacing a worker must not bypass ownership, evidence or authority
checks at the action target.

The first useful scenario is a plan publishing a durable decision packet, with
its evidence and allowed answerers. The existing coordinator sees it, answers
under its delegation or obtains a human answer, and the supported action proceeds
only while that evidence and authority remain valid. The service records the
observed result. Prove that restart loses no pending decision and that delegating
one responsibility creates neither duplicate effects nor gaps in existing work.

Carry current permissions forward with references to their rulings. Do not paste
the coordinator's entire comment history into every prompt. A broad instruction
to unblock work does not authorize changing caam policy or overriding another
owner's restrictions.

The long-lived conversation can remain a useful human interface. Its existence
while idle is not itself the cost problem; repeated model-driven monitoring,
context replay and routing are. Services should take over those repetitive tasks
without requiring the conversation to remain alive. Retiring the session or
closing its epic requires explicit disposition of its outstanding obligations;
container deployment alone is not that decision.

## What would make this convincing

Use observable scenarios rather than a prescribed multi-week observation period:

- Ask from one tool, stop its worker, answer from another host and tool, and resume
  through the third tool without shared files or terminal input.
- Submit competing answers and replay an old answer after the problem has cleared
  and returned. Only the currently authorized decision may take effect.
- Kill a worker before the action, during it, and after it but before its result is
  saved. Pending work survives and a supported effect is not repeated.
- Leave a question unanswered while unrelated work finishes. Repeated checks of
  unchanged facts make no model calls.
- Lose database or factory access. Report “cannot determine,” not “complete.” A
  command-line client cannot cure a shared database outage either.
- Start without the old journal and reproduce the relevant admission, hold and
  recovery decisions. Keep model-selection evidence queryable.
- Run common scenarios in both deployment modes, then their deployment-specific
  failure tests. Exercise backup restore before resuming mutations.

Wall-clock limits help contain a runaway worker, but do not themselves bound
tokens or money. Model-call, token and spending limits need separate controls.

## Ownership and choices still to settle

The orchestrator owns coordination operations, derived facts and action rules.
`livespec-runtime` owns the shared attention types. This orchestrator owns the
current plan-operation prose; FABle's assumption that it belongs to livespec core
was incorrect. Core changes are needed where shared family contracts change.
The overseer owns supervision integration; the console renders and submits through
public operations; Dolt-server owns database lifecycle; deployment tooling owns
the applicable shared infrastructure.

Remaining engineering questions include the coordination schema and transaction
implementation, which first action
can be made safely repeatable, credential delivery to pods, and reuse of existing
deployment machinery. The research does not justify a fleet-wide switch of GitOps
controller. The API needs authenticated callers and scoped permissions; supplying
a role name is not authority.

Delegated decision-making must be explicit. Existing grants should continue to
work, and changing transport must not grant an agent permission to answer a
human-only question. The new direction already authorizes investigating and
replacing pane-dependent answer routing; asking again whether cross-host answering
is desirable would repeat a settled decision.

## Evidence and further reading

The direction is recorded on plan epic `bd-ib-k6dqwc`: the approved second-pass
ruling of 25 October, scope comment `01a17981-29e0-75da-9e5b-1feecee8bb5c`
for portability, and the correction and coexistence ruling identified by
`maintainer-cross-tenant-dolt-and-coordinator-coexistence-20261027`. The last of
these supersedes the first version of this report on storage. Astra and FABle produced their new reports
on 26 October 2026. They reviewed source documentation and repository code;
neither performed a deployment or live transaction proof. This summary resolves
their differences rather than treating agreement as proof of implementation.

Earlier research:

- [Journal history](002-dispatch-journal-genesis.md) and
  [how work reaches the factory](003-how-work-reaches-the-factory.md).
- [Recorded discussion and directions](004-discussion-transcript-and-maintainer-directions.md).
- [Other factory designs](005-external-dark-factories.md),
  [capacity and control approaches](006-external-how-others-solve-capacity-and-control.md),
  and [human attention](007-external-human-attention.md).
- [The first design draft](008-first-pass-control-plane-design-draft.md) is historical;
  its single-coordinator and storage proposals are superseded where they conflict
  with later rulings.
- [Measured ledger concurrency](../../../.ai/ledger-writers-are-multi-host.md),
  [operation contracts](../../../SPECIFICATION/contracts.md), and
  [plan-operation prose](../../../.claude-plugin/prose/plan.md).

Selected primary sources consulted by the researchers on 26 October 2026:

- [AWS: transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
  explains saving pending delivery with a change and handling duplicate delivery.
- [Dolt branches and transactions](https://docs.dolthub.com/sql-reference/version-control/branches),
  [transaction implementation](https://github.com/dolthub/dolt/blob/main/go/libraries/doltcore/sqle/dsess/transactions.go),
  and [concurrent transaction example](https://www.dolthub.com/blog/2023-12-14-concurrent-transaction-example/)
  informed the concurrency concerns. Some documentation URLs failed; these sources
  do not replace proof against the pinned deployed version.
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/),
  [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/), and
  [client-go leader election](https://pkg.go.dev/k8s.io/client-go/tools/leaderelection)
  explain why scheduling and leader selection do not guarantee a unique effect.
- [Compose service configuration](https://docs.docker.com/reference/compose-file/services/)
  and [the official Docker image](https://hub.docker.com/_/docker) support the host
  deployment discussion and the distinction between service containers and DinD.
- [JetStream publishing](https://docs.nats.io/learn/jetstream/publishing) and
  [delivery](https://docs.nats.io/learn/jetstream/delivery-and-acknowledgment), plus
  [Temporal message passing](https://docs.temporal.io/encyclopedia/workflow-message-passing)
  and [activity execution](https://docs.temporal.io/activity-execution), explain
  the useful guarantees and limits of the deferred alternatives.

No broker, schema, Kubernetes-specific scheduling option or secrets product is
selected solely by this report. The immediate proposal is one useful, recoverable
answer flow with shared meaning across tools and deployment modes.
