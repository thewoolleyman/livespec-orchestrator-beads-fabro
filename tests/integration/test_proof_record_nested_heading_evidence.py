"""The nested-heading record shape, read by the real acceptance evidence leg.

The synthetic reader coverage lives in
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_proof_record.py`;
what it cannot do is prove the repair reaches the surface the post-merge
acceptance pass actually grades on. `read_proof_leg` is that surface — it issues
the comments read, parses the records, resolves attribution and projects one
`AssertionEvidence` per assertion — and the defect this module pins was measured
THERE, as an item parked on NEEDS_ATTENTION while a correctly attributed verified
record sat on its pull request.

THE DEFECT, AS MEASURED. Measured on released 0.170.0 against the published body
of `thewoolleyman/livespec-overseer` PR #2341 comment 5976999030, whose `##
Assertion 1` section states the assertion, introduces its replay under a nested
`### Replay proof` heading, and closes with `Reproduced: yes` at the end of that
same subtree: `ProofRecord.reproduced` returned `None`, and returned `True` once
the nested heading marker was removed from the body and nothing else changed.
`_sections` split at every prose heading, so the verdict was detached from the
section carrying the assertion text and the assertion graded as unevidenced.

THE FIXTURE IS A REPRESENTATIVE RECORD, NOT THAT PUBLISHED ONE, for a reason this
module should state rather than leave to be guessed. That record belongs to
another repository's pull request; a test reading it would either fetch from the
forge — which the sibling payload module records as the thing that stops a test
being a test of this repository — or vendor one tenant's comment into another's
suite. The shape is what the defect turns on, so the fixture reproduces the shape
and is immutable text committed here.

THE CONTROLS ARE WHAT MAKE THE PASSING ASSERTION WORTH ANYTHING, and the record
carries both directions on purpose. A reader answering `True` for whatever it is
handed would satisfy a one-assertion fixture, so the record wraps its assertions
in a record-wide `#` title — the widening's fail-OPEN direction — and publishes a
verdict for only two of its three assertions: the unverdicted one must still be
reported through `unevidenced` rather than borrow its sibling's `yes` or the
trailing `## Summary`'s run-wide statement, and the refused one must still grade
as a FAILING check rather than as no evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attribution import (
    MergingDispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import read_proof_leg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import VERDICT_VERIFIED

_RUN_ID = "01M467EWE4PS0EQH6SKZWXNA7F"
_PR_NUMBER = 2599
_RECORD_URL = (
    "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2599"
    "#issuecomment-5977000000"
)
_REPRODUCED_ASSERTION = (
    "The proof reader grades an assertion from its own reproduced verdict when that"
    " verdict is beneath nested prose headings inside the assertion section."
)
_UNVERDICTED_ASSERTION = (
    "A missing assertion verdict remains unevidenced when only a sibling assertion or a"
    " sibling summary section carries a reproduced verdict."
)
_REFUSED_ASSERTION = (
    "Heading-like proof output inside fenced code preserves assertion boundaries and the"
    " existing fence-aware evidence behavior."
)
_ASSERTIONS = (_REPRODUCED_ASSERTION, _UNVERDICTED_ASSERTION, _REFUSED_ASSERTION)

# One verified record in the shape the defect turns on: a record-wide `#` title,
# one `##` section per assertion, a nested `###` replay subsection per section, and
# each verdict at the END of its own subtree. Written as text rather than assembled
# from the assertions above so the published bytes are what the reader is handed.
_RECORD_BODY = f"""Proof of Done — verified — run {_RUN_ID} — 2026-10-05T14:30:00Z

# Proof of Done record

## Assertion 1 — {_REPRODUCED_ASSERTION}

Proof mode: `factory_captured`

### Replay proof

```text
$ uv run pytest -q -k nested_heading
# the runner's own comment, printed by `cat`
### 3. the executed target list
1 passed
```

Reproduced: yes. The replay matches the capture byte-for-byte.

## Assertion 2 — {_UNVERDICTED_ASSERTION}

Proof mode: `factory_captured`

### Replay proof

```text
$ uv run pytest -q -k borrows
# this subsection publishes no verdict of its own
```

## Assertion 3 — {_REFUSED_ASSERTION}

Proof mode: `factory_captured`

### Replay proof

```text
$ uv run pytest -q -k fenced
# no boundary survived the printed heading
```

Reproduced: NO. Step 2 printed nothing.

## Summary

Reproduced: yes. Every assertion replayed.
"""


@dataclass(kw_only=True)
class _CommentsRunner:
    """The pass's command seam, answering the comments read with the record."""

    stdout: str
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _payload() -> str:
    return json.dumps({"comments": [{"body": _RECORD_BODY, "url": _RECORD_URL}]})


def test_the_acceptance_proof_leg_grades_a_nested_verdict_and_parks_the_rest(
    tmp_path: Path,
) -> None:
    """One pass over one record: the recovery, and both directions it must not buy."""
    runner = _CommentsRunner(stdout=_payload())

    leg = read_proof_leg(
        repo=tmp_path,
        criteria=EffectiveCriteria(
            text="\n".join(f"- {one}" for one in _ASSERTIONS),
            source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
            assertions=_ASSERTIONS,
            proof_modes=(PROOF_MODE_FACTORY_CAPTURED,) * len(_ASSERTIONS),
        ),
        outcome=DispatchOutcome(
            work_item_id="bd-ib-yj6ij4",
            status="green",
            stage="done",
            pr_number=_PR_NUMBER,
            merge_sha="0000000",
            detail="merged",
            fabro_run_id=_RUN_ID,
        ),
        runner=runner,
        dispatch=MergingDispatch(fabro_run_id=_RUN_ID, dispatch_id=None),
    )

    assert runner.argvs == [["gh", "pr", "view", str(_PR_NUMBER), "--json", "comments"]]
    assert leg.record is not None
    assert leg.record.verdict == VERDICT_VERIFIED
    assert leg.record.url == _RECORD_URL
    assert [one.text for one in leg.assertions] == list(_ASSERTIONS)
    assert [one.check is not None for one in leg.assertions] == [True, False, True]
    assert [one.passed for one in leg.checks] == [True, False]
    assert leg.unevidenced == (_UNVERDICTED_ASSERTION,)
