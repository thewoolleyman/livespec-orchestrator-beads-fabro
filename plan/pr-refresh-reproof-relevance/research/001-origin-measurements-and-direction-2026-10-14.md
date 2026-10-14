## The maintainer's statement of what done means

Open a work item to address the re-proof loops. If the changes were not likely to be relevant or cause a difference in the definition of done, no need to re-run proof. Make a plan for this and start it working and monitor it, it's another throughput high priority fix.

## Definition of Done assertions derived from that statement

- On hp's fleet Fabro server, a factory run whose pr_refresh rebase brings in only default-branch commits that cannot affect what the item's Definition of Done assertions observe proceeds from pr_refresh to pr and publishes without re-running proof_capture, review and proof_verify.
- On hp's fleet Fabro server, a factory run whose pr_refresh rebase brings in a commit that can affect what the item's Definition of Done assertions observe, or whose relevance the rule cannot decide, re-runs proof_capture, review and proof_verify for the new head before publication.
- Every pr_refresh that changes the publish head leaves a record on the pull request stating whether the verified proof was carried forward or re-run, naming the verified head, the new head, the incoming commit range and the rule inputs that decided it, so a reviewer can audit the decision.
- Over a 7-day window on hp's fleet Fabro server after the fix is released, no run spends a proof_capture, review and proof_verify lap after a pr_refresh whose incoming commits the released rule classifies as unable to affect the item's Definition of Done, and the window's re-proof minutes are reported against the 64.1-minute, five-lap baseline of 2026-10-11 to 2026-10-14.

# pr-refresh-reproof-relevance — origin, measurements and direction

Opened 2026-10-14 for the livespec fleet maintainer, who asked for this plan on
2026-10-14 and called it a high-priority factory-throughput fix. The statement
above is theirs, verbatim. The four assertions were derived by the creating
session and are recorded as session-derived in the first handoff entry. A
separate session drives the plan.

## The problem

Every head change at `pr_refresh` sends the run back through `proof_capture`,
`review` and `proof_verify`, even when the commits that moved master cannot
change anything the item's Definition of Done assertions observe. That rule is
ratified: `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch",
sub-section "Definition-of-Done and Proof-of-Done stages", paragraph
"Scripted publication and proof-head integrity" says: "A changed head MUST
return to `proof_capture`, then `review` and `proof_verify`; only proof for the
new head can reach final publication." and "A later head change requires fresh
proof; publication MUST NOT reuse a verified record from before that change."
Scenario 132 ("Slow hooks after a post-draft rebase are command work", "Refresh
is idempotent and bounded") exercises it. The workflow implements it as the
`pr_refresh_head` script node in
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`. That node
fails with `LIVESPEC_PR_REFRESH_HEAD_CHANGED` whenever the
`livespec-pr-refresh-changed` marker exists, and its failure edge routes to
`proof_capture`. It does not look at what the rebase brought in.

## The motivating run

hp run `01M4VSTCF4GWH9JWC53AEE0BP1` (bd-ib-t4dtx4, a small `AGENTS.md`
bullet; Definition of Done observes only `AGENTS.md`). Read from
`fabro events --json` on hp's fleet server (`http://127.0.0.1:32276`):

| stage | start (Z) | end (Z) |
|---|---|---|
| dod_gate | 23:34:12 | 23:35:36 |
| implement | 23:35:36 | 00:09:57 |
| janitor | 00:10:00 | 00:21:37 |
| publish_draft | 00:21:38 | 00:31:52 |
| proof_capture, review, proof_verify | 00:31:54 | 00:47:39 |
| pr_refresh #1 | 00:47:40 | 00:58:15 |
| pr_refresh_head: HEAD_CHANGED | 00:58:17 | |
| re-proof lap 1 (capture, review, verify) | 00:58:18 | 01:11:39 |
| pr_refresh #2 | 01:11:40 | 01:24:08 |
| pr_refresh_head: HEAD_CHANGED | 01:24:11 | |
| re-proof lap 2 | 01:24:12 | 01:36:04 |
| pr_refresh #3: GATE_FAILED | 01:36:05 | 01:49:56 |
| needs_human: NO_RUN_ID | 01:49:58 | |

The work was proven and verified by 00:47Z. The next 62 minutes produced
nothing new: two re-proof laps (25.2 min of capture, review and verify), three
sandbox gate runs at about 12 min each, and then a failure. The third refresh's
sandbox `just check` failed. The causes were check-heading-coverage-debt-register
(the #2917 timezone defect, livespec-dev-tooling-a6gq5n) and
check-master-ci-green while master was red. `needs_human` then failed
`LIVESPEC_NEEDS_HUMAN_NO_RUN_ID` (bd-ib-zddbkq).

Master commits in the window, by committer time (from `git log origin/master`):

- 00:31Z `693825eb` touched `plan/dolt-server-failures/**` only. That is what refresh 1 brought in.
- 00:54Z `4af8531c` touched `plan/publish-draft-green-work-loss/**` only, and
  01:00Z `edf5a38e` touched `plan/factory-idle-with-ready-work/**` only. Those are what refresh 2 brought in.
- 01:12Z `ea918b17` touched `plan/**`, and `35fea321` (spec v133) touched `SPECIFICATION/**`
  plus `tests/heading-coverage*.json`. Those are what refresh 3 met.

So both completed re-proof laps followed refreshes that brought in only `plan/`
research notes. Those notes cannot change what an `AGENTS.md` assertion
observes. A conservative path rule would have carried the proof forward twice
and saved 25 min of agent time on this run. The third refresh brought spec and
gate-input changes, and a conservative rule would correctly have re-proved it.

## Population, 2026-10-11 00:20Z to 2026-10-14 03:48Z

One `fabro ps -a --json` against hp's fleet server, then `fabro events --json`
for every ImplementWorkItem run longer than 40 min (132 runs). `pr_refresh` is
recent, so only 5 runs reached it:

- 3 `pr_refresh_head` UNCHANGED completions.
- 4 runs hit HEAD_CHANGED, with 5 re-proof laps and 64.1 min of
  capture, review and verify. That count excludes each refresh's own sandbox gate.
  - 01M4VSTCF4GWH9JWC53AEE0BP1, bd-ib-t4dtx4: 2 laps, 25.2 min, failed.
  - 01M4VSBSTC4103TZPMMRQFSHY6, overseer-3brqwk: 1 lap, 9.6 min, succeeded.
  - 01M4VQV7APGJS3ZAA38YAB7106, bd-ib-s6bowj: 1 lap, 15.3 min, failed.
  - 01M4TTKCTVFHD5Z0ZGZ2V1QYBB, bd-ib-mqevnt: 1 lap, 14.0 min, failed.

Master merged 46 PRs in the 24 h before the run (peak 6/h; 87 commits counting
reverts and spec snapshots). At that rate, a lap of about 25 min (refresh gate
plus re-proof) gives master time to move again before `pr`. Each lap therefore
raises the chance of the next refresh, and of hitting the three-refresh bound
or a refresh that a red master breaks.

## Direction (for the proposal, not decided)

The proposal must make the relevance rule DETERMINISTIC and CONSERVATIVE, and
re-prove whenever the rule is unsure. `pr_refresh` already re-runs the full
repository gate on the rebased head, so gate correctness is re-established either
way. The only question is whether the verified proof's observations could
differ on the new head. Candidate rule inputs:

1. The incoming range: `<old base>..<new base>`, and the paths it touches.
2. The item's own diff paths (merge-base..head), before and after the rebase.
   The carry-forward also requires the rebased item diff to equal the verified
   one, for example by equal `git patch-id`. Any conflict or refresh-repair
   round always re-proves.
3. Paths and spec headings named by the item's Definition of Done assertions,
   its `References:` line, and its captured proof steps' commands and inputs.
   A changed `SPECIFICATION/` file is relevant when it changes the text under
   a referenced heading, and otherwise only if the rule cannot tell.
4. A fixed gate and tooling path set whose change always re-proves: workflow
   and `.fabro` files, `.github/workflows/**`, hooks and `lefthook*`,
   `justfile`, `pyproject.toml`, lockfiles, `.mise.toml`, and the dev-tooling
   pack.
5. Any input that cannot be read means re-prove, naming the input.

A carried-forward refresh must leave an auditable record on the pull request.
The record names the verified head, the new head, the incoming range, the
decision and the inputs that decided it. `pr` must accept that record as the
proof of the head it publishes. This means changing the two ratified sentences
quoted above. That revise is the MAINTAINER's to ratify, and no session
self-ratifies it.

## Boundaries with neighbouring plans

- **publish-draft-green-work-loss** (epic bd-ib-acrr56) covers refresh REPAIR.
  That is a conflicted or gate-red refresh at publish_draft or pr_refresh
  (bd-ib-tzj9x, Scenario 176 in v134), plus hook time limits (bd-ib-xi63mq,
  Scenario 177). v134 landed as `5a04748f` and was reverted by #2925
  (`850abe2c`, with its two proposals `cf3052fc` and `4de59ea2`) at 03:46Z. It
  is to be re-landed. It neither adds nor removes the changed-head re-proof.
  Its repaired head ALWAYS re-proves, and this plan keeps that: a repair round
  is never carried forward. The two proposals edit adjacent paragraphs of the
  same contracts sub-section. Whichever revise lands second must rebase its
  text on the first.
- **stall-watchdog-false-kills** (epic bd-ib-laf735), bd-ib-4pn4pd: a resume
  never supplies the published head, so a resume entering at `pr_refresh`
  fails NO_PROVENANCE. That is about provenance, not relevance. A carry-forward
  record must be written so that resume provenance can read it, and it adds no
  new requirement there.
- **definition-and-proof-of-done** (epic bd-ib-7sjdzv) owns the Proof of Done
  record format and stages. This plan adds one record verdict or field for the
  carry-forward. It does not redesign capture or verify.
- **Not this plan:** the third refresh's gate failure (livespec-dev-tooling-a6gq5n,
  master-red refusals) and bd-ib-zddbkq (needs_human run id). Both are recorded
  as deferrals in the scoping event.
