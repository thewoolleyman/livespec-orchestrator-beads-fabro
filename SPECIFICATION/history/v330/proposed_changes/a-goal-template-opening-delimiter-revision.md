---
proposal: a-goal-template-opening-delimiter.md
decision: modify
revised_at: 2026-11-09T05:54:26Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified and accepted under delegated decision mode, in the v330 slot legacy-coordinator-agent assigned. Both proposals carry work item bd-ib-cfgtlo. On 2026-11-08 bd-ib-ev3pbz and bd-ib-s754le each spent about 5.5 minutes of drive before goal-minijinja-preflight refused a literal opener, and repair comments then poisoned both for good, because the preflight read append-only ledger comments. The intent is kept whole: a ledger comment can no longer strand an item, and a field opener is caught at filing and at approve and refused permanently with exit 5. An accept-as-written cut passed an independent review. The pre-merge doctor LLM pass then found that two MUSTs of the proposal contradict unchanged text. First, refusing on a lesson opener breaks the fail-open rule of the Dispatch-brief lessons injection section. Second, comment_safe_external_text strips its input and truncates it at 1000 characters as well as rewriting openers, so routing every rider through it breaks the human answer route's verbatim rule. Both were verified against the code. That cut was never pushed; it is kept at refs/backup/spec/revise-v330-accept-abandoned-20261109 in the primary clone. The modifications are listed below. No design record is contradicted. A fresh independent sonnet review returned NO BLOCKERS on these exact bytes. Its nits are left for a later pass: three long cross-reference lines, Scenario 333 not exercising a comment-composed brief block separately, and the retained 'comment-poisoned' label. The heading-coverage TODO rows for Scenarios 333 and 334 and their debt-register entries are owned by bd-ib-cfgtlo.

## Modifications

1. Ledger comments, every brief block composed from ledger comments, and the injected lessons pass through an opener-only rewrite instead of comment_safe_external_text. The rewrite turns {{, {% and {# into [[, [% and [#, and does not strip, truncate, bound or escape anything else. Lessons are no longer a refusal cause, so lessons injection stays fail-open. Only the item's title, description, acceptance criteria and notes can refuse. 2. The outcome detail, drive's summary and the REFUSED: line name each offending field with the 0-based character offset of its first delimiter. None of them may quote the delimiter, because a fleet launcher copies the REFUSED: line into a ledger comment. The filing finding's offset is defined the same way. 3. The exit-5 cause is scoped to a hand-picked --item dispatch, and a drain's own exit code is unchanged by this rule. 4. The human answer route's rationale bullet no longer says an admitted opener would cost the item its dispatchability. 5. Scenario 333 also covers a non-record instruction comment longer than 1000 characters, which is rendered whole with only its openers rewritten, and a lesson opener. Scenario 334's Given excludes other mechanical findings and asserts that the finding comment carries no opener. Scenario 321 asserts the offset and that no delimiter appears in the summary or the REFUSED: line.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T05:53:23Z
verdict: NO BLOCKERS
proposal_stem: a-goal-template-opening-delimiter
content_digest: 09aa49b66cc6aceaf9e6029e98693835f976b2bfd99cb20f2baa8909a695f8f2
