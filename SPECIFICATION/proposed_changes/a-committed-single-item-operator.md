---
topic: a-committed-single-item-operator
author: claude-opus-5-5
created_at: 2026-11-13T02:18:40Z
---

## Proposal: A committed single-item operator override launches one named item outside the repository WIP gate, on the dispatch target's build, under every hold and the shared fleet cap

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Provisional fleet launch scripts" commits two launchers: `dispatch-dual.sh` (impl) and `resume-capped.sh` (resume). Both take a per-factory FIFO ticket, and the impl launcher yields at the repository WIP gate. Operators also need a third kind of launch: one named work item, driven through the Dispatcher's hand-picked operator path `dispatch --item`. That path admits the item without enforcing `wip_cap` (§"Per-repo WIP cap", the 2026-07-30 ruling). No committed launcher does this, so each operator seat writes its own. This proposal makes three changes:

- **Single-item operator override.** A new committed launcher, `fleet-launch/override-item.sh`, launches exactly one named work item through `dispatcher.py dispatch --repo <target> --item <work-item-id>`. The rules it does not apply are a closed list: the FIFO order, the repository WIP gate, the in-flight addition, the breakage exception, and the five rules that act on a FIFO ticket. It applies every other rule of the section exactly as an impl launcher does. It honours four holds: the gmktec factory hold (released by the freeze allowlist), the canary repository hold (released by the canary exemption list), the repository hold, and the per-item hold §"Dispatcher policy settings" already defines (status `blocked` with its recorded reason). It waits for a free shared fleet slot. It writes a fleet in-flight marker that every launcher counts until the run lists, and it removes that marker on every exit. It never reads the default branch's CI itself. It never routes around the Dispatcher's master-CI preflight, the shared fleet and per-factory caps, the pre-dispatch wall's exit-`5` refusal of a spec-change-tier item, the pre-dispatch Definition-of-Done judgement, or the canary-sample verdict record.
- **Build of the dispatch target.** Every committed launcher runs the orchestrator build registered for its dispatch target repository, resolved through the registered-plugin-root command §"Self-contained plugin dispatch" requires, for the target's checkout. It never runs the build of this repository's own checkout. `dispatch-dual.sh` and `resume-capped.sh` already resolve the build this way (they pass `"$REPO"`). The section has never stated the rule, so the change codifies it for all three launchers.
- **An empty board is a count of zero.** A board read that succeeds and lists no non-terminal run counts as 0 live runs, so the shared fleet count over empty boards is just the live in-flight markers. Only a failed read, or one that returns something other than a board listing, is unreadable and holds. The committed board reader already behaves this way (`board_parse_rows` in `fleet-launch/board-snapshot.sh`: "An empty board exits 0 with nothing on stdout ... a reading of zero, not an unreadable board"). The section does not yet state it.

The seat rule at the end of the section gains the override as the third committed path. A seat that launches one named item outside the WIP gate must use it and must not use a local copy.

### Motivation

Work item bd-ib-fc6da3, approved by legacy-coordinator-agent. Its Definition of Done asserts that the committed override:

1. launches exactly one named item through `dispatch --item` outside the WIP gate;
2. runs the build registered for the dispatch TARGET repository;
3. holds while the gmktec hold file exists, unless the freeze allowlist names the item;
4. holds while a canary repository hold for the target exists, unless the canary exemption file names the item, and while a repository hold or an item hold names it;
5. waits for a free shared-fleet slot and writes an in-flight marker that is counted until the run lists;
6. on an empty board, reads the count as zero plus its live in-flight markers, and launches instead of waiting as it would on an unreadable board.

Two measured incidents, both caused by the dispatcher seat's uncommitted override (seat 59a085b4):

- **Wrong build, 2026-11-13 ~00:45Z.** The override was dispatching a livespec-dev-tooling item for the #5100 canary. It resolved its build from the registry entry of the ORCHESTRATOR checkout, `7477c7d58beb` (v0.323.1). The dev-tooling clone had adopted v0.325.0 for the canary. Left unfixed, the canary would have run on the build it was meant to replace. The seat patched the override to read the dispatch target's registration before the launch.
- **Stalled on an empty board, 2026-11-13 ~01:5xZ.** The same override's fleet read returned nothing when the board listed no run (`[ -n "$rows" ] || return`). Its wait loop read that as unreadable. With zero live runs, two canary overrides waited about 6 minutes for a slot that already existed. The seat patched that too.

Neither patch is visible to grading, and neither binds the next seat. The section's seat rule already requires every seat to launch through a committed launcher and never a local copy ("A gate the seat needs that the committed launchers lack MUST land in them through this repository's change path before the seat relies on it"). The override is such a gate path. Today it exists only as local copies.

The bypass has a sanctioned source. §"Per-repo WIP cap" states that `dispatch --item` "is a sanctioned override that admits a single named work-item WITHOUT enforcing `wip_cap`", and a surface asserting cap conformance must scope its assertion to the enforcing paths. The launcher-side WIP gate is only an early yield for that same cap, so skipping it for the override is consistent. Nothing else in the section is a WIP bound, so nothing else is skipped.

Design choices, stated for the grade:
- **Bypass is a closed, normative list.** The override MUST NOT apply nine named rules. Four are the WIP and order rules: the FIFO order, the repository WIP gate, the in-flight addition and the breakage exception. Five act on a FIFO ticket the override never holds: the yielding-ticket marker, the held-queue-head skip, the dead-pid stall, the early-exit re-ticket and the priority-1 release. It MUST apply every other rule of the section by the impl launcher's rules, including the host-only screen, the origin-tip checkout, the launch-time Definition-of-Done preflight, the factory-class pressure gate, the credential wrapper, the ACP overrides and the canary-sample verdict record.
- **The Dispatcher's admission conditions are untouched.** The override never reads default-branch CI (§"A caller does not gate a dispatch on the default branch's CI"). `dispatch --item` runs the master-CI preflight, as it does on every dispatch entry path. The pre-dispatch wall still refuses a spec-change-tier item awaiting ratification with exit `5`. The override treats that as a `refused` non-run exit and never retries it through another verb.
- **Caps are not bypassed under any name.** The override must wait under the shared fleet cap, its target factory's per-factory cap and the binding re-count under that factory's launch mutex, as an impl launcher does. The bullet also binds it to every cap or bound the section later applies to an impl launcher's launch. That includes #5101's per-server limit and committed fleet cap bound, if they are ratified.
- **The marker counts for the whole master-CI wait.** The override never marks its marker waiting under #5088's rule. A single expedited item holding its slot through a master-CI wait costs at most one slot. In exchange, the override needs no pass-line re-bind and no `FLEET_LAUNCH_MASTER_CI_WAIT_MAX` accounting, and it can never overshoot a cap at a pass line.
- **The gmktec hold is released only by the freeze allowlist.** Definition of Done assertion 3 names the allowlist alone. The priority-1 release of the "gmktec factory hold." bullet does not apply to the override, because the override is already the operator's expedite. The allowlist line is consumed once at the launch under the freeze-allowlist lock, so a second override of the same item is held, as for any launcher.
- **The item hold is the ratified per-item hold, not a new mechanism.** §"Dispatcher policy settings" already defines the per-item hold: status `blocked` with its reason recorded on the item. The idle-slot audit reads no other operator hold. A launcher-only hold file would be a second per-item hold mechanism that only this launcher honours, so the override reads the item's ledger status instead. It reads that status at every hold check and again under the mutex. The seat-local `hold-item-<work-item-id>` files are interim notes and are not specified here.
- **No retry.** The override takes no ticket, so it cannot re-ticket. A `dispatch --item` that exits non-zero before its run lists ends the override, with a terminal line and, while the item still reads `ready`, the one ledger comment "Ready item never silently dropped" requires. The operator decides whether to run it again.
- **The build rule covers every committed launcher.** It codifies what `dispatch-dual.sh` and `resume-capped.sh` already do, so the override cannot be the only launcher bound by it.

In-flight survey, 2026-11-13 ~02:15Z. Scope: the in-tree proposals on origin/master under `SPECIFICATION/proposed_changes/`, the 29 remote `spec/*` branches, and the open PRs touching `SPECIFICATION/` or `fleet-launch/`. These touch §"Provisional fleet launch scripts" or Scenario 307:
- each-gmktec-fabro-server-s-2 (bd-ib-rtzhfc, #5101, in-tree): per-server limits from `max_concurrent_runs`, a runtime fleet cap bounded by the committed `fleet-launch-cap`, a committed-cap count that still counts markers the shared fleet count skips, and fail-closed handling of unreadable values. It also rewrites Scenario 307's candidate scenario. Its bullets bind "an impl launcher or a resume launcher". This proposal's override bullet binds the override to "every cap, limit or bound this section applies to an impl launcher's launch", so once both ratify, the override waits under the per-server limit and the committed fleet cap bound like any impl launch. The override's marker is never skipped, so the committed-cap count includes it under either rule. This proposal adds its scenarios under a new heading and does not edit Scenario 307's block, so it never collides with #5101's change 6. It does not depend on #5101's livespec-dev-tooling prerequisite (change 9). Relation: `align`, in either revise order.
- each-gmktec-fabro-server-s (bd-ib-rtzhfc, in-tree, the WIP-cap half): changes what counts against `wip_cap` in §"Per-repo WIP cap". The override bypasses the launcher-side WIP gate, and `dispatch --item` does not enforce `wip_cap`, so nothing here reads that count. Relation: `align`.
- a-fleet-launcher-holds-its (bd-ib-4vwaty, #5088, in-tree): impl and resume markers marked `master-ci-wait=1` during the Dispatcher's master-CI wait, skipped from the shared fleet count up to `FLEET_LAUNCH_MASTER_CI_WAIT_MAX`. The override never writes that line, so its marker counts for the whole wait and never enters the skipped set or its ceiling. The override never reads the wait or pass lines either. Relation: `align`.
- a-fleet-launcher-honours-a (bd-ib-aibd3u, in-tree): adds `exempt:` lines to a repository hold file. The override applies "every per-item exemption the file carries under any rule of this section", so an `exempt:` line releases it once that proposal is ratified. Relation: `align`.
- the-launcher-holds-one-wip-number (bd-ib-5k2yq2, in-tree): rewrites **Breakage exception.** to order a listed ticket ahead on the FIFO, and adds **Capacity-deferred return.** for a `drive` reporting `capacity-deferred`. The override takes no ticket and runs no `drive`, and `dispatch --item` does not defer on the cap, so neither bullet reaches it. Relation: `align`.
- fleet-launchers-log-and-retry (bd-ib-7itf42, PR #5073): non-run exit rules (failed status read, comment only while `ready`, TERM bound). The override's non-run exits inherit them through "the non-run exit rules of this section". Relation: `align`.
- concurrent-git-fetches-into-one (bd-ib-zyu2ug, PR #5072): one fetch lock per checkout. The override's origin-tip refresh is the impl launcher's and takes the same lock. Relation: `align`.
- Implementation drafts PR #4822 (bd-ib-3ufx6l), #4218 (bd-ib-nmuyjc.6) and #3788 (bd-ib-nz4av6): launcher code and harness cases only, with no specification text. The override lands on what they leave. Relation: `align`.
No in-flight item is superseded or in conflict.

### Proposed Changes

All edits are in `contracts.md` §"Provisional fleet launch scripts" and in one new scenario appended to `scenarios.md`. Scenario 307's text is not edited. No H2 heading in `contracts.md` is added, renamed or removed.

**1. Caller-side framing (`contracts.md`, the section's first paragraph and the gate list's lead sentence).** In the section's first paragraph, replace "it decides only WHEN a caller invokes `drive --action impl:<item>` or `resume --item <item>`," with:

> it decides only WHEN a caller invokes `drive --action impl:<item>`, `resume --item <item>` or, for the single-item operator override defined below, `dispatch --item <item>`,

In the sentence that begins the caller-side gate list ("The committed `fleet-launch/` launchers MUST also enforce the following caller-side gates. Each is a gate on WHEN a launcher invokes `drive --action impl:<item>` or `resume --item <item>`;"), replace "`drive --action impl:<item>` or `resume --item <item>`;" with:

> `drive --action impl:<item>`, `resume --item <item>` or, for the single-item operator override, `dispatch --item <item>`;

**2. Build of the dispatch target (`contracts.md`).** Immediately after the bullet beginning "**Tenant credential wrapper.**", add:

> - **Build of the dispatch target.** A launcher's *dispatch target repository* is the repository whose work item it launches, the one its `drive`, `resume` or `dispatch` runs against through `--repo`. Every committed `fleet-launch/` launcher MUST run the orchestrator build registered for its dispatch target repository. It MUST resolve that build through the command §"Self-contained plugin dispatch" requires, the one that prints the plugin root of a governed project's registered install, run for the dispatch target repository's checkout. It MUST resolve the build for every launch, and MUST run every Dispatcher, `drive`, `resume`, ledger and host-only command of that launch from the plugin root that command prints. It MUST NOT resolve the build by any other lookup. It MUST NOT take the build from the registration of the checkout of this repository it runs from, from the build its own session runs, or from a version pinned anywhere else. A launcher for which that command exits non-zero MUST launch nothing for that launch, and MUST NOT fall back to any other build. A clone adopts a build for a canary on its own, so the target's registration is the only build that reflects what the target has adopted.

**3. An empty board is a count of zero (`contracts.md`).** Append to the end of the bullet list that begins "The committed `fleet-launch/` launchers MUST also enforce the following caller-side gates", after its last bullet, whichever bullet that is when this proposal is revised (today "**gmktec target and candidate cap.**"; after #5101, its "**Committed fleet cap bound.**"):

> - **An empty board is a count of zero.** A factory board read whose command exits zero and that lists no non-terminal run, either with no output or with a listing header and no non-terminal run row, MUST be read as a live run count of 0 for that board. A shared fleet count over boards that all read empty is then the number of live fleet in-flight markers it counts. The launcher MUST compare that number against the shared fleet cap as it compares any other count. A board read is unreadable only when its command fails or times out, or when its output is not a board listing. Only an unreadable read MUST be treated as at the cap, under this section's rule for a count that cannot be read. A launcher, the single-item operator override included, MUST NOT treat an empty board as unreadable.

**4. The single-item operator override (`contracts.md`).** Immediately after the bullet added by change 3, add:

> - **Single-item operator override.** The committed launcher `fleet-launch/override-item.sh` is the *single-item operator override*. It takes one work-item id and its dispatch target repository. It launches that one item through the Dispatcher's hand-picked operator path, `dispatcher.py dispatch --repo <target> --item <work-item-id>`, which admits the named item without enforcing `wip_cap` (§"Per-repo WIP cap"). It MUST launch no other work item and MUST NOT invoke `drive`, `loop` or a drain. It MUST NOT start a second `dispatch --item` while one it started is live. It MAY start another one only after a dispatch it started was stopped before admission under "Holds re-read until admission".
>
>   *What it bypasses.* The override takes no per-factory FIFO ticket and holds no queue position, so it binds ahead of every queued ticket. The override MUST NOT apply exactly these rules of this section, and no others:
>   - the per-factory FIFO order;
>   - "Repository WIP gate.";
>   - the in-flight addition of "Shared WIP claim-count cache.";
>   - "Breakage exception.";
>   - "Yielding ticket marked and skipped.";
>   - "Held queue head skipped.";
>   - "Dead-pid ticket is a stall.";
>   - "Early-exit re-ticket.";
>   - "Priority-1 release.".
>
>   *What it never bypasses.* The override MUST apply every other rule of this section. In particular it MUST pass every caller-side gate this section requires of an impl launcher, by the impl launcher's rules:
>   - the tenant credential wrapper and the build of the dispatch target;
>   - the Dispatcher's ready set, with its bounded retry;
>   - the host-only screen;
>   - the checkout at the origin tip;
>   - the launch-time Definition-of-Done preflight, run once before it takes the mutex, where a failure ends the override without a launch;
>   - the factory-class pressure gate, where a launcher gates on it;
>   - the shared fleet cap, the per-factory cap and the binding re-count;
>   - the configured ACP overrides and judge-model environment;
>   - the canary-sample verdict record: when its launch is a canary sample, its verdict file names the full `gitCommitSha` of the canary clone's install record, as §"Self-contained plugin dispatch" requires of the launching launcher.
>
>   Its *target factory* is the factory instance an impl launcher for the same item selects under this section, including the effect of the gmktec target setting. Every cap, limit or bound this section applies to an impl launcher's launch binds the override's launch too, under whatever name the section gives it. The override MUST NOT read, enforce or stand in for any of the three admission conditions §"A caller does not gate a dispatch on the default branch's CI" reserves to the Dispatcher. It MUST NOT read the default branch's CI state itself. It leaves the master-CI preflight to `dispatch --item`, which runs that preflight as on every dispatch entry path. The pre-dispatch wall still refuses a spec-change-tier item whose linked topic awaits ratification, with exit code `5`, and still applies the pre-dispatch Definition-of-Done judgement. The override MUST NOT retry either refusal or route the item through any other verb.
>
>   *Holds.* While any of the following holds its launch, the override MUST launch nothing, and MUST NOT take the target factory's launch mutex or write a fleet in-flight marker. It MUST log one line naming the hold it read: for a hold file, the file and the first line of its contents; for the item hold, the status `blocked` and its recorded reason. It MUST wait and read the holds again on its next poll.
>   - The gmktec factory hold file, for a launch onto a gmktec factory instance, unless the freeze allowlist names the item. The override reads the allowlist at every hold check. It consumes the item's allowlist line at the launch, under the freeze-allowlist lock, exactly as "One-shot allowlist release" requires. The priority-1 release does not apply to the override.
>   - The canary repository hold file of its dispatch target repository, unless the canary exemption list names the item. The override reads the exemption list at every hold check, and an absent or unreadable list exempts no item.
>   - The repository hold file of its dispatch target repository. The override applies it by the "Hold scope by launch kind" rules, with its own launch read as kind `dispatch`. Every per-item exemption the file carries under any rule of this section releases it.
>   - The *item hold*: the per-item hold of §"Dispatcher policy settings", the item's ledger status `blocked` with its recorded reason. The override MUST read the item's status at every hold check, under the dispatch target repository's credential wrapper, and a status it cannot read holds it. The item hold carries no exemption and no `kinds:` scope.
>
>   The override MUST read all four again under the target factory's launch mutex, immediately before it invokes `dispatch --item`, as "Holds re-read at the launch point" requires. It MUST keep reading them until admission, by the rules "Holds re-read until admission" applies to an impl launcher's drive. An override that stops its dispatch under that rule keeps no ticket. It MUST release its fleet in-flight marker and return to waiting on its holds.
>
>   *Fleet slot and marker.* The override MUST wait until the shared fleet count is below the shared fleet cap and its target factory's count is below that factory's cap, each read as an impl launcher reads it. Then it takes the target factory's launch mutex and writes a fleet in-flight marker. It re-counts with that marker included, and proceeds only while each count is at or below its cap, as an impl launcher's binding count does. Otherwise it MUST remove its marker, release the mutex and wait. It MUST release the mutex before `dispatch --item` starts. The marker MUST name the work item, the target factory and the pid of a process that stays alive until the dispatch exits. Every launcher's shared fleet count MUST count the marker until the item's run lists on its factory board. The override MUST remove the marker when the run lists, and on every exit of the override, a signal exit included. The override MUST NOT mark its marker under any rule of this section that skips a marker from the shared fleet count, so the marker counts for the whole of the Dispatcher's master-CI wait. A count that cannot be read holds the override, and an empty board reads as zero as "An empty board is a count of zero." requires. The wait is bounded by `FLEET_LAUNCH_MAX_WAIT_S` and ends with a `max-wait` terminal line, as for an impl launcher.
>
>   *Exits.* The non-run exit rules of this section apply to the override, with `none` as its ticket number. It re-takes no ticket, so on every non-run exit while its item still reads `ready` it MUST append the one ledger comment that "Ready item never silently dropped" prescribes. A `dispatch --item` that exits non-zero before its run lists MUST end the override without a retry, with a terminal line whose cause names the exit code. An exit code `5` is a `refused` exit: its terminal line and its comment name the refusal line the Dispatcher wrote, as for a drive. When the registry names no build for its dispatch target repository, the override MUST make a non-run exit with the cause `build-unresolved`.
>
>   The override is a caller-side launch under this section's first paragraph. It changes no admission condition the Dispatcher owns. Its over-cap admission is the sanctioned override of §"Per-repo WIP cap" and MUST NOT be reported as a cap violation.

**5. The seat rule (`contracts.md`, the paragraph beginning "Until the deletion the next paragraph requires").** Replace "(impl through `dispatch-dual.sh`, resume through `resume-capped.sh`)" with:

> (impl through `dispatch-dual.sh`, resume through `resume-capped.sh`, and one named item outside the repository WIP gate through `override-item.sh`)

and, after the sentence ending "for any launch.", add:

> A seat that launches one named work item outside the repository WIP gate MUST do so through `override-item.sh`, and MUST NOT run any other script, copy or hand-typed command that invokes `dispatch --item` for that launch.

**6. Harness cases (`contracts.md`).** Immediately after the paragraph beginning "The `check-fleet-launch` harness cases MUST also cover holds re-read until admission:", add:

> The `check-fleet-launch` harness cases MUST also cover the build of the dispatch target, the empty board and the single-item operator override, against a stub plugin registry, a stub Dispatcher that records its argv and the build directory it ran from, a stub ledger, stub factory boards, and throwaway queue, lock, in-flight and state directories:
>
> - a stub registry with one entry whose `projectPath` is this repository's checkout and another, at a different build, whose `projectPath` is a stub target's checkout. An impl launcher, a resume launcher and the override for that target each run from the plugin root the registered-plugin-root command prints for the target's checkout, and never from the other build.
> - the same registry with no entry for the stub target, so that command exits non-zero: the override launches nothing and leaves a `build-unresolved` terminal line.
> - a stub `fabro ps` that exits 0 with no output on every board, and one that lists only terminal runs, with one live fleet in-flight marker and a shared fleet cap of 2: an impl launcher and the override each read a shared fleet count of 1 and launch. A stub `fabro ps` that fails holds both as at the cap.
> - an override for an item of a stub target whose counted-claims count equals its `wip_cap`, while an impl launcher for that target yields at the WIP gate with the oldest FIFO ticket. The stub Dispatcher receives exactly one `dispatch --repo <target> --item <work-item-id>`. The override writes no ticket file. The queued launcher keeps its ticket number and its place.
> - the gmktec factory hold file present: an override whose item the freeze allowlist does not name is held, a priority-1 item included. Once the allowlist names it, it launches, and the allowlist no longer names it.
> - the target's canary repository hold file present: the override is held until the canary exemption list names its item, and then launches.
> - the target's repository hold file present with no `kinds:` line: it holds the override. A repository hold file carrying `kinds: resume` does not.
> - the stub ledger reading the item's status as `blocked` with a recorded reason, and a stub ledger read that fails: each holds the override. A file named `hold-item-<work-item-id>` does not hold it.
> - every hold above: the override's yield line names the hold, and while held the override takes no launch mutex and writes no fleet in-flight marker.
> - a hold file created, or the item's status turned `blocked`, while the override holds the target factory's launch mutex: the override releases the mutex and its marker and launches nothing.
> - the override sent TERM while it waits on the stub dispatch before the run lists: its fleet in-flight marker is removed.
> - a canary-sample launch: the override's verdict file names the full `gitCommitSha` of the stub canary clone's install record.
> - the shared fleet count equal to the shared fleet cap: the override waits and writes no marker. Once the count drops below the cap, it writes its marker under the mutex and starts `dispatch --item`. Another launcher's shared fleet count includes that marker until the stub run lists. The marker is removed after the run lists.
> - a stub dispatch that prints master-CI wait lines: the override's marker carries no `master-ci-wait=1` line, and stays in every launcher's shared fleet count.
> - a stub CI reader that records every read: the override makes none.
> - a stub dispatch that exits `5`: the override does not retry, and leaves a `refused` terminal line and one ledger comment naming the refusal line. A stub dispatch that exits `1` before listing: the override does not retry, and leaves a terminal line naming exit code `1` and one ledger comment.
>
> The scenario "A single-item operator override launches one named item outside the WIP gate, on the dispatch target's build, under every hold and the shared fleet cap" in `scenarios.md` exercises these cases.

**7. Scenario (`scenarios.md`).** Append the scenario below. It carries no number; the revise pass assigns one.

## Scenario: A single-item operator override launches one named item outside the WIP gate, on the dispatch target's build, under every hold and the shared fleet cap

Governing clause: `contracts.md` §"Provisional fleet launch scripts".

```gherkin
Feature: The committed single-item operator override
  Background:
    Given fleet-launch/config.sh values overridden to a stub plugin registry, a stub Dispatcher that records its argv and the build directory it ran from, a stub ledger, stub factory boards, and throwaway queue, lock, in-flight and state directories
    And a stub target repository A whose checkout the stub registry names as the projectPath of an entry at build 0.325.0
    And this repository's checkout named by another entry at build 0.323.1
    And no hold file exists unless a step creates it

  Scenario: The override launches exactly one named item through dispatch --item outside the WIP gate
    Given repository A's counted-claims count equals its configured wip_cap
    And an impl launcher for repository A holds the oldest FIFO ticket on the target factory and yields at the repository WIP gate
    And the shared fleet count is below the shared fleet cap
    When the operator runs the single-item operator override for work item bd-o of repository A
    Then the stub Dispatcher receives exactly one dispatch --repo A --item bd-o
    And the override writes no FIFO ticket
    And the queued impl launcher keeps its ticket number and its place
    And the override makes no read of the default branch's CI

  Scenario: The override runs the build registered for the dispatch target repository
    When the override launches work item bd-o of repository A
    Then dispatch --item runs from the 0.325.0 build's cache directory
    And no command of that launch runs from the 0.323.1 build
    When the stub registry carries no entry whose projectPath is repository A's checkout
    Then the override launches nothing
    And it leaves a build-unresolved terminal line

  Scenario: The gmktec factory hold holds the override unless the freeze allowlist names its item
    Given the override's target factory is a gmktec factory instance
    And the gmktec factory hold file exists
    And the freeze allowlist does not name bd-o
    When the override for bd-o runs
    Then it launches nothing
    And it logs a line naming the gmktec factory hold file
    When the freeze allowlist names bd-o
    Then the override launches bd-o
    And the freeze allowlist no longer names bd-o

  Scenario: The canary, repository and item holds each hold the override
    Given the canary repository hold file for repository A exists
    And the canary exemption list does not name bd-o
    When the override for bd-o runs
    Then it launches nothing
    When the canary exemption list names bd-o
    And the repository hold file for repository A exists with no kinds: line
    Then the override still launches nothing
    When the repository hold file for repository A is removed
    And the stub ledger reads bd-o's status as blocked with a recorded reason
    Then the override still launches nothing
    And it takes no launch mutex and writes no fleet in-flight marker
    When the stub ledger reads bd-o's status as ready
    Then the override launches bd-o

  Scenario: The override removes its marker on every exit
    Given the override for bd-o has written its fleet in-flight marker and invoked dispatch --item
    When the override is sent TERM before bd-o's run lists
    Then its fleet in-flight marker is removed

  Scenario: The override waits for a free shared fleet slot and its marker is counted until the run lists
    Given the shared fleet count equals the shared fleet cap
    When the override for bd-o runs
    Then it waits and writes no fleet in-flight marker
    When one run leaves the stub boards
    Then the override writes a fleet in-flight marker naming bd-o under the target factory's launch mutex
    And it invokes dispatch --item for bd-o after releasing that mutex
    And another launcher's shared fleet count includes that marker until bd-o's run lists on its factory board
    And the override removes the marker once the run lists

  Scenario: An empty board reads as zero plus the live in-flight markers, not as unreadable
    Given every stub factory board lists no non-terminal run, its stub fabro ps exiting 0 with no output
    And one live fleet in-flight marker of another launch
    And a shared fleet cap of 2
    When the override for bd-o reads the shared fleet count
    Then it reads 1
    And it launches bd-o without waiting
    When a stub fabro ps instead exits non-zero
    Then the override holds as at the cap
```

**8. Unchanged.** Scenario 307's text and its gherkin block are unchanged. So are the impl and resume launchers' existing gates, the "gmktec factory hold." bullet with its priority-1 release for `dispatch-dual.sh` and `resume-capped.sh`, and §"Per-repo WIP cap". This proposal adds no hold file: the override's item hold is the ratified per-item hold of §"Dispatcher policy settings".

**9. Revise co-edit.** The revise pass that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new scenario heading in the same revise commit. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit. It carries `test: "TODO"`, `work_item: "bd-ib-fc6da3"`, and a non-empty `reason` naming the tier the owed test runs at: integration, as `check-fleet-launch` harness cases over a stub registry, a stub Dispatcher and stub boards. The same commit adds one matching `tests/heading-coverage-debt.json` entry carrying `spec_root`, `spec_file`, `heading`, `work_item: "bd-ib-fc6da3"` and `first_seen` set to the revise date. No `contracts.md` H2 heading changes, so no other row is owed.
