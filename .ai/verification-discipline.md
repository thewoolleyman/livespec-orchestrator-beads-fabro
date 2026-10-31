# Verification discipline: the five rules in full

Moved word for word from `AGENTS.md` §"Verification discipline (repo-additive)" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## Verification discipline (repo-additive)

Five rules. Rules 1-3 come from a 2026-07-28 three-way exchange between the
`dispatch-claim-liveness`, `console-happy-path-mvp` and `factory-hardening`
tracks, in which **three sessions independently reached confident wrong answers
on the same question in one day**; rules 4-5 were added 2026-08-27 by the
`homelab-loop-hardening-orchestrator` thread, each from a near-miss caught by a
control rather than by care. Each bad method produced a **confident wrong
answer rather than an obviously empty one**, which is why none self-announced.
Full account, with every measurement:
`plan/archive/dispatch-claim-liveness/handoff.md` §"THE THREE STANDING RULES".

Provenance, because a rule with a visible author is harder to dismiss:
`console-happy-path-mvp-supervisor` authored Rule 1's form and Rule 3's example;
`factory-hardening-supervisor` contributed Rule 2's sharper variant and caught
the third near-miss.

1. **Asserting an absence requires stating the scope searched.** "No call site",
   "no release", "no occurrence" — say what population you searched, and make it
   the whole workspace unless there is a reason it cannot be. If the check could
   not have returned the other answer, it is not evidence.
   *Worked example:* "no released build carries this fix" came from sampling two
   plugin caches that were **created before the fix commit existed**, so their
   lacking it was guaranteed and carried zero information. When the question is
   "was this released", ask `git tag --contains <sha>`.

2. **Verify the absence of the RIGHT token — a count is not a behavior test.**
   Pick a token that *cannot appear unless the behavior is there*, and say which
   token you chose and why.
   *Worked example:* a fork's `pr.md` was judged to lack a rebase-before-push fix
   because it contained 2 `rebase` mentions against our 6. **Both of its 2 were
   innocent** — a title, and a `gh pr merge --rebase --auto` arm — so six
   mentions in auto-merge context would have reported the fix PRESENT. The
   discriminating token was `fetch`: ours 2, theirs 0. **The count was
   directionally right and still not evidence.**
   - *Corollary — prefer a PROVENANCE question to any content probe.* Before
     grepping a file's contents for a fix, ask whether it *could* contain it:
     that same fork's `pr.md` had exactly ONE commit in its history, 18 days
     older than the fix. `git log -- <file>` has no wrong-answer failure mode.
   - *Corollary — read the spec clause a check implements before calling it
     defective* (coordinator ruling R187, 2026-10-28). A measured behaviour
     that looks wrong may be exactly what the ratified spec mandates.
     *Worked example:* console's `check-fork-drift` exited 0 on a fork 23
     orchestrator releases stale. That was ruled a defect, and a
     Definition-of-Done assertion demanding a failure was added to the
     re-sync item. The launch-time preflight refused the assertion, because
     console's `### Workflow-Fork Drift Gate` contract and Scenario K say a
     newer install "MUST NOT fail" the check. The gap was in the spec, so it
     went to the maintainer as a spec-change-tier item
     (`livespec-console-beads-fabro-gk7yhj`) instead of a factory assertion.
   - *Corollary — search for a literal COPIED from the artifact*, never one
     reconstructed from memory. Four probes failed this way in one session
     (missing backticks; a line break inside a code block; another repo's
     invocation syntax; a `| head` that truncated the hits). **A verification
     that can only fail silently is not a verification.**
   - *Corollary — never list environment variable NAMES with a line-oriented
     filter when secrets may be present.* `env | cut -d= -f1` printed the
     continuation lines of a multi-line PEM private key whole into a session
     transcript on 2026-10-01, because those lines carry no `=` and newline
     framing cannot tell a value's own line breaks from record boundaries.
     Only NUL framing can: use `printenv NAME | wc -c` per name, or
     `env -0` split on the NUL byte and keep the part before the first `=`.
     The same trap defeats `grep`/`cut` over `keyctl pipe`, a bare `printenv`,
     and any `.env` dump.

3. **An instruction can outlive the condition that made it correct.** The danger
   is not writing something false — it is writing something **true that stops
   being true while still reading as authoritative**, in the section a successor
   trusts *instead of* checking. A "do not re-derive this" list is the
   highest-risk place in any document for exactly that reason: date such entries
   and re-verify before quoting one.
   *Worked example:* "expect the stale-base refusal, apply the known recovery"
   was true while a worker ran a week-old plugin and false the moment it
   restarted — and it reached a merged handoff either way.

4. **Concurrence is not independence when the method is shared.** Two parties
   applying the same method to the same artifact produce **one** measurement, not
   two. Their agreement shows the method is DETERMINISTIC, not that the answer is
   right — and it is *more* persuasive than a single wrong answer, because the
   receiving party sees N reports and cannot see they share one origin. This is
   the multi-party form of Rule 2's problem; Rule 2 asks whether your instrument
   is pointed correctly, this one asks whether the second opinion is a second
   instrument.
   *Worked example (2026-08-27):* two sessions independently measured a tenant's
   spec-commitment census by reading the projection's bridged
   `spec_commitment_hint` while reasoning about a guard that reads the
   beads-native `spec_id` column, and the concurrence was relayed onward as
   corroboration. It was one reading taken twice. Re-taken against **both**
   fields it happened to hold — but a divergence could not have printed under the
   original method.
   *The larger instance, same day:* a coordinator PRESCRIBED one reading method
   to four peers and read their agreement as fourfold confirmation. Two defects
   existed in the prescription, and both were caught only because two peers
   **departed** from the brief. Compliance would have banked three greens on a
   holed method.
   - *Corollary for anyone standardising a method:* a departure from your brief
     is **signal**, not noise to be corrected back into line. It is the only
     thing that can falsify the brief itself.
   - *What a genuine second reading looks like:* a different artifact, not the
     same one read again. Another tenant found a free-form value that the first
     tenant's data structurally could not contain — that is corroboration in the
     sense the shared-method census was not.
   - *Why a SECOND PARTY is load-bearing, and what cannot replace it (2026-09-12,
     this repo, plan `bd-ib-uy4lp7`):* an instrument failure is invisible to its
     OWN author for the same structural reason the other party's is invisible to
     them — each returns a clean, plausible answer **at exit 0**. Three of the
     implementing session's claims failed that way in one thread: a
     `/proc/<pid>/environ` scan for `CLAUDE_PLUGIN_ROOT` that could not hit for
     ANY process, including the scanning session's own; a "no resolution-source
     field" discriminator naming a field NO dispatch writes, which as stated
     would have disqualified the two canaries the same item counted; and a
     "residual VERIFIED DISCHARGED" proved on a green run that structurally
     cannot enter the fail-fast branch it was meant to test. TWO were caught by
     the independent reviewer; one by a control the session happened to run.
     The reviewer's own first probe failed identically from the opposite
     direction — a `grep -rl` by run id across sibling trees returning a clean
     zero that WOULD HAVE FALSIFIED a requirement — and it disclosed that rather
     than letting the zero stand. So the asymmetry is the point, not the credit:
     a single agent running both roles banks the same greens twice. Reviewing
     your own work harder is not a substitute for a party whose blind spots are
     not yours.

5. **A next-action line EXECUTES — author it from evidence, not from status.**
   Under an unattended resume (`LIVESPEC_PLAN_UNATTENDED`), `resume_directive`
   returns `ask: False` whenever the newest plan handoff names exactly one next
   action, and the session **takes it directly** — no picker, no human. A
   next-action line is therefore not advice to a successor; it is an instruction
   that fires.
   *Worked example (2026-08-27, this repo, caught before dispatch):* a handoff
   named "Dispatch `bd-ib-6mnyq4`", authored from the item's STATUS — `ready`,
   already admitted, no dependency edge, factory idle. The item carried a binding
   rider, "DISPATCH HELD, DELIBERATELY, PENDING `bd-ib-u7nrue`", whose release
   condition was that sibling's PR merging; it had not merged. Both items insert
   into the same pre-dispatch sequence in `_dispatcher_run_checks.py`, which is
   why the hold exists. The directive resolved `ask: False`, so an unattended
   resume would have dispatched straight into the collision the rider was written
   to prevent.
   **Before writing any item id into a next-action line, run
   `bd comments <id> --json` and read it.** Status is not evidence that an item is
   dispatchable: riders arrive AFTER filing, they are binding scope, and neither
   the description nor `acceptance_criteria` announces that any exist — this is
   the "read its comments" rule above, promoted from a pre-implementation check to
   a pre-*authoring* one, because the automatic path reaches dispatch without a
   human ever re-reading the item.

**Run these on your own work, not only on other people's.** Every instance above
was caught by a second signal disagreeing, never by the check announcing itself.
Passing a check you never ran is luck, not method.
