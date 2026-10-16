"""The one recipe that takes a candidate canary: file from the fixture, dispatch.

`just canary-dispatch <factory>` is the whole operator surface. It files a FRESH
work-item from the committed fixture — fresh rather than replayed, so the second
canary is like the first — and hands the id it was assigned straight to
`dispatcher.py dispatch --factory`, which is the surface that routes a dispatch
to a NAMED factory rather than to `dispatcher.default_factory`.

The filing leg is exercised against the in-memory ledger rather than asserted
from the script's text: whether the recipe's first command yields a dispatchable
item is the question that decides whether its second command has anything to
dispatch, and no reading of a shell script can answer it.

The canary module is reached through `import_module` inside each test rather
than imported at the top, so the first thing every test asserts is a genuine
fact about the artifact under construction rather than a collection error.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.types import StoreConfig

_REPO_ROOT = Path(__file__).resolve().parents[1]
_JUSTFILE = _REPO_ROOT / "justfile"
_RECIPE_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-canary-dispatch.sh"
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_canary"
_NOW = "2026-10-16T00:00:00Z"


def _canary() -> Any:
    canary = import_module(_MODULE_NAME)
    assert hasattr(canary, "file_canary_work_item"), dir(canary)
    assert hasattr(canary, "run_file_canary_command"), dir(canary)
    return canary


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orch-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orch-beads-fabro",
        database="livespec-orch-beads-fabro",
        bd_path="bd",
        fake=True,
        repo_root=_REPO_ROOT,
    )


@pytest.fixture(autouse=True)
def _empty_ledger() -> None:
    reset_fake_singleton()


def test_the_just_recipe_takes_a_factory_name_and_delegates_to_the_script() -> None:
    assert _RECIPE_SCRIPT.is_file(), str(_RECIPE_SCRIPT)
    justfile = _JUSTFILE.read_text(encoding="utf-8")

    assert "[positional-arguments]\ncanary-dispatch factory:" in justfile
    assert 'bash dev-tooling/just-canary-dispatch.sh "$1"' in justfile


def test_the_recipe_script_files_from_the_fixture_then_dispatches_to_that_factory() -> None:
    assert _RECIPE_SCRIPT.is_file(), str(_RECIPE_SCRIPT)
    script = _RECIPE_SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    # Exactly one argument, so a forgotten factory name refuses here rather than
    # silently dispatching to `dispatcher.default_factory`.
    assert "$# -ne 1" in script
    assert "dispatcher.py file-canary --repo ." in script
    assert "dispatcher.py dispatch" in script
    assert '--item "$item"' in script
    assert '--factory "$factory"' in script
    # The id the first command printed is what the second dispatches, so the
    # capture has to be a command substitution rather than a guess.
    assert 'item="$(' in script


def test_filing_mints_a_fresh_item_carrying_the_fixture_brief() -> None:
    canary = _canary()
    fixture = canary.read_canary_fixture(repo=_REPO_ROOT)
    config = _config()

    filed = canary.file_canary_work_item(repo=_REPO_ROOT, config=config, now_iso=_NOW)

    assert isinstance(filed, str), filed
    assert filed.startswith("bd-ib-")
    record = make_beads_client(config=config).show_issue(issue_id=filed)
    assert record["title"] == fixture.title
    assert record["description"] == fixture.description
    # Admitted by intake rather than parked, so the recipe's second command has
    # a dispatchable item without an operator driving the approve valve.
    assert record["status"] == "ready"


def test_two_canaries_are_two_items() -> None:
    canary = _canary()
    config = _config()

    first = canary.file_canary_work_item(repo=_REPO_ROOT, config=config, now_iso=_NOW)
    second = canary.file_canary_work_item(repo=_REPO_ROOT, config=config, now_iso=_NOW)

    assert first != second


def test_the_subcommand_prints_the_filed_id_and_nothing_else(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = _canary()
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")

    exit_code = dispatcher.main(argv=["file-canary", "--repo", str(_REPO_ROOT)])

    assert exit_code == 0
    printed = capsys.readouterr().out
    assert printed.strip().startswith("bd-ib-")
    assert len(printed.splitlines()) == 1


def test_an_unusable_fixture_refuses_rather_than_filing_a_canary(
    *, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    canary = _canary()

    class _Args:
        repo = str(tmp_path)

    exit_code = canary.run_file_canary_command(args=_Args())

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "LIVESPEC_CANARY_FIXTURE_UNUSABLE" in captured.err
    assert canary.CANARY_FIXTURE_RELATIVE_PATH in captured.err


def test_a_fixture_that_cannot_be_read_is_reported_rather_than_filed(*, tmp_path: Path) -> None:
    canary = _canary()

    refused = canary.file_canary_work_item(repo=tmp_path, config=_config(), now_iso=_NOW)

    assert isinstance(refused, canary.CanaryFixtureUnusable), refused
