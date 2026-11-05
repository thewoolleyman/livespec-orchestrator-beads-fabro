# Independent review: factory run-work preservation, chosen direction (Fable, 2026-11-05)

Reviewer: Fable 5.1, read-only, no part in the design. Everything below was checked against the files named; anything I could
not verify is marked UNVERIFIED with the scope I searched. Line numbers refer to the files as they stood on 2026-11-05.

Sources read: note 004 and the spec proposal in the `plan-frwp-direction` worktree; the four children in
`tmp/frwp-review/children-2026-11-05.md`; `workflow.fabro` (master and `e7f5ec757^`), `workflow.toml`; `contracts.md`
paragraphs at lines 3457, 6302, 6304, 9336-9400; the Dispatcher modules under `commands/`; `dev-tooling/checks/fabro_port_seam.py`;
the fork lineage `carrier-candidate-registered-20261023` (`checkpoint.rs`, `hooks.rs`, `source.rs`, `publish.rs`,
`fabro-types/src/settings/run.rs`, `docs/public/agents/hooks.mdx`); `preserve_runs.sh`; ledger items bd-ib-w64kr3 and
bd-ib-sgnfom (read-only `bd show`).

## Ranked findings

### F1 (severe) — The engine itself resets the run branch to a detached HEAD at the next checkpoint, so "push the run branch tip, never HEAD" does not close the rhivsm hole; the sibling rule then makes the useless tip the "newest" ref

Claim. Guard 1 of note 004 §4 ("preserve the run branch tip, never a detached HEAD") protects only until the next engine
checkpoint. After that checkpoint the run branch tip IS the detached HEAD's commit plus one empty checkpoint commit, the design's
sibling rule writes that tip to `<run-id>-<sha12>`, and the design's "newest = latest committer time" rule and recovery routing
(proposal finding 3) then prefer the sibling, which carries no work.

Evidence.
- `checkpoint.rs:477-543` (`commit`): the checkpoint calls `ensure_repository` first (line ~491) and then `git add -A` and
  `git commit --allow-empty` on whatever HEAD is (lines 528-537, sha read by `rev-parse HEAD`).
- `checkpoint.rs:766-790` (`ensure_repository`): when `symbolic-ref HEAD` is not the run branch (a detached HEAD, or master), it
  runs `git checkout -q -B <run branch>` — `-B` moves `fabro/run/<run-id>` to the current HEAD. The run's real tip is dropped from
  the run branch at that moment.
- The measured incident (note 004 §4; `preserve_runs.sh` comment "A late node (e.g. refresh_repair) can leave the workspace HEAD
  detached on master") shows the detached-HEAD state does occur in production runs.
- Proposal finding 1: "The run's newest work-in-progress ref is the one whose commit has the latest committer time." The empty
  checkpoint on top of master is the newest commit. The guard "MUST NOT name a ref whose commit is reachable from the item's base
  commit alone" does not catch it: a fresh empty commit on top of the default branch is not reachable from the base.
- Proposal finding 3 seeds the re-dispatch from "the run's newest work-in-progress ref" — so a re-dispatch after this sequence starts
  from master, and the real work sits on the older sibling that "MUST NOT be taken".
- Note: I could not establish which node detached HEAD in run 01M6MHQE92Q4. `refresh_repair`'s script (`workflow.fabro:721-726`)
  only reads a brief file; it checks nothing out. UNVERIFIED which stage detaches HEAD (scope: the `refresh_repair`,
  `publish_draft` and `pr_refresh` node scripts I read, and `hooks.rs` `restore`/`check_out_source` at 859-958, which I did not
  trace end to end).

Recommendation. Add one cheap guard to the preserve step and to the "newest" rule: never push, and never count as newest, a tip whose
TREE equals the tree of the item's base commit or of `origin/<default_branch>`'s head (`git rev-parse <tip>^{tree}` compared to
both). That is the only shape the reset produces (empty checkpoint on a default-branch commit), and the test is two `rev-parse`
calls. Replace "latest committer time" with "the newest-by-committer-time ref among those whose tree differs from both" in finding
1 and 3. Also state in the spec that the rule is needed because the engine moves the run branch to HEAD at the next checkpoint,
so nobody later "simplifies" it away.

### F2 (severe) — Work item bd-ib-ofvsr3's own text tells the implementer to force the push

Claim. The item's title and Definition of Done say "never forcing a ref"; its Why says the opposite, and an implementer reading the
Why first will force.

Evidence. `children-2026-11-05.md:27`: "but push-only (no `git add`, no commit) and forced, because the Red-to-Green amend and the
Red-retry rewind rewrite the run branch." versus line 1 ("never forcing a ref") and line 8 ("without a forced update"). The forced
push is exactly what note 004 §4 measured as the regression. The interim reference script the item names also forces:
`preserve_runs.sh` pushes `"+$sha:$ref"`; the `+` is harmless only because the script first redirects a non-ancestor tip to a
sibling, which the item does not say.

Recommendation. Rewrite the Why before the item is approved: "push-only, never forced; a tip that descends from no existing
work-in-progress ref opens a `<run-id>-<sha12>` sibling". Note in the item that `preserve_runs.sh` is the reference for the branch
and sibling logic only, not for its `+` refspec.

### F3 (severe) — bd-ib-xdhe5z's Definition of Done still states the invariant the maintainer gave up, so it is not gradeable under this design

Claim. The item asserts that before every cancel, removal and sweep "the run's newest committed tree is on a named ref on origin",
and its host-captured proof asserts a run cancelled at its wall budget "leaves that committed tree fetchable". Under the chosen
design the destroy step publishes nothing and reads no sandbox; a commit the detached commit runner made during the node visit in
progress is on no ref when the run is destroyed, by the maintainer's explicit acceptance.

Evidence. `children-2026-11-05.md:48-58` (eleven bullets, seven of which say "the run's newest committed tree is on a named ref on
origin"); line 64 (host-captured proof); line 76 ("This item states the INVARIANT ... Do not implement this item ahead of that
direction") — the direction has now been chosen and the item was not re-cut. Proposal finding 2: "The step adds no new read of a
live sandbox ... the work in progress that no ref carries is the bounded loss this section accepts." Note 004 §3.2 says the same.
The item's References line names Scenario 175, not the new Scenario 315.

Recommendation. Re-cut the Definition of Done to what the design actually promises: "before the destroying call the item carries a
`livespec-preserved-tree` comment naming every ref that preserves the run, or stating none does; the destroy proceeds either way; a
repository check fails a destroy path that does not go through the step". Delete the "newest committed tree is on origin" bullets or
reword them to "the newest tree a FINISHED node visit left". Point References at Scenario 315. Drop bullet 10 ("A later dispatch ...
receives that ref in its brief"), which duplicates bd-ib-v6br5b.

### F4 (high) — The credential path the step needs is being withdrawn by two items whose Definitions of Done do not name it

Claim. The design relies on the Dispatcher-materialized `push_origin` helper. That helper mints a GitHub App installation token from
the App credentials in the container environment. bd-ib-w64kr3 removes "any key from which one can be minted" from agent stages,
and bd-ib-sgnfom's Definition of Done confines publication credentials to `publish_draft`, `pr_refresh`, `pr` and "a command node
that preserves a run's work, such as the needs_human preservation step". A work-in-progress preserve step that is a RUN HOOK is
neither a command stage nor a command node, and the proposal's own wording calls it a "command step (or workflow run hook)".

Evidence.
- `_dispatcher_git_push.py:15-21`: `push_origin` refuses when `LIVESPEC_AGENT_STAGE` is anything but empty, `publish_draft`,
  `pr_refresh`, `pr`; lines 60-66 and 74-80: it mints a fresh installation token per push through `mint_app_token.py`, which
  needs the App id and private key.
- `workflow.toml:40-56`: the App id and private key ride the container-level `[environments.livespec-ci.env]` table, "the
  container-level channel that reaches every node's subprocesses". Nothing today gives a command node a credential an agent node
  cannot read; whatever w64kr3 builds to change that decides whether a hook or command node can still mint.
- `_dispatcher_graph_adapters.py:219` sets `LIVESPEC_AGENT_STAGE` only on the agent launch command, so a command node or a
  sandbox hook does not inherit it today. Good — but w64kr3 may change where the gate lives.
- `bd show bd-ib-sgnfom` (2026-11-05): Definition of Done bullet 3 names "the needs_human preservation step" only.
  `bd show bd-ib-w64kr3`: "no GitHub App credential and no key from which one can be minted" in every agent stage.
- Fabro docs `hooks.mdx:156, 271-275`: a command hook runs in the sandbox by default (`sandbox = true`) in "the same environment
  as the agent's tools"; with `sandbox = false` it runs on the host, which has no workspace to push from.

Recommendation. Make bd-ib-ofvsr3 depend on bd-ib-sgnfom (or land before it with an explicit note in sgnfom's Definition of Done),
and amend sgnfom's bullet 3 to name both preservation steps, as the spec amendment does. Decide the mechanism (F6) before w64kr3,
because a run hook has no stage identity for a per-stage credential scheme to key on.

### F5 (high) — "Before the next agent turn starts" is vacuous for the last visit of a run that ends at `non_converged` or `dead_implementer`

Claim. Finding 1's timing clause gives no deadline when there is no next agent turn. Three terminals are reached from command nodes
after a committing agent node and push nothing themselves; under the letter of the clause the last fix lap's work need never reach
origin.

Evidence. `workflow.fabro:2223` `janitor -> non_converged`, `review_fix_admission -> non_converged`, `recapture_route ->
non_converged` (edges listed at 2343-2420), `implementation_diff -> dead_implementer` (2164). The `non_converged` node
(2110-2114) grades counts and reads pull-request comments; I found no push in the first 1200 characters of its script
(UNVERIFIED for the remainder; scope: `grep -n push_origin|needs-human/` over the whole file found pushes only in `needs_human`
and the publish nodes). `needs_human` is the only terminal that pushes (2066-2071).

Recommendation. Change the deadline to "before the run takes its next transition, or before the run ends" and add a Scenario 314
case for a run that ends at `non_converged` after a fix visit. With the mechanism in F6 (settle nodes or `checkpoint_saved`) this
costs nothing extra; it only closes the wording.

### F6 (high) — The mechanism question is posed between the wrong two options; `checkpoint_saved` exists and the existing settle nodes are the simplest command-node placement

Claim. Note 004 §6 weighs "command node after each agent node" (edge-condition surgery on every agent node) against a
`stage_complete` hook (fires only on success, ordering relative to the checkpoint unknown). Two better options are not considered.

Evidence.
- The fork's hook event enum includes `CheckpointSaved` (`fabro-types/src/settings/run.rs:2502-2516`) and the docs describe it as
  "After a checkpoint is written to disk", non-blocking, with a node-id matcher (`hooks.mdx:114, 224`). That is exactly the event
  the design wants: it fires after the checkpoint, so the tip it sees is the one to preserve. UNVERIFIED that this fork's Petri
  engine emits it: `grep -rn "CheckpointSaved\|checkpoint_saved" lib` finds only the enum and the TypeScript client constant;
  the emitter lives in Petri's hook service, which is outside `lib/` (`hooks.rs:3-9`). Measure it first.
- `stage_complete` is documented "After a node handler finishes successfully" (`hooks.mdx:106`), and `stage_failed` separately.
  The checkpoint is taken in `prepare_result` (`hooks.rs:1521-1572`, call at 1546-1547), so whether a `stage_complete` hook sees
  the visit's checkpoint depends on Petri's ordering, which I could not read. Since HEAD is attached to the run branch
  (`ensure_repository`), the agent's own commits are already on the tip before the checkpoint; only the checkpoint's capture of
  uncommitted files would be one visit late.
- Command hooks "do not fail open. A non-zero exit code (other than 0 or 2) produces a block decision" (`hooks.mdx:362`); the
  step must therefore `exit 0` unconditionally to satisfy "never fails the run".
- The single-node graph the maintainer is reverting to already has three command nodes that sit exactly where committed work
  lands: `implement_commit_settle` (`e7f5ec757^:workflow.fabro:411`, edge 2234), `fix_commit_settle` (572), and
  `review_fix_commit_settle`. Agents commit only through the commit runner in those three agent nodes; every other node's
  checkpoint holds non-product state (proof assets, findings) that the broker already posts. Adding the push to the END of those
  settle scripts preserves every commit-runner commit after it has settled, moves no edge condition, adds no node, and makes three
  to six pushes per run instead of thirty or more.
- Cost of "every node visit": every checkpoint is `--allow-empty` (`checkpoint.rs:532`), so every node visit moves the tip and the
  clause fires on every one; each push mints a new installation token (`_dispatcher_git_push.py:74-80`). Thirty mints per run
  across concurrent runs is a real App rate-limit exposure that the design does not mention.

Recommendation. Order of preference: (1) one `[[run.hooks]] event = "checkpoint_saved"` block in `workflow.toml` IF a measurement
shows the fork emits it after the checkpoint — zero graph change; (2) otherwise, the push at the end of the three existing settle
nodes plus `needs_human`; (3) only if the maintainer insists on every visit, new nodes. Drop `stage_complete` from the note; it
is the weakest of the four. Narrow the spec clause from "every node visit" to "every node visit that can leave a commit on the run
branch" so that (2) conforms without a waiver.

### F7 (high) — The preserve-then-destroy wrapper and its "any other module" check are the design's largest piece and are mostly unnecessary once the refs exist; the check as specified is also not implementable with the cited family

Claim. Finding 2 wraps nine destroy call sites so each can read the forge and write a receipt before destroying. Once every finished
visit is already on origin, nothing at destroy time needs to be preserved; the receipt belongs at the ONE place a run's ending is
already recorded. The check "fails when any Dispatcher module, other than the module that implements this step, calls a Fabro
operation that cancels or deletes a run" cannot be built on `fabro_port_seam`, which enforces the opposite thing, and would
false-positive on non-Fabro `.cancel(` calls and on probe-run reaps.

Evidence.
- `fabro_port_seam.py:1-30, 131`: the check asserts that Dispatcher modules reach the engine ONLY through `FabroPort`
  (`FAMILY_PREFIX = "_fabro_port"`). It says nothing about which callers may call `port.rm`. Note 004 §3.2 ("The `fabro_port_seam`
  family of checks fails any Dispatcher module that destroys a run another way") describes a check that does not exist.
- `.cancel(` is also a thread/handle verb: `session_wait.py:149`, `_session_wait_pane.py:246,299`,
  `_dispatcher_codex_app_server_io.py:98`. An AST check keyed on the method name needs receiver typing to avoid them.
- `_acp_availability_probe_run.py:346` calls `port.rm` on probe runs that have no work item; the proposed clause has no exemption,
  so either the check flags it or the step must write a receipt on no item.
- Recovery routing does not read the receipt: `_dispatcher_recovery_preserved.py:221-248` discovers the needs-human ref by
  `git ls-remote refs/heads/needs-human/<run>` for the run ids the journal names. A work-in-progress ref carries the item id AND the
  run id in its name, so routing can discover it the same way. The receipt is for humans.
- The terminal disposition is already one function: `_dispatcher_terminal_routing.py:100-112` (`dispose_terminal`, with
  `_dispose_external_fabro_cancel` at 115-160 writing the "cancelled outside the Dispatcher" comment), plus the reconcile absent-run
  release for a run that vanished with no Dispatcher watching.
- Internal tension in finding 2: it requires the step to "perform every publication an existing clause ... requires for that
  ending (the checkpoint-failed publication and the janitor-green publication above)" — both read the live sandbox through
  `/runs/{id}/files` (`contracts.md:6302, 6304`; `_dispatcher_preserved_tree.py:1-17`) — and in the same paragraph says the step
  "adds no new read of a live sandbox and MUST NOT delay a destroy on one". Note 004 §3.2 says the design "removes the dependency on
  Fabro's `/runs/{id}/files` transport on Kubernetes" while keeping Scenario 306, which depends on it.

Recommendation. Replace finding 2 with: "When the Dispatcher records a run's ending (its terminal disposition) or releases an item
whose run is absent, it lists `refs/livespec/wip/<item>/<run-id>*` on the forge and writes one `livespec-preserved-tree` comment
naming what it found." No wrapper, no new check on nine call sites. For plan assertion 3 ("a destroy path that skips preservation is
caught by a check"), satisfy it with the check that matters under this design: a declaration test that the workflow carries the
preserve step at every place the clause names (the same shape as `tests/test_factory_checkpoint_declaration.py`, which
`workflow.toml:479-480` already cites as binding `skip_git_hooks`). Record on the epic that assertion 3's "destroy path" wording
predates the direction; the maintainer can confirm in one line. If the maintainer still wants a caller check, make it a type seam —
`FabroPort.rm(..., receipt: PreservedTreeReceipt)` — so pyright is the check and `.cancel(` ambiguity never arises. Retire Scenario
306's janitor-green publication: a janitor-green head is a committed checkpoint on the run branch and is on a work-in-progress ref
already; that also lets bd-ib-adcaa6, bd-ib-vraou4 and bd-ib-ds4yrm close as superseded instead of becoming "callers of the
preserve-then-destroy step" (note 004 §5).

### F8 (medium) — `needs_human` has the same detached-HEAD defect the design fixes for the new step, and the proposal leaves it

Claim. The needs-human preservation commits and pushes `HEAD`, not the run branch tip.

Evidence. `workflow.fabro:2071`: `livespec_preservation_push git -c core.hooksPath=/dev/null push origin "HEAD:$ref"` (two
occurrences), after a `git add`/`git commit` on HEAD. With HEAD detached on master, the needs-human ref preserves master plus the
working-tree dust; the run branch's work is on no ref. The proposal's finding 1 states "the commit preserved MUST be the tip of the
run branch, never the workspace HEAD" for the new step only; the credential-clause amendment names the needs-human step without
giving it the same rule.

Recommendation. One sentence in the needs-human paragraph (§"A factory run never awaits a human") or in finding 1: the needs-human
preservation pushes the run branch tip (or re-attaches HEAD to it first). Cheap, and it removes the second copy of the hole F1
describes.

### F9 (medium) — Several clauses in the proposal are untestable or factually wrong as written

Claims and evidence.
1. Scenario 314, first case: "When the run reaches its next agent turn Then origin's ref ... points at commit I". Between the
   implement visit and the next agent turn, every command node visit adds an empty checkpoint (`checkpoint.rs:532`), so the ref
   points at a descendant of I, not I. Say "points at I or at a descendant of I whose tree is I's tree".
2. Scenario 314, third case: "When a refresh_repair visit rebases the run branch". `refresh_repair` (`workflow.fabro:721-726`)
   rebases nothing; it reads `livespec-refresh-repair-brief` and exits 0 or 1. The rebase is `pr_refresh`'s. Name the node that
   does it, or name none.
3. Finding 1: "the comment MUST state, for the newest ref, whether its commit is the run branch tip the run last reported". The
   run's last reported tip is the `git_commit_sha` in the engine's checkpoint note (`hooks.rs:716-725`), readable only while the
   run record exists. After `fabro rm` or a server crash — the endings this design exists for — it cannot be read. Make it "when
   the run's events are readable".
4. Finding 2: "When a `livespec-preserved-tree` comment written after the run's last node visit already names the run's refs, the
   step MUST NOT add a second one." Deciding "after the run's last node visit" needs the run's events (same problem) and the
   comment's timestamp. Replace with "already names the same newest ref and commit".
5. Finding 4 and bd-ib-efiasj bullet 5: "Refs whose item was already `closed` before this paragraph took effect are outside its
   scope." Nothing records when the paragraph took effect, so the Dispatcher cannot grade it. Simplest fix: trigger deletion only on
   the Dispatcher's OWN close/accept transition (drop "or on any later pass that reads the item"). That excludes every previously
   closed item with no cutoff, and the "retry on a later pass" bullet becomes a retry of a journaled deletion, not a scan.
6. Finding 1: "the engine's checkpoint for that visit moved the tip". The tip also moves when the agent commits and the checkpoint
   is then "reused" (`checkpoint.rs:492-500`). Say "the tip of the run branch differs from the tip last preserved".
7. Finding 1 names `<sha12>` as "the first twelve hexadecimal digits of the first commit written to that ref" — fine — but Scenario
   314 case 3 says "first twelve digits of G", and `preserve_runs.sh` uses `${sha:0:12}` of the pushed sha; consistent. No change.
8. The credential amendment says the step "MUST use it only to push the run's own ... refs". An installation token cannot be scoped
   to a ref; this is a prose MUST inside a paragraph whose first sentence is "MUST NOT rest on prompt prose alone". Acceptable as a
   step obligation, but say "the step pushes only ..." rather than implying the credential is limited.

### F10 (medium) — The design overstates how often the run branch is rewritten, which inflates the sibling machinery's importance

Claim. With the single `implement` node, the Red commit and the Green amend both happen INSIDE one node visit, before that visit's
checkpoint; the amend therefore rewrites nothing that was pushed. Note 004 §2 and §4 describe the amend as a rewrite of the run
branch that the sibling rule exists for.

Evidence. `hooks.rs:1521-1572`: one checkpoint per attempt, in `prepare_result`, after the handler returns. The pre-split graph
(`e7f5ec757^:workflow.fabro:193, 411, 2233-2238`) has `implement -> implement_commit_settle -> implement_completion`; the amend
is the commit runner's, waited on by the settle node. The rewrites that CAN move a pushed tip are `pr_refresh`'s rebase
(`research-context-facts-2026-11-04.md:50`) and the engine's reset in F1. The sibling rule is still right (it is what saves the
work in F1), but its stated motive is wrong, and bd-ib-ofvsr3's Why repeats the wrong motive as a reason to force (F2).

Recommendation. Correct §2 and §4: "the amend inside `implement` precedes the visit's checkpoint and rewrites no pushed tip; the
rewrites that matter are the publish-stage rebase and the engine's `checkout -B` after a detached HEAD".

### F11 (low) — Minor holes in the "one node visit" bound that the notes should state rather than leave implicit

- A cancelled attempt is not checkpointed (`hooks.rs:1543-1545` returns before `snapshot` on `Status::Cancelled`), so a cancel
  that lands during the preserve step itself (a settle node, or the hook) loses that step's preceding visit's commit-runner
  commits if they settled after the previous push. That is still one visit; say so.
- A retried attempt (`stage_retrying`) checkpoints per attempt; a `fix` attempt that times out and is retried leaves two tips in
  sequence, both descendants of the previous push — fast-forwards. No hole, worth a sentence.
- `[run.run_branch] push = false` (`workflow.toml:432-434`) leaves `self.publisher` unused (`hooks.rs:695-716`), so the design's
  push never races the engine's. Correct, and worth stating as a precondition so nobody turns the engine push on later.
- The `refs/livespec/wip/` namespace is not fetched by a default clone, so the WIP refs cannot "pollute the remote" in the sense
  the `workflow.toml:428-431` comment meant. Good; say it there when the comment is next touched.

## Answers to the brief's questions

1. Holes. (a) F1: a run whose HEAD was detached and then checkpointed again — the engine resets the run branch, and the design's
   "newest" rule follows it to a work-free tip. (b) F5: runs ending at `non_converged` or `dead_implementer` have no "next agent
   turn", so the last visit's push is not required by the clause. (c) F8: the existing `needs_human` ending pushes HEAD. (d) F11:
   a cancel during the preserve step loses one visit, as accepted.
2. Correctness. The fast-forward-or-sibling rule is correct and implementable in a command node today (`push_origin` exists, is
   Dispatcher-materialized, and is callable from a command node; `git merge-base --is-ancestor` plus a non-forced refspec is all it
   needs), with the tree-equality guard of F1 added. The checkpoint is taken in `prepare_result` after the handler returns, so a
   command node that follows sees it; whether a `stage_complete` hook does is UNVERIFIED and `checkpoint_saved` is the event to
   measure (F6). The credential reaches a command node today; whether it reaches one after w64kr3/sgnfom is undecided and must be
   decided with them (F4). Settle-node placement beats both "a node after every agent node" and `stage_complete` (F6).
3. Over-engineering. Unnecessary: the nine-site preserve-then-destroy wrapper and its caller check (F7); the receipt's ancestry
   statement against the run's last reported tip (F9.3); "every node visit" where three settle nodes carry every commit (F6);
   keeping Scenario 306's sandbox-read publication and the three per-path items (F7); the "took effect" cutoff (F9.5). Smallest
   design meeting the plan's six assertions: one push step in the three settle nodes and `needs_human` (or one `checkpoint_saved`
   hook), with the F1 guard; routing extended to `ls-remote refs/livespec/wip/<item>/<run>*`; one receipt comment at the existing
   terminal disposition and absent-run release; deletion of the item's `refs/livespec/wip/` and `preserved-publish/` prefixes on
   the Dispatcher's own close/accept; a declaration test for the workflow step as assertion 3's check. Two work items instead of
   four (progress step + routing; receipt + retention), or three if the maintainer wants retention separate.
4. Spec quality. F5, F9 (seven items), F3 (xdhe5z), F2 (ofvsr3 contradicts itself), F4 (sgnfom's Definition of Done omits the step).
5. Big picture. The design treats the run branch as a stable truth and HEAD as the hazard; the engine treats HEAD as the truth and
   rewrites the run branch to match (F1). Every preservation rule here should be written against trees, not refs: a ref is worth
   preserving when its tree differs from what origin already holds. The receipt and the wrapper are the design's bulk and buy the
   least; the push and the routing extension buy nearly everything.

## Verdict

The direction is right and simple at its core: one non-forced, tree-guarded push after each committing visit, discovered by
routing from the ref name, cleaned up at close. As written, the proposal and the children wrap that core in a destroy-time
wrapper, a caller check that cannot be built on the cited family, and receipt obligations that need data the targeted endings
destroy. Two defects must be fixed before anything is dispatched: the engine's reset of the run branch to a detached HEAD defeats
the "newest" rule (F1), and bd-ib-ofvsr3 instructs a forced push (F2). bd-ib-xdhe5z's Definition of Done must be re-cut to the
accepted loss (F3), and the credential items must name the new step (F4). With those four fixed and finding 2 collapsed to a
receipt at the existing terminal disposition, the design meets the plan's Definition of Done at roughly half the proposed surface.

REVIEW-COMPLETE
