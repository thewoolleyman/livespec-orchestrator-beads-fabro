# 005 — Wave B's pushed commit did not compile, and the two review legs were not independent

Research note for plan thread `fabro-fork-control-plane-gaps` (epic
`bd-ib-bb41`), 2026-09-07, the session that resumed after the 16:33Z restart.
Status is read from the ledger, never from this file. Labels **measured** /
**inferred** as in 001.

Two findings, both about verification rather than about the Wave B fixes
themselves. The first cost one rebuild cycle. The second nearly cost the whole
value of the two-leg review protocol, and it was caused by this session's own
brief.

## 1. The pushed Wave B commit did not compile — and the author's evidence was true

The 2026-09-06 handoff recorded that the full seven-crate chain "was started
after a final import fix and KILLED by this restart before reporting — it has
NO verdict", and instructed the successor to re-run it first. That instruction
was correct and it paid.

**Measured 2026-09-07** on branch `factory-wave-b` at the pushed commit
`40f3eb87f`: `cargo check --all-targets` on the seven crates FAILED, as did
`cargo test -p fabro-acp`, `cargo test -p fabro-workflow --lib`, and
`clippy -D warnings`. Only `fmt` and `fabro-types` passed.

What makes this worth recording is that the commit message's own validation
claim — "fabro-acp lib tests green (13), the workflow tests for js4t57 green" —
**was true**. The lib target compiled and its tests passed. The integration
test target and the workflow crate did not. So an author who runs
`cargo test -p <crate>` and reads a green lib line has evidence that is
accurate, specific, and insufficient, with nothing in the output announcing the
gap. `--all-targets` is the discriminator, and it is exactly the flag a
targeted test run omits.

### The four defects

| # | Site | Defect | Runtime meaning |
|---|---|---|---|
| 1 | `fabro-acp/src/session.rs`, permission-timeout drain | `MutexGuard` held across `terminate().await` | Real: made `run_acp_turn` `!Send` |
| 2 | `fabro-workflow/.../handler/llm/acp.rs:1796,1804` | `AttrValue::from("ask")` — no such impl | Compile-only (test code) |
| 3 | `fabro-workflow/.../pipeline/initialize.rs:1436` | `InitOptions` literal missing two fields | Compile-only (test code) |
| 4 | `fabro-workflow/.../handler/llm/acp.rs:701` | unnested or-pattern under `-D warnings` | Lint-only |

Defect 1 is the one with teeth, and its mechanism is worth carrying forward
because it is invisible at the call site. The code read:

```rust
if let Some((id, title)) = permission_timeout.lock().expect(...).take() {
    state.terminate().await?;
    ...
}
```

In **edition 2021** an `if let` scrutinee's temporaries live for the whole
construct, so the guard spans the `await` and the future stops being `Send`.
The cascade is what makes it hard to read back to its cause: the error surfaces
at `tests/session.rs:422` (`tokio::spawn` needs `Send`) and again at
`handler/llm/acp.rs:627`, neither of which is the offending line. Clippy names
it directly — "this `MutexGuard` is held across an await point" — which is the
cheapest instrument for the whole class. The fix is to bind the `.take()` to a
local before the `if let`.

Note the near-miss for a successor: **edition 2024 changed this rule.** The
same code in a 2024-edition crate drops the guard before the body and compiles.
So "this pattern is fine, I have written it before" is a genuinely true
statement that is false here.

## 2. Two review legs, one mutable worktree — the independence was fictional

Both adversarial review legs for fork PR `thewoolleyman/fabro#5` were pointed at
the SAME worktree, `~/.worktrees/fabro/factory-wave-b`, and BOTH were told to
run mutation checks. That brief is defective and the defect is this session's.

**Measured — and note the attribution correction, which is itself the point.**
This session first recorded these three mutations as the Codex leg's, because
they were observed in the tree in the minute after Codex exited while the
Claude leg was still running. The Claude leg then stated they were ITS OWN,
still in flight, and identified a different artifact as Codex's: an added test
`reviewer_duplicate_permission_option_labels_collapse_to_first_option`, present
before Claude made any edit and reverted by Codex before Claude finished. The
correction matters more than the original claim: **a shared mutable worktree
destroys attribution as well as independence**, and the observer could not tell
whose edit was whose from the tree alone. The three mutations were:

| File | Function | Mutation |
|---|---|---|
| `fabro-acp/src/session.rs` | `trim_to_head` | early `return` |
| `fabro-workflow/.../handler/llm/acp.rs` | `permission_answer_from` | `Timeout => Cancelled` instead of `TimedOut` |
| `fabro-workflow/.../pipeline/initialize.rs` | `refused_pre_run_push` | early `return None` |

Both legs were live against that one tree. `HEAD` was never touched —
`git status --short` showed working-tree modifications only, and the pushed
commit stayed clean — but each leg was, for some window, reading or compiling
source the other had altered.

**The coupling was real and it was measured, in the direction opposite to the
one first suspected.** The Claude leg's first baseline run reported
`permission_question_and_answer_mapping_are_bounded_and_exact` as FAILED, 12
passed and 1 failed, contradicting the branch's own 13-passed claim. Re-run on
verified-clean source it PASSES. The failing assertion was on
`select_permission_outcome`, which this branch does not touch — consistent with
a foreign mutation on disk during that compile, alongside an observed
`Blocking waiting for file lock on build directory`. The leg withdrew the
result rather than filing it. Had it not re-checked, this thread would now hold
a filed defect against code the branch never modified.

**Why this is worse than an ordinary race.** A mutation reads as ordinary
source. A test failing against a mutant is indistinguishable from a test
failing against a real defect. So neither leg could have announced the problem,
and the coupling would have surfaced only as two reviewers "agreeing" — which is
the shape the protocol exists to rule out.

**The sharpest instance.** Mutation M3 rewrote precisely the line whose
behaviour one of the findings disputes: whether a permission deadline is
deterministic. A reader opening that file inside the window would have seen
`Timeout => Cancelled` and concluded the branch behaves as the finding claims.
It does not; `HEAD` maps `Timeout => TimedOut`. The mutation would have
manufactured corroboration for a finding about the mutated line — and because
attribution was already lost, there would have been no way to tell that the
corroborating evidence was another reviewer's probe.

This is the multi-party form of the trap already catalogued in `AGENTS.md`
§"Verification discipline" Rule 4 — concurrence is not independence when the
method is shared — one level worse, because here the legs shared a mutable
**subject**, not merely a method.

**Containment.** The Claude leg was messaged mid-run with the three sites, told
not to report them as findings, and asked to state explicitly whether any
finding or test run of its own could have been taken against mutated source and
to re-verify any that could. It restored the tree to `HEAD` before finishing.

**The rule.** Give each adversarial review leg its own worktree, or forbid
mutation checks in a shared one. A reviewer that mutates source is doing exactly
what it was asked to do; the defect is in the brief, not in the reviewer.

## 3. A second silent-failure instrument, in the review harness itself

The Codex leg was invoked twice before it produced anything, and **both failed
invocations exited 0**:

- `-m gpt-5.5` → `404 Not Found: The model 'gpt-5.5' does not exist or you do
  not have access to it`.
- `-m gpt-5.6-sol` (the value in `~/.codex/config.toml`) → `Selected model is at
  capacity. Please try a different model.`

Only `-m gpt-5.6-terra` ran. A caller that checks exit status alone records two
completed review legs that never reviewed anything — the missing-leg
degradation that `AGENTS.md` §"Vet an escalation" already warns about, arriving
here through a different door. **Check that the output contains a verdict, not
that the process exited 0.**

## 4. What is still open after this note

- Fork PR `thewoolleyman/fabro#5` is open at `e3f25d2da` with the full chain
  green; review findings are being applied before it merges.
- After merge: rebuild, re-pin vps retaining `fabro.9081419-pre-wave-b.bak`,
  rebuild the orchestrator image, land the runbook rows with the merge sha, run
  the three Wave B live controls, and accept `.4`, `.6` and `bd-ib-js4t57`.
- The hp re-pin remains a maintainer call. hp held two live foreign runs at
  05:15Z on 2026-09-07 and a unit restart kills them; the binary is staged there
  as `/home/cwoolley/.fabro/bin/fabro.new` and hp still reports
  `fabro 0.254.0 (8de6611 2026-08-16)`.
