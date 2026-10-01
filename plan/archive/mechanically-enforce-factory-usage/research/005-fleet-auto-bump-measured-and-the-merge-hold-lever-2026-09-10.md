# The auto-bump measured live, and the merge hold as Phase-0's suppression (2026-09-10)

Written at the fresh-context resume the 2026-09-10 18:07Z handoff asked for.
Research note 004 resolved rollout decision #4 by reading the workflows; this note
MEASURES the machinery on the forge, finds one of 004's supporting claims wrong in
a direction that matters, and records the lever Phase 0 actually uses. Every
number was read from the forge on 2026-09-10 between 18:15Z and 18:25Z.

## 1. What the forge shows

**The release train is fast, and every tag fans out immediately.** dev-tooling cut
eight releases in the twenty hours before this note (`v1.83.6` at 22:12Z on the
9th through `v1.85.1` at 18:12Z on the 10th). Within four minutes of `v1.85.1`,
every one of the seven consumers had a `chore(deps): bump livespec-dev-tooling pin
to v1.85.1` pull request open with **auto-merge already armed** — verified
`auto=true` on all seven (livespec #2755, driver-claude #739, driver-codex #679,
driver-pi #228, orchestrator-git-jsonl #853, console #1205, dev-tooling's own
self-pin #2238). The next release PR in dev-tooling (#2239, "release 1.85.2") was
already open with auto-merge armed too. So research note 004's core claim holds
and is sharper than it said: the body-changing release would reach every
consumer's master **within about an hour of the tag**, not "within ~24h".

**But the pins are NOT advancing, and 004's "bump PRs merge green" premise is
only half true.** The live pins read `v1.70.0` (this repo), `v1.69.4` (livespec,
driver-claude), `v1.64.1` (overseer), `v1.85.0` (console) against latest `v1.85.1`.
This repo has **never merged** a dev-tooling bump PR: twenty-three of them
(#2417 through #2439) were opened since the 9th and every one was closed
unmerged, each superseded by the next release's PR. The open one, #2439, is red
on `check-per-file-coverage` and `check-metadata-batch`, and the failing test
names a dev-tooling regression against this repo
(`livespec_dev_tooling/checks/_plan_record_timeline.py:148`,
`AttributeError: 'list' object has no attribute 'unwrap'`). overseer #2261 and
runtime #704 are red the same way. The consumers that DID merge on the 9th
merged `v1.69.4` / `v1.70.0`; something after `v1.70.0` broke the bump for the
rest of the fleet.

Two consequences. First, the standing fleet-currency breakage is real and
unrelated to this plan: the pin-freshness sweep opens and closes a red PR here
every day and nobody is paged. That is a separate item (see §4). Second, and
this is the correction to 004: a red bump PR is not a suppression. It happens
to block the break in this repo today, but relying on it would be blinding a
gauge — the "never defeat a live check" rule — and it says nothing about the
consumers whose bump PRs are green.

## 2. What the levers actually are

Read from the workflows, with one addition 004 did not have:

- **`set-merge-hold:<id>:on`** — a first-class drive valve. The factory
  implements, reviews and opens the pull request; the pr stage pushes but does
  not arm auto-merge, reports `MERGE_HOLD=held`, the run ends green, the item
  stays `active` holding no capacity slot, and `needs-attention` carries
  `hygiene:merge-hold:<id>` until `set-merge-hold:<id>:off` arms the merge.
  Verified present in the deployed plugin build: `workflow.toml` declares
  `merge_hold = false`, `_dispatcher_engine.py` gates on it, and
  `_needs_attention_merge_hold.py` emits the row.
- **Hold the tag.** dev-tooling's `auto-enable-merge.yml` skips a release-please
  PR carrying the `do-not-merge` label, but it triggers on `opened / synchronize /
  unlabeled`, never on `labeled`, so an already-armed release PR also needs
  `gh pr merge --disable-auto`. Holding the tag holds both the fan-out and the
  daily sweep (the sweep asks `gh release view` for the latest tag). The
  `release-park` alarm goes red after 24 hours, which is the honest signal for a
  deliberately parked release.
- **Open the bump PRs without auto-merge.** The reusable sweep already carries a
  `no_auto_merge` flag for one source (`codex-acp`). Extending that to a
  dev-tooling-side switch for the dev-tooling source is a single-repo code change
  to the two reusable workflows, but consumers pin those workflows by tag, so it
  reaches them only as they bump — which is the thing being suppressed.

And the scope correction that makes the choice tractable: the window that needs
suppression is the **hours** between the tag and the last consumer's paired
bump-plus-reinstall, not the warn phase. Freezing the release train or the
fleet auto-bump for N days would stop every other thread's dev-tooling fixes
fleet-wide.

## 3. Phase-0 decision: dispatch R1a under a merge hold

Sequence, in this order because a `ready` item in the dev-tooling tenant is
visible to that tenant's drain the moment it is routed:

1. `set-merge-hold:livespec-dev-tooling-pxsr7w:on`.
2. Route pxsr7w backlog → ready through the intake Definition-of-Ready gate.
3. `drive --action impl:livespec-dev-tooling-pxsr7w` (factory `hp`,
   warn-default per the item's criteria).

Nothing reaches a consumer until a human releases the hold, so the maintainer's
"suppression first" mandate is met at the source rather than in ten consumer
workflows. The consumer-side lever — which of "hold the tag" or "open bump PRs
without auto-merge" — is decided at R1a's merge time and is R2's first
deliverable; R2 (`livespec-dev-tooling-xzxrm5`) already owns the fleet installer
re-run and the census. Recommendation for that ruling: the `no_auto_merge` switch,
because it is the only lever that lets each consumer merge its bump deliberately,
paired with the one-command reinstall on that primary.

Vetted per the escalation rule before acting: both legs reported. The Codex leg
returned NO (act on this default; the lever choice is escalation-worthy only at
merge time). The Opus leg returned NO with two conditions, both adopted: verify
the hold is in effect BEFORE dispatching, and make the lever ruling an explicit
precondition of R1a's merge, stated on both items. Verified: the
`merge-hold:on` label was read back on pxsr7w before it was routed to `ready`.

## 4. Side findings, not acted on here

- **This repo cannot merge any dev-tooling bump past `v1.70.0`.** Twenty-three
  red-or-superseded bump PRs since the 9th; the failing test names
  `_plan_record_timeline.py:148` in dev-tooling. Filed as a separate item rather
  than widened into this plan.
- **`gh pr list --search` with a conventional-commit scope returns nothing.** A
  query string containing `chore(deps):` is a malformed search (parentheses
  group), so it matches zero rows with exit 0. A nine-repo survey came back
  empty this way before a jq title filter found every PR. Recorded in the
  AGENTS.md instrument catalogue in the same pull request as this note.
