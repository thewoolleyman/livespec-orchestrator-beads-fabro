"""The plan posting primitive: the one route a plan Proof of Done record takes.

Binds the second assertion of `bd-ib-wbdgil` and the plan-record clause of
`SPECIFICATION/contracts.md` (v115): one posting primitive renders plan records
"so that no session hand-formats one", it computes the publishing identity
itself, and it "MUST refuse a `verified` post whose computed identity equals that
of the `captured` record it replays".

WHY THE PUBLISHED BYTES ARE READ BACK THROUGH THE ARCHIVE GATE'S OWN READER AND
NOT MATCHED AS TEXT. "In the ratified structure" is a claim about what the
consumer can do with the record, and the consumer is `_plan_proof_record` plus
`_plan_proof_leg`. A containment check on the header would pass for a body whose
per-assertion sections the gate reads as unevidenced — the exact failure measured
on two correctly published item records in 2026-10-04, where every assertion read
as unobserved because of a section-splitting defect nothing in the record's own
text revealed. So the assertion is that the gate's reader recovers the verdict,
the identity and the per-assertion reproduction verdict from the bytes the
primitive appended.

WHY THE SELF-VERIFIED REFUSAL IS PAIRED WITH AN INDEPENDENT REPLAY THAT SUCCEEDS.
A primitive that refused EVERY replay would satisfy the refusal assertion on its
own, and would make the ratified remedy — have a different party replay —
unreachable. The two posts differ in nothing but the session identity in the
environment, which is the one input the clause makes the refusal turn on.

WHY THE REFUSAL IS READ OFF THE LEDGER AND NOT OFF THE EXIT CODE. A record
comment must not be edited after posting, so a refusal that fired after the
append would leave a not-evidence record permanently on the epic. "Nothing was
published" is therefore asserted as the comment count, which an exit code cannot
establish.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    PROOF_RECORD_BUDGET_BYTES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    latest_plan_proof_entry,
    plan_proof_entries,
)
from livespec_orchestrator_beads_fabro.commands._plan_record_post import PLAN_RECORD_SURFACE
from livespec_orchestrator_beads_fabro.types import StoreConfig

_SLUG = "record-post-thread"
_ASSERTION = "The released build runs in a real operator session."
_CAPTURING = "capturing-session"
_REPLAYING = "replaying-session"
_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


class _NeverRuns:
    """A runner that fails loudly: a session identity must never reach the forge.

    The clause's ordering is load-bearing — the agent session answers BEFORE the
    forge login, because on this fleet every session on a host shares one token and
    resolving a session's identity from the forge would give a capture and its
    replay the SAME identity.
    """

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        raise AssertionError(f"no command may run: {argv} in {cwd} ({timeout_seconds}s)")


def _payload(*, path: Path, reproduced: bool | None) -> Path:
    document: dict[str, object] = {
        "build": {"release_tag": "v0.167.0", "installed_build": "0.167.0"},
        "assertions": [
            {
                "text": _ASSERTION,
                "steps": ["Install the released build.", "Run it in an operator session."],
                "proof": "$ delivered --version\n0.167.0",
                "reproduced": reproduced,
            }
        ],
    }
    _ = path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _post(
    *, module: object, epic_id: str, verdict: str, record: Path, session: str, emitted: list[str]
) -> int:
    runner: CommandRunner = _NeverRuns()
    return module.run_post_plan_record_command(  # pyright: ignore[reportAttributeAccessIssue]
        post=module.PlanRecordPost(  # pyright: ignore[reportAttributeAccessIssue]
            repo=Path("/nonexistent-repository"),
            epic_id=epic_id,
            verdict=verdict,
            record_path=record,
        ),
        config=_config(),
        runner=runner,
        env={_SESSION_ENV: session},
        emit=emitted.append,
    )


def test_the_primitive_posts_a_capture_and_an_independent_replay_and_refuses_a_self_replay(
    tmp_path: Path,
) -> None:
    # The guard is a REAL instrument before anything relies on it: it fires when
    # called, so "no command ran during the three posts" is evidence rather than a
    # property of a stand-in that could never have complained.
    with pytest.raises(AssertionError):
        _ = _NeverRuns().run(argv=["gh"], cwd=tmp_path, timeout_seconds=1.0)
    module_path = (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_plan_record_post.py"
    )
    assert module_path.is_file()
    module = importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_record_post")
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug=_SLUG,
        title="Record post thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-05T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the released build has been run in a real session.",
            assertions=(_ASSERTION,),
        ),
    )
    epic_id = created["epic_id"]
    emitted: list[str] = []

    captured = _post(
        module=module,
        epic_id=epic_id,
        verdict=VERDICT_CAPTURED,
        record=_payload(path=tmp_path / "capture.json", reproduced=None),
        session=_CAPTURING,
        emitted=emitted,
    )

    assert captured == 0
    # The gate's OWN reader recovers the record, which is what "the ratified
    # structure" means: the header's verdict and computed identity, and the
    # per-assertion reproduction verdict read out of the body's own section.
    entries = plan_proof_entries(comments=_fake().list_comments(issue_id=epic_id))
    assert [(one.record.verdict, one.record.run_id) for one in entries] == [
        (VERDICT_CAPTURED, _CAPTURING)
    ]
    # A capture makes no claim about reproduction: it is the first leg and has
    # nothing yet to have reproduced, so the primitive drops the payload's field.
    assert entries[0].record.reproduced(assertion=_ASSERTION) is None

    self_replay = _post(
        module=module,
        epic_id=epic_id,
        verdict=VERDICT_VERIFIED,
        record=_payload(path=tmp_path / "replay.json", reproduced=True),
        session=_CAPTURING,
        emitted=emitted,
    )

    assert self_replay != 0
    # Nothing was appended: a refusal after the append would leave a record the
    # archive gate calls not-evidence permanently on the epic.
    assert len(_fake().list_comments(issue_id=epic_id)) == 1
    assert _CAPTURING in "".join(emitted)

    independent = _post(
        module=module,
        epic_id=epic_id,
        verdict=VERDICT_VERIFIED,
        record=_payload(path=tmp_path / "replay.json", reproduced=True),
        session=_REPLAYING,
        emitted=emitted,
    )

    assert independent == 0
    replay = latest_plan_proof_entry(
        entries=plan_proof_entries(comments=_fake().list_comments(issue_id=epic_id)),
        verdicts=(VERDICT_VERIFIED,),
    )
    assert replay is not None
    assert replay.record.run_id == _REPLAYING
    assert replay.record.reproduced(assertion=_ASSERTION) is True
    # The mode comes from the plan's own section, never from the payload, so a
    # record cannot declare a leg the maintainer did not.
    assert f"Proof mode: {PROOF_MODE_HOST_CAPTURED}" in replay.record.body


# ---------------------------------------------------------------------------
# bd-ib-555xcd: the plan record is measured against the SAME declared budget,
# and an over-budget record is refused rather than appended.
#
# WHY THIS SURFACE IS COVERED SEPARATELY RATHER THAN BY ANALOGY WITH THE ITEM
# ONE. A plan record does not go to the forge at all: it is appended to the
# epic through the ledger, so the forge ceiling the budget was measured
# against is not the limit this path will actually meet. Applying the budget
# here is the conservative reading — the ledger's own comment column is
# unmeasured — and the thing worth asserting is that the refusal reaches this
# publisher too, since nothing about the forge measurement implies it.
# ---------------------------------------------------------------------------

_PLAN_BULK_ASSERTIONS = tuple(
    f"The bounded plan record arm number {index} holds in a real session." for index in range(7)
)


def _bulk_payload(*, path: Path, proof_bytes: int) -> Path:
    document: dict[str, object] = {
        "build": {"release_tag": "v0.173.7", "installed_build": "0.173.7"},
        "assertions": [
            {
                "text": text,
                "steps": ["Install the released build.", "Run it in an operator session."],
                "proof": "p" * proof_bytes,
                "reproduced": None,
            }
            for text in _PLAN_BULK_ASSERTIONS
        ],
    }
    _ = path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _bulk_epic(*, tmp_path: Path) -> str:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="bounded-plan-record",
        title="Bounded plan record thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-07T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when every arm has been run in a real session.",
            assertions=_PLAN_BULK_ASSERTIONS,
        ),
    )
    return str(created["epic_id"])


def _post_bulk_plan(*, tmp_path: Path, proof_bytes: int) -> tuple[int, str, int]:
    """Drive one plan post and report its code, output, and the epic's comment count."""
    module = importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_record_post")
    reset_fake_singleton()
    epic_id = _bulk_epic(tmp_path=tmp_path)
    emitted: list[str] = []
    code = _post(
        module=module,
        epic_id=epic_id,
        verdict=VERDICT_CAPTURED,
        record=_bulk_payload(path=tmp_path / "bulk.json", proof_bytes=proof_bytes),
        session=_CAPTURING,
        emitted=emitted,
    )
    return code, "".join(emitted), len(_fake().list_comments(issue_id=epic_id))


def test_an_under_budget_plan_record_of_the_same_shape_still_appends(tmp_path: Path) -> None:
    """The control: this seven-assertion plan fixture CAN publish when it fits.

    Without it the refusal below is equally consistent with a budget doing its job
    and with a fixture that could never append, and the output of the two is
    identical. The pair differs only in the per-assertion proof size.
    """
    code, _, comments = _post_bulk_plan(tmp_path=tmp_path, proof_bytes=4096)

    assert code == 0
    assert comments == 1


def test_an_over_budget_plan_record_is_refused_and_never_appended(tmp_path: Path) -> None:
    """The refusal fires BEFORE the append, so the epic carries no oversize record.

    The comment COUNT is the assertion rather than the exit code, for the reason the
    rest of this module's refusals assert it: a plan record must not be edited after
    posting, so an append that happened before the refusal could not be taken back.
    """
    code, emitted, comments = _post_bulk_plan(tmp_path=tmp_path, proof_bytes=30000)

    assert code == 3
    assert comments == 0
    assert PLAN_RECORD_SURFACE in emitted
    assert str(PROOF_RECORD_BUDGET_BYTES) in emitted
    assert "No single proof" in emitted
    assert "Nothing was published" in emitted
