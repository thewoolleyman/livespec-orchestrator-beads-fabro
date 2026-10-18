"""The records a stranded-claim pass leaves: journal rows and ledger comments.

PURE renderers, so every claim each record makes is assertable here rather
than inferred from a pass that wrote one.

TWO PROPERTIES carry more than their size. A record whose claim stamp carried
no server url STATES that rather than printing `None`, because the comment is
the account an operator reads months later and `None` reads as a bug in the
writer. And neither body may carry a goal-template opening delimiter: a ledger
comment is append-only, the goal brief renders it verbatim, and an opener
admitted into one costs the item its dispatchability permanently.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_stranded_claim_records.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records"

# The two goal-template opening delimiters, assembled rather than written, for
# the reason AGENTS.md records: a literal one in this file's own text is read by
# the detector that guards against them.
_OPENERS = (chr(123) + chr(123), chr(123) + "%")


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def test_the_release_record_names_the_item_the_run_the_factory_and_the_reason() -> None:
    assert _MODULE_PATH.is_file()
    module = _module()

    record = module.recovery_journal_record(
        stage=module.STRANDED_CLAIM_RELEASE_STAGE,
        recovered=module.RecoveredClaim(
            work_item_id="bd-ib-one",
            run_id="01RUN",
            factory_name="hp",
            factory_server_url="https://hp.example:32276",
            reason=module.REASON_RUN_ABSENT,
            route="absent-run-release",
            status="ready",
            effects_written=("journal-record", "ledger-comment", "status-transition"),
        ),
    )

    assert record == {
        "stage": "stranded-claim-release",
        "work_item_id": "bd-ib-one",
        "run_id": "01RUN",
        "factory": "hp",
        "factory_server": "https://hp.example:32276",
        "reason": "run-absent",
        "status": "ready",
        "effects_written": ["journal-record", "ledger-comment", "status-transition"],
    }


def test_a_held_claim_row_carries_its_reason_its_host_and_its_remedy() -> None:
    module = _module()

    record = module.hold_journal_record(
        held=module.HeldClaim(
            work_item_id="bd-ib-one",
            run_id=None,
            factory_name="hp",
            factory_server_url=None,
            dispatching_host="other-host",
            hold_reason="owner-elsewhere",
            remedy=None,
        )
    )

    assert record == {
        "stage": "stranded-claim-hold",
        "work_item_id": "bd-ib-one",
        "run_id": None,
        "factory": "hp",
        "factory_server": None,
        "dispatching_host": "other-host",
        "reason": "owner-elsewhere",
        "remedy": None,
    }


@pytest.mark.parametrize("server", ["https://hp.example:32276", None])
def test_the_release_comment_names_every_fact_the_clause_requires(*, server: str | None) -> None:
    module = _module()

    body = module.release_comment_body(
        work_item_id="bd-ib-one",
        run_id="01RUN",
        factory_name="hp",
        factory_server_url=server,
    )

    assert body.splitlines()[0] == module.RELEASE_COMMENT_MARKER
    for fragment in ("bd-ib-one", "01RUN", "hp", module.REASON_RUN_ABSENT, "ready"):
        assert fragment in body
    # An absent server is STATED rather than rendered as `None`.
    assert ("None" in body) is False
    assert (server is None) == ("no server recorded on the claim stamp" in body)


@pytest.mark.parametrize("predecessor", ["01PREVRUN", None])
def test_the_repeated_comment_names_both_runs(*, predecessor: str | None) -> None:
    module = _module()

    body = module.repeated_comment_body(
        work_item_id="bd-ib-one",
        run_id="01RUN",
        predecessor_run_id=predecessor,
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
    )

    assert body.splitlines()[0] == module.REPEATED_COMMENT_MARKER
    for fragment in ("bd-ib-one", "01RUN", module.REASON_RUN_ABSENT_REPEATED, "needs-human"):
        assert fragment in body
    assert ("01PREVRUN" in body) == (predecessor == "01PREVRUN")
    assert ("(run id not recorded)" in body) == (predecessor is None)


def test_neither_comment_can_poison_a_later_goal_render() -> None:
    module = _module()
    bodies = (
        module.release_comment_body(
            work_item_id="bd-ib-one",
            run_id="01RUN",
            factory_name="hp",
            factory_server_url=None,
        ),
        module.repeated_comment_body(
            work_item_id="bd-ib-one",
            run_id="01RUN",
            predecessor_run_id="01PREVRUN",
            factory_name="hp",
            factory_server_url=None,
        ),
    )

    for body in bodies:
        for opener in _OPENERS:
            assert opener not in body
