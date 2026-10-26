# Livespec coordination across hosts, containers and agent tools

Research summary and proposed direction · 26 October 2026  
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
A unified view can combine them without copying their authority. New shared
storage is justified for records with no adequate owner, such as pending
coordination decisions and unfinished requests to perform an action. Multiple
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

## The main disagreement: where to save new coordination work

Astra recommends a transactional coordination service, with the previously
approved dedicated non-Beads Dolt database as the first candidate. FABle proposes
ledger comments for the initial answer flow, introducing the database later with
fleet scheduling.

FABle is right to reuse existing records, but too optimistic about what a comment
proves. Earlier repository experiments found that concurrent comments survive,
but their read order does not establish commit order; some concurrent metadata
updates lose changes. “Take the first answer” needs a server-enforced rule, not
two workers independently reading a list and deciding they won.

The recommendation is to retain Beads/Fabro authority and prove the storage
guarantees for new coordination before enabling automatic actions. Use the
separate Dolt database if existing public operations cannot provide those
guarantees. Do not postpone durability merely to call the first delivery small,
or build a second database for facts with a reliable existing home.

Dolt is a candidate, not a completed prerequisite. The research found optimistic
transactions and conflict handling, not a basis for assuming PostgreSQL-style
locking. Test the deployed version with concurrent writers, failed transactions,
ambiguous responses and restore. Competing reservations must contend on shared
state; a check followed by unrelated writes is insufficient. Provisioning, grants,
backup and authenticated pod access also remain to be proved.

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
2. Save one kind of plan question and accept an authorized answer through the same
   API from Claude, Codex or pi, including on another host.
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

Remaining engineering questions include storage implementation, which first action
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

The latest direction is recorded on plan epic `bd-ib-k6dqwc`, scope comment
`01a17981-29e0-75da-9e5b-1feecee8bb5c`. Astra and FABle produced their new reports
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
