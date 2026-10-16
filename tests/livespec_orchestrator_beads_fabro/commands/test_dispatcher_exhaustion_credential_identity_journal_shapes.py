"""Every journal shape the credential-identity read must survive un-raised.

Sits beside `test_dispatcher_exhaustion_credential_identity`, which binds the
BEHAVIOUR the clause names. This module covers the shapes a live dispatch
journal actually holds and that behaviour cannot reach: the file is append-only
and written by concurrent passes, so a truncated last line is an ordinary state
rather than a fault, and `omitempty`-sparse records mean a missing key is the
encoding of an absence rather than evidence of loss.

WHY A SEPARATE MODULE. These cases came out of a coverage measurement taken
after the behavioural Red was authored, and a Red's test bytes are fixed across
its Red-to-Green pair -- the same reason `test_plan_result_proof_subject.py`
sits beside `test_plan_result_proof.py`.

EVERY CASE HERE ASSERTS `None` AND WOULD ASSERT IT ANYWAY, so each one carries
a POSITIVE CONTROL on the same journal: a well-formed assessment appended after
the degraded line, read back as the identity it names. Without the control, a
reader that had simply stopped reading the journal -- or one that raised and was
caught somewhere upstream -- would satisfy every negative in the file.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T17:40:00Z"
_ITEM = "bd-ib-b53dhr"
_IDENTITY = "1111111111111111"
# The literal `_dispatcher_session_headroom_io.ABSENT_CREDENTIAL_IDENTITY`
# writes when there is no credential to fingerprint. Spelled out rather than
# imported so this module states the value it is asserting about, and bound to
# the exported name by the first case below.
_ABSENT = "absent"


def _identity_module() -> Any:
    return import_module(f"{_PACKAGE}._dispatcher_exhaustion_credential_identity")


def _read(*, path: Path | None) -> str | None:
    return _identity_module().journaled_admission_credential_identity(
        journal_path=path, work_item_id=_ITEM
    )


def _assessment(*, work_item_id: str, assessments: object) -> dict[str, object]:
    return {
        "at": _NOW,
        "stage": "acp-session-headroom",
        "work_item_id": work_item_id,
        "session_headroom_floor_percent": 20,
        "assessments": assessments,
    }


def _reading(*, identity: object) -> dict[str, object]:
    return {
        "credential_identity": identity,
        "utilization_percent": 10.0,
        "remaining_percent": 90.0,
        "unobservable": None,
        "observed_at": _NOW,
        "five_hour_drain_percent_per_hour": None,
    }


def _journal(*, tmp_path: Path, lines: tuple[str, ...]) -> Path:
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def _healthy_line() -> str:
    return json.dumps(_assessment(work_item_id=_ITEM, assessments=[_reading(identity=_IDENTITY)]))


def test_the_absent_sentinel_is_bound_to_the_name_the_reader_excludes() -> None:
    """The clause's wording: an absent identity is not a credential identity."""
    headroom_io = import_module(f"{_PACKAGE}._dispatcher_session_headroom_io")

    assert headroom_io.ABSENT_CREDENTIAL_IDENTITY == _ABSENT


def test_no_journal_and_a_journal_that_is_not_a_file_both_name_no_identity(
    tmp_path: Path,
) -> None:
    """A fresh clone and a `--journal` naming nothing yet owe the same answer."""
    assert _read(path=None) is None
    assert _read(path=tmp_path / "never-written.jsonl") is None
    # The control: the same reader on a journal that DOES hold the assessment.
    assert _read(path=_journal(tmp_path=tmp_path, lines=(_healthy_line(),))) == _IDENTITY


def test_a_truncated_or_non_object_line_is_passed_over_rather_than_raising(
    tmp_path: Path,
) -> None:
    """The append-only journal's last line can be half-written at any instant."""
    degraded = ('{"stage": "acp-session-headr', "[1, 2, 3]")

    for line in degraded:
        assert _read(path=_journal(tmp_path=tmp_path, lines=(line,))) is None
        # The control: the identity is still read when a healthy record sits
        # UNDER the degraded line, which is the real concurrent-write shape.
        assert _read(path=_journal(tmp_path=tmp_path, lines=(_healthy_line(), line))) == _IDENTITY


def test_an_assessment_for_another_work_item_names_no_identity_for_this_one(
    tmp_path: Path,
) -> None:
    """One evaluation journals one record per AFFECTED item, not one per journal."""
    other = json.dumps(
        _assessment(work_item_id="bd-somebody-else", assessments=[_reading(identity="9999")])
    )

    assert _read(path=_journal(tmp_path=tmp_path, lines=(other,))) is None
    # The control, on the same journal: this item's own record still answers,
    # and answers with ITS identity rather than the neighbour's.
    assert _read(path=_journal(tmp_path=tmp_path, lines=(_healthy_line(), other))) == _IDENTITY


def test_an_assessment_naming_nothing_usable_names_no_identity(tmp_path: Path) -> None:
    """Sparse, ill-shaped, unobservable and ABSENT readings all owe `None`.

    The last of the four is the clause's own case and the only one that is not
    a tolerance: an absent credential HAS a journaled identity string, and the
    clause rules that it is not a credential identity.
    """
    unusable: tuple[object, ...] = (
        "not-a-list",
        [],
        ["not-a-mapping"],
        [_reading(identity=None)],
        [{"observed_at": _NOW}],
        [_reading(identity=_ABSENT)],
    )

    for assessments in unusable:
        line = json.dumps(_assessment(work_item_id=_ITEM, assessments=assessments))
        assert _read(path=_journal(tmp_path=tmp_path, lines=(line,))) is None
        # The control: the NEWEST record decides, so a healthy record appended
        # after the unusable one is the one that answers.
        assert _read(path=_journal(tmp_path=tmp_path, lines=(line, _healthy_line()))) == _IDENTITY


def test_the_first_real_identity_wins_over_an_absent_reading_beside_it(
    tmp_path: Path,
) -> None:
    """A record is single-valued, and an absent reading is not what names it."""
    line = json.dumps(
        _assessment(
            work_item_id=_ITEM,
            assessments=[_reading(identity=_ABSENT), _reading(identity=_IDENTITY)],
        )
    )

    assert _read(path=_journal(tmp_path=tmp_path, lines=(line,))) == _IDENTITY
