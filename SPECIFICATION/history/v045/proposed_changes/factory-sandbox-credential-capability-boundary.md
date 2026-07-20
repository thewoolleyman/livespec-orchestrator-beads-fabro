---
topic: factory-sandbox-credential-capability-boundary
author: claude-opus-4-8
created_at: 2026-07-20T19:30:00Z
---

## Proposal: Factory sandbox credential capability boundary

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- ../tests/heading-coverage.json

### Summary

Codify the authorization boundary the maintainer declared 2026-07-20: a
credential projected into the Fabro factory sandbox MUST NOT carry any
capability that lets the unattended agent execute code on the host substrate
or rewrite a gate that validates the factory's own output. GitHub `workflows`
read-write is the first worked instance — it is REJECTED, not deferred — and
the resolution for such work is ROUTING to the attended host session,
performed automatically, never handed back as manual maintainer work.

The constraint is written as a CAPABILITY rule rather than a rule about one
named GitHub grant, so that future grants of the same shape are covered
without a further amendment.

This proposal also repairs the drift the boundary creates. The specification
currently states the OPPOSITE posture in two places and classifies the
forbidden work as dispatchable in a third:

1. `contracts.md` instructs the preflight and adopter docs to surface the
   `workflows` grant as an App-installation REQUIREMENT.
2. `scenarios.md` Scenario 32 asserts that same requirement in Gherkin.
3. `contracts.md`'s `factory_safety` "sharp line" classifies writing CODE as
   factory-safe, which makes a `.github/workflows/` edit factory-safe —
   exactly the dispatch this boundary forbids.

Left unamended, the specification would simultaneously say the sandbox
credential may not push workflow files AND that such items are safe to
dispatch, which is precisely the wasted-run trap the boundary exists to close.

### Proposed Changes

#### 1. New constraint section in `SPECIFICATION/constraints.md`

Insert the following new `## ` section immediately after
`## Codex full-access runtime constraints` and immediately before
`## Process boundaries`, grouping it with the other external-runtime
privilege-posture sections:

```markdown
## Factory sandbox credential constraints

**Scope —** the FACTORY SANDBOX path: any Fabro sandbox executing
agent-written code on the fleet's self-hosted substrate, whether or not
the invocation named an `--item`. The `--item`-presence distinction that
§"Dispatcher loop invocation surface" uses as its proxy for whether a
human is present governs COST verdicts only; it does NOT relax anything
in this section. A hand-picked dispatch runs the same agent-written code
on the same host as a queue drain, so both are bound identically.

- **No self-amending capability.** A credential projected into the factory
  sandbox MUST NOT carry any capability that would let the sandbox execute
  code on the host substrate, or modify any gate that validates the
  factory's own output. This is a rule about CAPABILITY, not about any one
  named grant: a permission qualifies whenever holding it would let an
  agent weaken, disable, or rewrite the implement → janitor → CI → merge
  chain that admits the agent's own work. A grant that is technically
  narrower than the capability it confers is judged by the capability. New
  grants of this shape are governed by this rule as written and do not
  require it to be amended.
- **Coarse grants are judged at the granularity offered.** Where a capability
  is offered only at a coarser granularity than the work requires, the coarser
  capability is what is being granted and this section judges it as such. A
  permission MUST NOT be granted on the basis that the immediate work-item
  would use only a benign part of it.
- **GitHub `workflows` read-write is the worked instance, and it is
  REJECTED, not deferred.** The fleet's check matrix runs on self-hosted
  runners, so a workflow file is executable configuration and write access
  to `.github/workflows/` is arbitrary code execution on the maintainer's
  host — the blast radius is the machine, not the pipeline. Every gate in
  the factory's safety model is DEFINED IN those files, so the capability
  would let an agent disable its own examiner in the same pull request. The
  grant is also all-or-nothing: GitHub offers no per-path or comment-only
  scoping. The factory sandbox's credential MUST NOT hold it.
- **Latitude determines privilege; the two credentials MUST NOT be
  conflated.** The fleet's fan-out credential legitimately DOES hold
  `workflows` read-write, because the fan-out is a narrow, deterministic
  pin-string rewrite. The factory sandbox is an agent with open-ended
  latitude. The asymmetry is correct by design, and neither credential's
  posture may be inferred from the other's.
- **The resolution is ROUTING, not privilege — and never manual work.** Work
  whose scope requires a withheld capability MUST be routed to the attended
  host session, which already holds that capability legitimately and where
  every diff is reviewed. That routing MUST be performed automatically.
  Requiring the maintainer to hand-edit is NOT an acceptable resolution, and
  MUST NOT be specified, implemented, or surfaced as one. The boundary
  relocates which actor publishes; it MUST NOT cost autonomy.
- **Refusal is pre-dispatch, precise, and non-interactive.** Such work MUST
  be refused BEFORE a sandbox run is launched, never discovered at publish
  after the agent has authored and committed the work. The refusal MUST name
  the host-session route. On the unattended path a refusal MUST reach a
  terminal verdict and MUST NOT park on an interactive prompt no operator is
  attached to answer.
- **Refusal predicates MUST be scoped to the capability, not approximated.**
  A predicate MUST key on the narrowest surface that actually requires the
  withheld capability — for the `workflows` instance, the
  `.github/workflows/` path prefix specifically. A broader approximation
  (`.github/`, or a `*.yml` glob) MUST NOT be used: composite actions under
  `.github/actions/` are publishable by the sandbox, so a broader predicate
  would refuse dispatchable work.
- **Withheld capability is a per-item eligibility fact, not a whole-item
  verdict.** An item whose scope only PARTLY requires a withheld capability
  SHOULD be considered for decomposition, so the portion the sandbox can
  publish is not refused along with the portion it cannot.

**Verification.** For each capability withheld under this section, the
governing check is that the factory sandbox's credential does not hold it and
that an item requiring it is refused at admission rather than at publish. A
credential observed holding a withheld capability, or an item observed
reaching a sandbox run despite requiring one, is a violation of this section
regardless of whether the run subsequently succeeded.
```

#### 2. `SPECIFICATION/contracts.md` — §"Self-contained plugin dispatch"

Replace this text, which currently prescribes the rejected posture:

```
Workflow-file-touching pushes structurally require the App's
`workflows` read-write permission grant; the preflight and the adopter
docs MUST surface that grant among the App-installation requirements.
```

with:

```
Workflow-file-touching pushes structurally require the App's
`workflows` read-write permission grant, which the factory sandbox's
credential MUST NOT hold (§"Factory sandbox credential constraints" in
`constraints.md`). The preflight and the adopter docs MUST therefore
surface that grant as one DELIBERATELY WITHHELD from the dispatch
credential, and MUST name the attended-host-session route for work
requiring it — never as an App-installation requirement to be granted.
```

The GitHub mechanic in the first clause is retained because it remains true;
only the prescription drawn from it is replaced.

#### 3. `SPECIFICATION/contracts.md` — §"Work-item beads-issue mapping"

The `factory_safety` enum stays at three reasons. Extend the
`mutates-host-machinery` example list and qualify the sharp line.

Replace:

```
  (changes the live host substrate the factory itself runs on — systemd
  timers, credential wrappers, the plugin cache, Fabro servers), and
```

with:

```
  (changes the live host substrate the factory itself runs on — systemd
  timers, credential wrappers, the plugin cache, Fabro servers, and
  executable CI configuration under `.github/workflows/`, which runs on
  the fleet's self-hosted runners), and
```

Replace:

```
  writing CODE for any of these (including the Dispatcher's own code) is
  factory-safe; APPLYING host state is host-only.
```

with:

```
  writing CODE for any of these (including the Dispatcher's own code) is
  factory-safe; APPLYING host state is host-only. Executable configuration
  that RUNS ON the host substrate is APPLYING host state, not writing code,
  however code-like its file format: editing `.github/workflows/` is
  host-only under this line, because the fleet's runners are self-hosted
  and those files are the factory's own gates.
```

#### 4. `SPECIFICATION/contracts.md` — §"Dispatcher admission, WIP cap, and post-merge acceptance"

Replace:

```
  runnability is intrinsic, not a transient external block); it is surfaced
  for host routing via the needs-attention awareness surface for a host
  actor to run. The Dispatcher MUST NOT retry it into a sandbox.
```

with:

```
  runnability is intrinsic, not a transient external block); it is surfaced
  for host routing via the needs-attention awareness surface for a host
  actor to run. That host actor is an attended host SESSION performing the
  work automatically, not the maintainer performing it by hand; a refusal
  MUST NOT be surfaced in a form that presents hand-editing as the intended
  resolution. The Dispatcher MUST NOT retry it into a sandbox.
```

#### 5. `SPECIFICATION/scenarios.md` — Scenario 32

Replace this step, the executable twin of change 2:

```
  And the diagnostic surfaces the App workflows read-write grant among the App-installation requirements
```

with:

```
  And the diagnostic surfaces the App workflows read-write grant as deliberately withheld from the dispatch credential, naming the attended-host-session route
```

#### 6. `SPECIFICATION/scenarios.md` — Scenario 48

Append a sibling scenario inside Scenario 48's existing `gherkin` block,
after the `needs-host-secrets` scenario, and amend that block's `Feature:`
line to carry the attended/automated qualifier.

Replace:

```
Feature: A ready work-item whose `factory_safety` is non-null is refused at
  the admission valve before any sandbox launch and surfaced for host routing.
```

with:

```
Feature: A ready work-item whose `factory_safety` is non-null is refused at
  the admission valve before any sandbox launch and surfaced for routing to
  an attended host session that performs it automatically.
```

Append after the final step of the existing scenario, separated from it by one
blank line and still inside the same `gherkin` fence:

```
  Scenario: A ready item editing .github/workflows/ is refused pre-dispatch
    Given a `ready` work-item whose scope edits a file under `.github/workflows/`
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then the item is not admitted to `active`
    And no Fabro sandbox run is launched for it
    And the refusal names the attended-host-session route
    And the refusal reaches a terminal verdict without an interactive prompt
    And the item stays `ready` (it is not marked `blocked`)

  Scenario: A ready item editing .github/actions/ is NOT refused
    Given a `ready` work-item whose scope edits a composite action under
      `.github/actions/` and no file under `.github/workflows/`
    And a free WIP slot, cleared dependencies, and a resolvable assignee
    When the Dispatcher's admission valve evaluates it
    Then the item is admitted to `active`
```

The second scenario is the negative case that pins the predicate's precision:
it fails if an implementation approximates the boundary as `.github/` or a
`*.yml` glob.

#### 7. `tests/heading-coverage.json`

Change 1 adds one `## ` heading, so the revise payload MUST carry a matching
entry in the same `resulting_files[]` write, spelled `../tests/heading-coverage.json`:

```json
{
  "heading": "## Factory sandbox credential constraints",
  "spec_root": "SPECIFICATION",
  "spec_file": "constraints.md",
  "test": "TODO",
  "reason": "Baseline heading-coverage backfill for the beads substrate (Phase E). The shared heading_coverage check is satisfied by enumerating every SPECIFICATION/ H2 heading; real test IDs are populated as the governed propose-change/revise loop's resulting_files[] mechanism binds each heading to an exercising test."
}
```

No other heading is added, renamed, or removed by this proposal.

### Motivation

**The boundary is a design decision, not a defect.** It was reached after a
factory-dispatched item failed twice at publish and the alternative — granting
the sandbox the missing permission — was considered and REJECTED. Recording it
only as a work-item comment leaves it as tribal knowledge, and the specific
failure mode is that the next reader encounters the *existing* contract text
first, which instructs them to grant exactly the permission that was refused.
The documentation debt was noted on the originating record as owed.

**Why a capability rule rather than a `workflows` rule.** The reasoning that
rejected the grant does not depend on anything specific to GitHub Actions: it
turns on the substrate being self-hosted, on the gates being defined in the
artifacts the capability would govern, and on the grant being coarser than the
need. Any future capability with those three properties should be refused by
the same argument, and a specification that named only `workflows` would have
to be amended each time to say so. Writing the rule at the capability level
also removes the recurring judgment call about whether a newly-offered grant
is "like" the one already refused.

**Why the drift repair is not separable.** `contracts.md`'s current sentence
and Scenario 32's current step do not merely omit the boundary — they instruct
the reader and the test suite toward the opposite posture. The `factory_safety`
sharp line is worse than an omission: it actively classifies workflow-editing
work as factory-safe, so an item can pass grooming, be admitted, burn a full
implement cycle, author and commit correct work, and only then be rejected at
push. That sequence has been observed. Filing the constraint while leaving the
classification intact would leave the specification self-contradictory on the
exact question the constraint answers.

**Why `mutates-host-machinery` rather than a fourth enum reason.** The
rejection's own leading argument is that write access to `.github/workflows/`
is code execution on the maintainer's host. `mutates-host-machinery` is already
defined as work that "changes the live host substrate the factory itself runs
on". These are the same claim, so the existing reason covers the case on its
plain meaning, and the admission valve's refusal-and-host-route path already
does the right thing for any non-null `factory_safety`. Adding a fourth member
to a deliberately closed enum would expand the label vocabulary every consumer
must know, in exchange for a distinction the existing reason already draws.

**Why the negative scenario matters.** Two items in the same repository, in
adjacent directories, land on opposite sides of this line: a composite action
under `.github/actions/` was published by the sandbox through a merged pull
request, while a sibling editing three `.github/workflows/` files was rejected
twice on the same credential. A predicate approximated as `.github/` or `*.yml`
would refuse the first, which is dispatchable work. Scenario 48's negative case
pins that precision so the approximation cannot be introduced silently.

**Why routing must be automatic.** The boundary is only acceptable because it
costs no autonomy. The same day the grant was refused, the blocked item was
performed from an attended host session in a single pass and merged green, with
no manual maintainer step. A specification that permitted "route it to the
maintainer" as the resolution would convert a credential-scoping decision into
recurring human labor, which was explicitly ruled out.
