# Forge comment ceiling measurement (2026-10-07)

Work-item: `bd-ib-555xcd` (a proof record is bounded and refused before posting
when it would exceed the forge comment ceiling). Plan epic: `bd-ib-7sjdzv`,
requirement carriers R2 and R7.

## What had to be measured, and why it could not be assumed

`bd-ib-555xcd` was raised after the `overseer-herdr-rewrite` session reported a
"65536-character publication limit" while posting a proof record. That session's
own handoff then corrected the report: the limit was an **assumption**, the forge
accepted a 66,680-character record, and no record was lost.

So the item's brief makes the measurement the implementer's first task, in these
words:

> First task of the implementer: measure the real ceiling against the forge
> (characters versus bytes, issue comments versus review comments) and record it
> in the repository rather than assuming 65536.

That instruction is load-bearing rather than procedural. A budget derived from an
assumed ceiling is a budget that refuses records the forge would have accepted,
or admits records it will reject — and either way the refusal names a number
nobody measured.

## Method

Measured against live GitHub on 2026-10-07 from inside the dispatched Fabro
sandbox, against this repository's own already-merged pull request **2646**,
under the run's `GITHUB_TOKEN` (the `thewoolleyman-factory-bot[bot]` installation
token).

Every probe posted a body of a known size, read back the stored body, and
**deleted the comment it created**. The post-measurement control confirms the
cleanup: PR 2646 finished with `0` issue comments and `0` review comments, and
`0` comments matching the probe's all-`x` signature on either surface. No
release, asset, issue or branch was created, and no other repository was touched.

An over-ceiling body is rejected **before anything is created**, so the
rejection arm costs nothing and leaves nothing behind.

## The headline finding: the enforced ceiling is 262,144 BYTES, not 65,536 characters

| # | Probe (issue comment, `POST /repos/.../issues/2646/comments`) | chars | UTF-8 bytes | Measured |
|---|---|---|---|---|
| A | `'x' * 200000` | 200,000 | 200,000 | **ACCEPTED**, stored 200,000 chars intact |
| B | `'x' * 262144` | 262,144 | 262,144 | **ACCEPTED**, stored 262,144 |
| C | `'x' * 262145` | 262,145 | 262,145 | **REJECTED** (422) |
| D | `'x' * 524288` | 524,288 | 524,288 | **REJECTED** (422) |
| E | `'x' * 1000000` | 1,000,000 | 1,000,000 | **REJECTED** (422) |

Probe A is the one that falsifies the assumption outright: a body **more than
three times** the assumed 65,536 ceiling was accepted and stored byte-intact.
Probes B and C bracket the real boundary to a single character.

**The enforced issue-comment ceiling is exactly 262,144 = 256 KiB = 4 × 65,536,
inclusive.**

## The forge's own error message names a limit it does not enforce

This is the part a future reader is most likely to re-derive wrongly, because the
forge states the wrong answer authoritatively. The 422 payload from probe E reads,
verbatim:

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "resource": "IssueComment",
      "code": "unprocessable",
      "field": "data",
      "message": "Body is too long (maximum is 65536 characters)"
    }
  ],
  "status": "422"
}
```

That message is wrong in **both** of its claims. The number is 4× smaller than
what is enforced (probe B accepted 262,144), and the **unit** is wrong too (see
below: bytes, not characters). This is almost certainly where the original
65,536 assumption came from — it is what the forge says when it refuses.

A budget sized from that message would waste three quarters of the available
room, and an operator debugging a refusal would be told a ceiling that no probe
can reproduce.

## Bytes, not characters — and the discriminator that settles it

The character/byte question cannot be answered with ASCII, where the two are
equal: every probe above is consistent with either unit. The discriminator is a
body whose character count is far **under** any candidate ceiling while its byte
count is **over** one.

| # | Probe | chars | UTF-8 bytes | Measured |
|---|---|---|---|---|
| F | `'—' * 131072` (U+2014, 3 bytes each) | 131,072 | 393,216 | **REJECTED** |
| G | `'—' * 262144` | 262,144 | 786,432 | **REJECTED** |
| H | `'—' * 87381` | 87,381 | **262,143** | **ACCEPTED**, stored 87,381 chars / 262,143 bytes |
| I | `'—' * 87382` | 87,382 | **262,146** | **REJECTED** |

Probe F is decisive. 131,072 characters is half of the character ceiling probe B
established, and only twice the forge's own advertised 65,536 — yet it was
refused, because its 393,216 **bytes** exceed 262,144. Probe F also rules out
UTF-16 code units: an all-BMP body of 131,072 characters is 131,072 UTF-16 units,
comfortably under any candidate.

Probes H and I then re-bracket the boundary from the multibyte side and land on
the **same byte number** as B/C, one byte apart: 262,143 bytes accepted, 262,146
bytes refused.

**The ceiling is denominated in UTF-8 bytes.** A budget measured in `len(str)`
would therefore over-admit by up to 4× on non-ASCII proof, and proof output is
exactly where non-ASCII arrives — em dashes in rendered prose, box-drawing in
tables, tree glyphs in `tree`/`git log --graph` output, and this repository's own
ratified em-dash header separator.

## Issue comments versus review comments: a different, far higher ceiling

The brief asks for both surfaces, and they do **not** agree.

| # | Probe (review comment, `POST /repos/.../pulls/2646/comments`) | chars | Measured |
|---|---|---|---|
| J | positive control, `'x' * 10` at a real diff line | 10 | **ACCEPTED** |
| K | `'x' * 262144` | 262,144 | **ACCEPTED** |
| L | `'x' * 262145` | 262,145 | **ACCEPTED** |
| M | `'x' * 1000000` | 1,000,000 | **ACCEPTED** |
| N | `'x' * 2000000` | 2,000,000 | **ACCEPTED** |

Probe J is why this row set is trustworthy, and recording it matters more than
the result. The **first** attempt at this surface aimed at `pyproject.toml` line
1, which is not in PR 2646's diff, and every size — including a 10-character
control — came back 422. Read without a control, those rejections looked exactly
like a body-size ceiling *lower* than the issue-comment one, which is the
opposite of the truth. The error payload named the real cause,
`pull_request_review_thread.line: could not be resolved`; re-aiming at line 67,
which the diff actually touches, turned the control green and let the body sizes
be measured at all.

That is the catalogued "instrument that cannot return a hit, reporting no hits"
trap (`AGENTS.md`), and it fired here on the first try.

**Review comments accept at least 2,000,000 characters.** They are therefore not
the binding surface — but they are also **not where records go**, and that is the
operative point rather than the generosity: a review comment must be anchored to
a line of the diff, and a Proof of Done record is a statement about the whole
change. `gh pr comment`, which every record publisher uses, posts an **issue**
comment. So 262,144 bytes is the ceiling that binds, and the review-comment
figure must not be mistaken for headroom this design can spend.

## What this measurement did NOT establish

Stated explicitly, because a later reader will otherwise assume it did.

**The beads/Dolt ledger comment ceiling is unmeasured.** The plan record command
(`_plan_record_post`) does not post to the forge at all — it appends to the plan
epic through `client.add_comment`, i.e. into the beads tenant on the shared
Dolt server. That store has its own column limit, and nothing here measured it;
the tenant password is not present in this sandbox, so it could not be. If that
column is a MySQL `TEXT` it would be **65,535 bytes** — *below* the budget
declared from the forge figure — which would make the forge-derived budget the
wrong instrument for that one publisher.

This is why the budget is declared as a single named constant with the ceiling it
was derived from recorded beside it: narrowing it for the ledger path later is a
one-line change to a named value, not a hunt through four publishers. Whoever
next has tenant credentials should measure the ledger comment ceiling and, if it
is lower, declare it as its own ceiling for the plan path.

**No CDN, UI or notification-email limit was measured.** The probes exercised the
REST API, which is the path every publisher takes. A body the API accepts could
in principle render poorly in the web UI or be truncated in a notification email;
that is a presentation question, not a lost-proof question, and this item is
about the latter.

**The ceiling was measured once, on one repository, on one day.** It is a
server-side validation an upstream change could move. The budget below it exists
partly so that a modest downward move does not immediately start losing proofs.

## What the implementation does with these numbers

- `FORGE_COMMENT_CEILING_BYTES = 262144` — the measured, enforced ceiling, in
  UTF-8 bytes, carrying this file as its provenance.
- `PROOF_RECORD_BUDGET_BYTES` — the declared budget, strictly **below** the
  ceiling, so a record that passes the budget check has headroom against both a
  future downward move and any per-publisher overhead the measurement did not
  see.
- `INLINE_PROOF_ALLOWANCE_BYTES` — the per-assertion inline allowance, declared
  separately so a capture agent can plan a bounded proof recipe **before** it
  runs, rather than discovering at post time that its evidence does not fit.

Every measurement is in UTF-8 bytes, never characters, for the reason probe F
establishes.
