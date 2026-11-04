# Proof-of-Done, publish-branch reclaim, and drive action-id traps

Moved word for word from `AGENTS.md` §"Proof-of-Done, publish-branch reclaim, and drive action-id traps" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## Proof-of-Done, publish-branch reclaim, and drive action-id traps

Three traps measured 2026-10-05 while driving plan
`definition-and-proof-of-done`. Each cost a wasted dispatch or a wrong
diagnosis, and none of them announced itself — every one produced a
plausible result at the surface the operator was watching.

**A host-captured proof record carries a publishing identity the primitive
COMPUTES from the recording agent session's OWN ENVIRONMENT, so any process
launched from that session recomputes the SAME identity and is refused as a
self-replay.** `computed_publishing_identity` in
`commands/_dispatcher_proof_identity.py` reads `AGENT_SESSION_ENV_VARS` —
`CODEX_SESSION_ID` first, then `CLAUDE_CODE_SESSION_ID`, then
`PI_SESSION_ID` (a nested Codex verifier inherits Claude's variable, so its own id wins) — and falls through to the forge login (`gh api user --jq
.login`) only when none of them is set. There is deliberately NO parameter a
caller can put an identity in: an identity a caller could NAME is one a
caller could RENAME, which would reduce the independence guarantee to a
naming convention. The consequence that bites is inheritance. A subshell, a
background job, a sub-agent, a `codex exec`, a second pane inside the same
session — each inherits that variable, so `post-host-record` refuses before
it posts anything:

```text
ERROR: post-host-record refused: the computed identity equals the identity
that recorded the capture (<identity>), so this post would not be evidence.
The host_recorded record it replays is <url>. A DIFFERENT session identity
must replay those steps.
```

Every refusal in that primitive fires BEFORE the `gh pr comment`, so nothing
is posted and nothing is lost — but no amount of re-trying from the
recording session can ever pass, because the inherited variable is the
input. **The replay therefore has to come from a SEPARATELY STARTED agent
session** — a new Claude Code, Codex or pi session, which exports a
different session id — or from a human at a terminal with no agent-session
variable set at all, whose identity resolves to the forge login instead.
Restarting the recording session is what changes the answer; re-running the
command inside it is not. Measured 2026-10-05: the first host record in this
repository is the `host_recorded` comment on pull request 2598, whose header
reads `Proof of Done — host_recorded — session
b1e14094-853e-412d-aa8b-c2adb51d7461 — 2026-10-05T09:28:17Z`. That third
field is a `session <uuid>` — a Claude Code session id, i.e. exactly the
value a replay from that same session would recompute. Scenario 136 of
`SPECIFICATION/scenarios.md` is the governing scenario.

**The publish-branch reclaim acts ONLY for an item that has an EARLIER
JOURNALED DISPATCH and NO LIVE RUN, so on a first dispatch it journals
nothing and leaves a surviving branch standing.**
`reclaim_stale_publish_branch` in
`commands/_dispatcher_publish_branch_reclaim.py` returns before asking
origin anything when `journaled_dispatch_ids` is empty: only a PREVIOUS
dispatch of that item can have left a publish branch behind, so on a first
dispatch the question has no possible yes, and a remote probe there would
put a forge outage on the critical path of every dispatch. The valve refuses
nothing and blocks no dispatch; it writes exactly one of two journal stages,
and the names matter because the ABSENCE of both is a third, silent outcome:

- `publish-branch-reclaim` — the surviving branch was preserved to a
  run-scoped ref and deleted from origin. The row carries `branch`, `head`
  and `preserved_ref`.
- `publish-branch-reclaim-held` — no reclaim was performed. The row carries
  `reason` and `detail`; the five reasons are `origin-unobservable`,
  `factory-unobservable`, `live-run`, `preserve-failed` and `delete-failed`,
  one per measurement that can fail. Every arm that cannot MEASURE holds and
  says which measurement stopped it, because a gauge that proceeded while
  blinded would turn `publish_draft`'s honest refusal into a silent ref
  deletion whose record reads exactly like a healthy reclaim.
- NEITHER row — the valve was never reached for that item. On a first
  dispatch that is the designed behaviour, not a fault.

**Read the held row's `reason` before clearing a publish branch by hand.**
The reasons are not interchangeable: `live-run` means a run is still alive
on that branch and a hand deletion destroys live work, while
`preserve-failed` and `delete-failed` mean the ref mechanics failed, so a
hand deletion discards the dead run's published head — the very proof the
reclaim exists to rescue. Measured 2026-10-05: on `bd-ib-andmpe` a dispatch
found the publish branch PRESENT but had no earlier journaled dispatch, so
it journaled no publish-branch row at all and left the branch standing; the
re-dispatch, after that run had ended, journaled `publish-branch-reclaim` at
2026-10-05T08:35:37Z. On `bd-ib-pa73qh` under v0.167.1 the row was
`publish-branch-reclaim-held` with `reason` `preserve-failed`.

**In zsh a drive action id written as an UNBRACED variable followed by a
colon and a literal word is REWRITTEN by a parameter modifier before
`drive.py` ever sees it.** zsh applies history-style modifiers to an
unbraced parameter expansion, so the colon and the value's FIRST LETTER are
consumed as a modifier and the rest of the word survives as literal text.
Measured first-hand with `zsh -f` on 2026-10-05, with `item=bd-ib-andmpe`
and the shell's working directory written below as `<cwd>`:

```text
"resolve-blocked:$item:ready"     -> resolve-blocked:bd-ib-andmpeeady
"reject:$item:rework"             -> reject:bd-ib-andmpeework
"set-admission:$item:auto"        -> set-admission:<cwd>/bd-ib-andmpeuto
"set-acceptance:$item:human-only" -> set-acceptance:.uman-only
"resolve-blocked:$item:backlog"   -> resolve-blocked:bd-ib-andmpe:backlog
```

Eight of the twelve valve values are rewritten — `ready`, `rework` and
`regroom` by `:r` (remove extension), `auto`, `ai-only` and `ai-then-human`
by `:a` (absolutize, which splices the working directory in), `human-only`
by `:h` (head, which collapses the id to `.`), and `citation-only` by `:c` —
while `backlog`, `manual`, `on` and `off` pass through untouched. **That
selectivity is what makes it dangerous: an unbraced invocation that worked
for `:backlog` is NO evidence the form is safe for `:ready`.** bash has no
such modifiers and leaves all twelve alone, so the same line that works in a
bash script fails typed into an interactive zsh.

Every rewritten form loses the value field, so `parse_human_valve_action`
sees two colon-separated fields where it needs three and
`run_human_valve_action` refuses with
`{"status": "failed", "domain_error": "invalid-action-id", "summary":
"Unsupported human valve action id."}`. Measured in one line:
`parse_human_valve_action(action_id="resolve-blocked:bd-ib-andmpeeady")`
returns `None`, while the braced form returns
`("resolve-blocked", "bd-ib-andmpe", "ready")`. The discriminator is that
the refusal echoes the MANGLED `action_id` — the id in the error is not the
id you typed — and in the `:a` cases it shows an absolute path, which reads
like a path bug rather than the quoting bug it is.

**Brace the variable: write `resolve-blocked:${item}:ready`, never
`resolve-blocked:$item:ready`.** A fully literal id is equally safe, and is
how the 2026-10-05 instance was finally driven.
