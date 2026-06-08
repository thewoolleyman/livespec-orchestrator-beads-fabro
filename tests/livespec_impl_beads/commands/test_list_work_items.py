"""Tests for the list-work-items thin-transport command (beads substrate).

The hermetic `FakeBeadsClient` is the backend (autouse fixture sets
`LIVESPEC_BEADS_FAKE=1` and resets the singleton). Work-items are seeded
into the same in-memory tenant the command reads by calling
`append_work_item` with a `fake=True` connection descriptor; the
process-singleton fake makes the seeded writes visible to `main`.
"""

import json

import pytest
from livespec_impl_beads._beads_client import make_beads_client
from livespec_impl_beads.commands.list_work_items import main
from livespec_impl_beads.store import append_work_item
from livespec_impl_beads.types import AuditRecord, StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed(item: WorkItem) -> None:
    # `append_work_item` creates an OPEN issue (and closes in place for the
    # `closed` case). Intermediate lifecycle statuses (`blocked`,
    # `in_progress`, `deferred`) are reached by a subsequent status
    # transition in the tenant — modelled here via the same fake client the
    # store talks to.
    append_work_item(path=_config(), item=item)
    if item.status not in ("open", "closed"):
        make_beads_client(config=_config()).update_issue(issue_id=item.id, status=item.status)


def _item(
    *,
    id_: str,
    status: str = "open",
    origin: str = "freeform",
    gap_id: str | None = None,
    depends_on: tuple[str, ...] = (),
    priority: int = 2,
    spec_commitment_hint: str | None = None,
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=f"{id_} title",
        description="d",
        origin=origin,  # type: ignore[arg-type]
        gap_id=gap_id,
        priority=priority,
        assignee=None,
        depends_on=depends_on,
        captured_at="2026-05-19T00:00:00Z",
        resolution="completed" if status == "closed" else None,
        reason="done" if status == "closed" else None,
        audit=AuditRecord(
            verification_timestamp="2026-05-19T01:00:00Z",
            commits=("c",),
            files_changed=("f",),
            merge_sha="abc123",
            pr_number=None,
        )
        if status == "closed"
        else None,
        superseded_by=None,
        spec_commitment_hint=spec_commitment_hint,
    )


def test_main_empty_store_prints_no_items(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(no work-items)" in captured.out


def test_main_lists_all_human(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a", origin="gap-tied", gap_id="G1"))
    _seed(_item(id_="li-b"))
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "li-a" in captured.out
    assert "li-b" in captured.out
    assert "gap=G1" in captured.out


def test_main_filter_gap_tied(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a", origin="gap-tied", gap_id="G1"))
    _seed(_item(id_="li-b"))
    rc = main(["--filter=gap-tied"])
    captured = capsys.readouterr()
    assert "li-a" in captured.out
    assert "li-b" not in captured.out
    assert rc == 0


def test_main_filter_freeform(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a", origin="gap-tied", gap_id="G1"))
    _seed(_item(id_="li-b"))
    rc = main(["--filter=freeform"])
    captured = capsys.readouterr()
    assert "li-b" in captured.out
    assert "li-a" not in captured.out
    assert rc == 0


def test_main_filter_blocked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a", status="blocked"))
    _seed(_item(id_="li-b"))
    rc = main(["--filter=blocked"])
    captured = capsys.readouterr()
    assert "li-a" in captured.out
    assert "li-b" not in captured.out
    assert rc == 0


def test_main_filter_ready_excludes_open_local_deps(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a"))
    _seed(_item(id_="li-b", depends_on=("li-a",)))
    rc = main(["--filter=ready"])
    captured = capsys.readouterr()
    assert "li-a" in captured.out
    assert "li-b" not in captured.out
    assert rc == 0


def test_main_filter_ready_does_not_exclude_missing_local_dep(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing local ids resolve to UNKNOWN; only OPEN excludes per the v072 contract."""
    _seed(_item(id_="li-c", depends_on=("li-missing",)))
    rc = main(["--filter=ready"])
    captured = capsys.readouterr()
    assert "li-c" in captured.out
    assert rc == 0


def test_main_filter_ready_includes_closed_deps(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a", status="closed"))
    _seed(_item(id_="li-b", depends_on=("li-a",)))
    rc = main(["--filter=ready"])
    captured = capsys.readouterr()
    assert "li-b" in captured.out
    assert rc == 0


def test_main_filter_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a"))
    _seed(_item(id_="li-b", status="closed"))
    rc = main(["--filter=closed"])
    captured = capsys.readouterr()
    assert "li-b" in captured.out
    assert "li-a" not in captured.out
    assert rc == 0


def test_main_with_gap_id_filter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a", origin="gap-tied", gap_id="G1"))
    _seed(_item(id_="li-b", origin="gap-tied", gap_id="G2"))
    rc = main(["--with-gap-id", "G1"])
    captured = capsys.readouterr()
    assert "li-a" in captured.out
    assert "li-b" not in captured.out
    assert rc == 0


def test_main_json_output_with_audit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-a", status="closed"))
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload[0]["id"] == "li-a"
    assert payload[0]["audit"]["commits"] == ["c"]


def test_main_json_output_without_audit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-open"))
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload[0]["id"] == "li-open"
    assert payload[0]["audit"] is None


# -- spec_commitment_hint surface (livespec PC #4 sub-proposal 3) --------


def test_main_json_output_includes_spec_commitment_hint_when_set(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--json` exposes spec_commitment_hint so the doctor invariant can match."""
    _seed(_item(id_="li-a", spec_commitment_hint="spec-impl-commitment-tracking"))
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload[0]["spec_commitment_hint"] == "spec-impl-commitment-tracking"


def test_main_json_output_includes_null_spec_commitment_hint_when_unset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--json` carries explicit null for freeform work-items (the unset case)."""
    _seed(_item(id_="li-a"))
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert "spec_commitment_hint" in payload[0]
    assert payload[0]["spec_commitment_hint"] is None


def test_main_with_spec_commitment_hint_filter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--with-spec-commitment-hint=<id_hint>` filters to exact hint match."""
    _seed(_item(id_="li-match", spec_commitment_hint="topic-x"))
    _seed(_item(id_="li-other", spec_commitment_hint="topic-y"))
    _seed(_item(id_="li-none"))
    rc = main(["--with-spec-commitment-hint", "topic-x"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "li-match" in captured.out
    assert "li-other" not in captured.out
    assert "li-none" not in captured.out


def test_main_with_spec_commitment_hint_filter_no_matches(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A hint with no matching record yields the empty-listing message."""
    _seed(_item(id_="li-a"))
    rc = main(["--with-spec-commitment-hint", "no-match"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(no work-items)" in captured.out


def test_main_with_spec_commitment_hint_filter_combines_with_filter_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hint filter composes with --filter (intersect, not union)."""
    _seed(_item(id_="li-open", status="open", spec_commitment_hint="topic-x"))
    _seed(_item(id_="li-closed", status="closed", spec_commitment_hint="topic-x"))
    rc = main(["--filter=closed", "--with-spec-commitment-hint", "topic-x"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "li-closed" in captured.out
    assert "li-open" not in captured.out


def test_main_with_spec_commitment_hint_filter_combines_with_gap_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hint filter composes with --with-gap-id (intersect, not union)."""
    _seed(
        _item(
            id_="li-a",
            origin="gap-tied",
            gap_id="G1",
            spec_commitment_hint="topic-x",
        )
    )
    _seed(_item(id_="li-b", spec_commitment_hint="topic-x"))
    rc = main(["--with-gap-id", "G1", "--with-spec-commitment-hint", "topic-x"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "li-a" in captured.out
    assert "li-b" not in captured.out
