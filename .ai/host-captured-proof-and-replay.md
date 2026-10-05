# Host-captured proof: taking a capture, and replaying it independently

A `host_captured` assertion is one no factory sandbox can prove. It is proved
by an agent session on an OPERATOR HOST, exercising the RELEASED build, and
then by a SECOND, independently started agent session that replays the same
steps and publishes its own verdict. The item rests in `acceptance` until that
replay lands.

Governing scenario: `SPECIFICATION/scenarios.md` §"Scenario 136 — A
host-captured assertion holds the item in acceptance until an independent host
replay verifies it against the released build". The surfaces named below are
the production ones — read them rather than re-deriving the flow, and note
that none of the five steps can be short-circuited: each one is the input the
next refuses without.

## The procedure, in order

1. **Declare the assertion under a `Host-captured` sub-heading carrying a
   non-empty `Reason:` line.** Both live inside the item description's
   `## Definition of Done` section; the title is matched case-folded by
   `_SUB_HEADING_MODES` in
   `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_definition_of_done.py`,
   and the reason must name the host surface the proof needs or the
   released-build requirement. A missing reason makes the declaration
   MALFORMED rather than absent: the assertions keep `host_captured`, and the
   approve valve refuses to move the item into `ready`, reporting that the
   sub-heading "carries no non-empty `Reason:` line, so its `host_captured`
   proof-mode declaration is malformed". For a work item both opt-out
   sub-headings owe a reason; for a PLAN epic `Host-captured` is the default
   and owes none, so only `Human-attested` does.

2. **Dispatch and merge as usual; the merged item then rests in acceptance
   with the host leg pending.** The host-side wall does not refuse an
   `ai-only` item for carrying a host leg. The post-merge acceptance pass
   lists the host-captured assertion as
   `pending the host leg; passes only from an independent host_verified record
   naming a build identity that contains the merge` (`PENDING_HOST_LEG_REASON`
   in `commands/_dispatcher_host_leg.py`), reports PASS, and leaves the rework
   counter unchanged. `needs-attention` surfaces the item as
   `hygiene:pending-host-leg:<item-id>`, and the accept valve refuses while
   the leg is pending.

3. **Capture on the host, by hand, against the released build.** Wait for a
   release whose tag contains the merge commit, install it, and run the
   assertion's steps on the host. Containment is checked by
   `merge_contained_in` in `commands/_dispatcher_host_containment.py`, which
   reads `gh api repos/<owner>/<repo>/compare/<base>...<head> --jq .status`
   and admits only `ahead` or `identical`. A record naming a build that does
   not contain the merge is reported `names a build that does not contain the
   merge` and the assertion stays pending — so capturing against the working
   tree, or against a release cut before the merge, buys nothing.

4. **Publish the capture with `post-host-record`**, which posts it as a new
   comment on the item's merged pull request:

   ```bash
   dispatcher.py post-host-record --repo <path> --item <id> \
     --verdict host_recorded --record <payload>.json --invoker <role:name>
   ```

   `<payload>.json` is a JSON object carrying a `build` object
   (`release_tag`, `installed_build`, `commit`) and an `assertions` array
   whose entries carry `text` — VERBATIM, as the Definition of Done states
   it, because an assertion the item does not declare is refused rather than
   published under a guess — plus `governing_scenario`, `steps` and `proof`.
   There is deliberately no `--identity`, `--session`, `--timestamp` or
   `--pull-request` flag: each is something the primitive COMPUTES, and a
   flag for one would be the route by which a session hand-formats the record
   the primitive exists to render. A `reproduced` field is DROPPED from a
   capture, whatever the payload claims — a capture is not its own replay.

5. **Have a separately started agent session replay the steps and publish its
   own verdict**, with `--verdict host_verified` or
   `--verdict host_not_reproduced` and its own payload, whose assertion
   entries DO carry `reproduced`. The publishing identity is computed from
   the invoking environment — `AGENT_SESSION_ENV_VARS` is
   `("CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "PI_SESSION_ID")`, read in
   that order, falling back to `gh api user --jq .login` when none is set —
   so a subshell, background job, sub-agent or second pane launched from the
   recording session INHERITS that identity and is refused before anything is
   posted: "the computed identity equals the identity that recorded the
   capture". Restarting the recording session is what changes the answer;
   re-running the command inside it never can. The replay drives
   `reconcile-merged` itself, which re-runs the acceptance pass; a
   `host_verified` record listing the assertion as reproduced passes it, and
   under `ai-only` the item closes to done.

## Two ways a replay goes wrong

Both are "instrument that cannot return a hit" failures in the sense
AGENTS.md §"Verification discipline (repo-additive)" Rule 2 means: each
produced a clean, plausible observation at exit 0, while the question being
asked could not have come back the other way.

### A publish branch seeded at an ancestor of master proves nothing

A proof about the publish-branch reclaim has to arrange for the publish ref
`feat/<item-id>` to stand somewhere the next run's push cannot reach. Seeding
it at a commit that is an ancestor of master — the release commit, say — does
the opposite. The next run branches from master, so its HEAD descends from the
seed, and the `publish_draft` node's push is the plain, non-forced
`git push -u origin "HEAD:refs/heads/$branch"`. The seeded ref is therefore
fast-forwarded by the next run and the push is simply accepted: no
`LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED` sentinel fires, the non-fast-forward
refusal the reclaim exists to clear never happens, and neither
`publish-branch-reclaim` nor `publish-branch-reclaim-held` reaches the
journal. "Publish accepted" is then guaranteed, so it discriminates nothing —
it is the identical observation a working reclaim and a never-reached reclaim
both produce.

Measured 2026-10-05 on `bd-ib-ht4c2m`: the first host record seeded
`refs/heads/feat/bd-ib-andmpe` at the v0.166.0 commit, an ancestor of master,
so its "publish accepted" observation carried no information. The independent
replay — pull request 2598, `host_not_reproduced`, session `01a10b66` — hit
the same seed with `bd-ib-dk3u2p`, whose first run fast-forwarded the branch,
published pull request 2604 and closed the item, leaving nothing to
re-dispatch.

So a seeded branch has to point at a commit master does not contain, on no
merged lineage, pushed to the publish ref deliberately. Only then does the
next run's plain push meet `! [rejected] … (non-fast-forward)`, which is what
`publish_draft` fails closed on and what the reclaim exists to clear. The
reclaim's own two preconditions then still apply on top of the seed — an
EARLIER journaled dispatch of the same item, and no live run — and AGENTS.md
§"Proof-of-Done, publish-branch reclaim, and drive action-id traps" records
both, along with the five hold reasons and why a held row's `reason` must be
read before clearing any publish branch by hand.

### A herdr agent pane finishes at `done`, so a wait on `idle` never returns

Step 5 needs a separately started agent session, and the usual way to launch
and watch one is a herdr pane. Such a pane finishes with agent status
`done` rather than `idle`, so a wait on such a pane has to accept either word.
A wait written on `idle` alone hangs on a pane that has already finished, and
nothing about it looks wrong — the pane is quiet, the wait is running, and the
status it is waiting for will never arrive.

The asymmetry is in herdr's own schema, which is what makes the mistake easy
to reach honestly. Measured first-hand against herdr 0.9.3's bundled API
schema (`herdr api schema --json`), two enumerations share one vocabulary and
differ by exactly this word:

- `PaneAgentState` — what an integration may REPORT, through
  `pane.report_agent` / `herdr pane report-agent --state` — is
  `["idle", "working", "blocked", "unknown"]`. There is no `done` in it.
- `AgentStatus` — what `agent.wait` matches on and `herdr agent get` renders
  — is `["idle", "working", "blocked", "done", "unknown"]`.

So `done` is observable but not reportable: it is herdr's own terminal status
for a pane whose agent has exited, and an operator reasoning from the
reportable vocabulary concludes — correctly for that surface, and wrongly for
this one — that a finished pane must be showing `idle`.

Write the wait to accept both words:

```bash
herdr agent wait <target> --until idle --until done --timeout <ms>
```

`--until` is repeatable, and omitting it entirely is equally correct: herdr's
own help states that without `--until` the wait "matches idle, done, or
blocked". Only the single-word form is broken. Pass `--timeout` as well —
without it the wait blocks indefinitely, which is what turns this from a
wrong answer into a stall.

Measured 2026-10-05 on `bd-ib-ht4c2m`: the recording session waited three
hours on the replay pane because it watched for agent status `idle` while the
pane had finished as `done`.
