# Interrupted review source recovery

Measured on 2026-10-09. This receipt preserves factory-produced source;
it is not a Green receipt or the plan's released Proof of Done. The five
plan assertions, their carriers, and all child acceptance bullets remain
unchanged.

## Race review identified additional destructive boundaries

The first resumed `bd-ib-gh5xwq` run,
`01M4GJ78GW7X4W92RMH40K32VK`, published the first accepted review fix as
`2228e881da3af242b938e868f7375316ca21cee3` on PR 2714. That fix rechecked
the journal after export and ledger read-back. The next independent review
identified further race windows: a questions lookup can take long enough
for a new journal stamp to appear, and failed answer/cancel operations can
lead to fallback destructive operations after a new stamp.

Seven controlled probes discriminate these boundaries: inventory, a genuinely
older run, export, questions without Abandon, questions with Abandon,
failed-answer fallback, and failed-cancel fallback. The published first fix
passed the first three and failed all four later-boundary controls. The
force-remove instrument was checked against the actual `rm -f RUN_ID`
argument position. Thus the new controls actually detect the regression.

The second `review_fix` accepted that finding and produced a test-only Red
plus staged Green source. Its ACP turn then timed out after 32 tool calls
and 2167 updates. The subsequent engine checkpoint commit also failed.
The run concluded with `git checkpoint commit failed for node 'review_fix'`;
the latest persisted workflow checkpoint still named the earlier published
commit and could not describe the unfinished source.

## Exact source and original Red provenance survived

A read-only copy from stopped sandbox
`7c2953add5d59033838b89e5f7fff87c3895c03be014dde91c05faa9fa16a15e`
on the actual hp factory retained source and the complete Git directory.
Regenerable caches were excluded. Every one of the 2913 tracked paths was
present in the extracted copy. The private archive has 3687 members,
42,264,392 bytes, and SHA256
`32b157acb3ef4d6c3f9d8bbb5f97f3f2137c3337dc6b9292f4bf2b810cb8c62e`.
Its parent directory is mode 0700; the archive is mode 0600. Raw run logs
and private sandbox exports are not published here.

The actual HEAD is the open Red commit
`947fdfa5c985e98d3354ddd60541155ae6d6b0fa`. It has no Green trailers.
Original producer attribution is `Claude Fable 5`, with Factory-Run-Id
`672bcce5efda4122a6b364e226b4a94f`. The Red receipt names
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_reconcile_supersession.py`,
whose unchanged bytes were independently checked against its recorded SHA256
`62e9c98dcc9f827b55414272a0da426fd32409e703a1828cfb382f71f5f6600b`.
The original Red output digest is
`5f1d875c66faa3fe2582e7aee7e5701b445273101595cee926b0e1fa32f6680e`,
captured at 15:46:28 UTC.

The sibling artifact `006-interrupted-review-green.patch` is the exact
6874-byte `git diff --cached --binary` from that HEAD. Its SHA256 is
`982ba4514340453671a21ef1dbbfb533e6b71107075f26a7ba428cc5a6c2ce89`.
There was no unstaged diff. It changes only two reconciler modules and their
termination helper tests; it does not alter the recorded Red test file.
All seven probes pass on this recovered staged source. That observation
does not establish that the interrupted Green hook passed.

The recovery publication preserves these original Git objects under
`refs/livespec/preserved-run/bd-ib-gh5xwq/<full-object-sha>`:

- `947fdfa5c985e98d3354ddd60541155ae6d6b0fa`: refreshed open Red.
- `5cb1252c91c64061ea15529b0f680c2cea9ec8fc`: preceding original Red.
- `3fd03de0bbfcf8a41c05bc24dfc63c766abcb310`: Red object referenced by the first fix's Green receipt.
- `2228e881da3af242b938e868f7375316ca21cee3`: first published review fix.

The next ordinary Dispatcher resume must adopt the preserved Red and patch,
retain original producer attribution, finish the normal Green amend and
hooks, and obtain fresh publication, proof, review, merge and acceptance.
The planning session has not implemented or amended this child inline.
The ledger recovery rider records publication read-back and the exact
factory continuation instructions.

## Credential proof classification was corrected without changing scope

The first resumed `bd-ib-656k7i` run reached proof verification on PR 2713
head `148b7c4473ab8f7e83be28ca97c8ba13be88f860`. Its verifier refused
pytest-only evidence for all three assertions. This item explicitly delivers
tests, and each assertion's subject is a test harness or regression test.
The governing Effective acceptance criteria and Scenario 137 permit this
shape; the proof-capture and review prompts expressly permit suite evidence
when a test, check or gate is itself the assertion's subject.

A read-back ledger rider named that existing exception without changing
assertions, steps, policy, counters or proof grades. A second ordinary
Dispatcher resume started run `01M4GPGFK9N7892S3DPZ0E4KXM`. It must obtain
its own independent review and exact replay. A policy clarification is not
a substitute for that replay or for normal merge and acceptance.
