"""Tests for the list-memos thin-transport command (beads substrate).

Seeds memos into the hermetic `FakeBeadsClient` (autouse fixture) via
`append_memo` with a `fake=True` connection descriptor; the
process-singleton fake makes the seeded writes visible to `main`.
"""

import json

import pytest
from livespec_impl_beads.commands.list_memos import main
from livespec_impl_beads.store import append_memo
from livespec_impl_beads.types import Memo, StoreConfig


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed(memo: Memo) -> None:
    append_memo(path=_config(), memo=memo)


def _memo(*, id_: str, state: str, text: str = "memo body") -> Memo:
    return Memo(
        id=id_,
        text=text,
        state=state,  # type: ignore[arg-type]
        disposition="discard" if state == "dispositioned" else None,
        captured_at="2026-05-19T00:00:00Z",
        work_item_id=None,
        knowledge_file=None,
        propose_change_topic=None,
    )


def test_main_empty_store_prints_no_memos(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(no memos)" in captured.out


def test_main_lists_memos_human(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_memo(id_="mm-aaa", state="untriaged"))
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "mm-aaa" in captured.out
    assert "untriaged" in captured.out


def test_main_filter_untriaged_excludes_dispositioned(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_memo(id_="mm-aaa", state="untriaged"))
    _seed(_memo(id_="mm-bbb", state="dispositioned"))
    rc = main(["--filter=untriaged"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "mm-aaa" in captured.out
    assert "mm-bbb" not in captured.out


def test_main_filter_dispositioned(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_memo(id_="mm-aaa", state="untriaged"))
    _seed(_memo(id_="mm-bbb", state="dispositioned"))
    rc = main(["--filter=dispositioned"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "mm-bbb" in captured.out
    assert "mm-aaa" not in captured.out


def test_main_json_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_memo(id_="mm-aaa", state="untriaged"))
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert isinstance(payload, list)
    assert payload[0]["id"] == "mm-aaa"
