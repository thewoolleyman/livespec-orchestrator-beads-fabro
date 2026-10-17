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

import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._config import (
    has_fabro_factories,
    has_fabro_factory,
)
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


def test_an_undeclared_factory_name_would_resolve_to_the_ambient_local_engine() -> None:
    """The hazard the recipe's factory guard exists to close, measured.

    An undeclared name is NOT an error downstream: `_factory_entry` answers `{}`
    for one, so the target resolves with no server and the dispatch lands on the
    ambient local engine rather than the candidate the name meant. This asserts
    the two predicates the guard is built on give the answer it needs — that this
    repository DOES constrain factory names, and that `hp-candidate`, the
    likeliest invocation of a candidate-canary recipe, is not among them.

    Without this, the guard below could be satisfied by a script that refuses
    everything or nothing, and the text assertions could not tell the difference.
    """
    assert has_fabro_factories(cwd=_REPO_ROOT) is True
    assert has_fabro_factory(cwd=_REPO_ROOT, factory="hp") is True
    assert has_fabro_factory(cwd=_REPO_ROOT, factory="hp-candidate") is False


def test_the_recipe_refuses_an_undeclared_factory_before_filing_anything() -> None:
    """An undeclared name must refuse at the guard, touching no ledger.

    Run against the REAL script rather than a transcription of it, and it needs
    neither credentials nor a ledger precisely BECAUSE the guard precedes
    `file-canary` — so this test passing is itself evidence of the ordering the
    finding turns on. A guard placed after the filing would reach `file-canary`
    here, which needs the tenant password, and this test would fail.

    Requiring the argument closed only OMISSION. An undeclared name is the
    strictly worse case: the run completes and is read as evidence about a
    candidate engine that never ran it — an item-quality failure wearing an
    engine failure's clothes, one layer up from the one the fixture removes.
    """
    completed = subprocess.run(
        ["bash", str(_RECIPE_SCRIPT), "hp-candidate"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0, completed.stdout
    assert "hp-candidate is not a factory this repository declares" in completed.stderr
    # The declared set is named, because a refusal an operator cannot act on
    # sends them to the config file to work out what they should have typed.
    assert "declared factories: hp" in completed.stderr
    # Nothing was filed: the refusal says so, and the filing narration that the
    # successful path prints is absent.
    assert "nothing was filed and nothing was dispatched" in completed.stderr
    assert "filed canary" not in completed.stdout


def test_the_recipe_grades_the_factory_name_before_it_files_a_canary() -> None:
    """The guard's position and its three outcomes, read off the script.

    POSITION is the load-bearing property: a guard that ran after `file-canary`
    would strand a filed canary at the top of the ready queue for a concurrent
    drain to select, so a typo would cost a disposal as well as a refusal.

    The exit codes deliberately skip 1, because `python3 -c` exits 1 on any
    uncaught exception — a probe that signalled "declared, and this is not one"
    with 1 would report an ImportError as a confident verdict about the operator's
    config. Measured while building this guard: with the probe's dependencies
    absent it refused `hp` while naming an EMPTY declared set, which is a
    plausible, actionable and entirely wrong cause.
    """
    script = _RECIPE_SCRIPT.read_text(encoding="utf-8")

    guard_at = script.index("factory_probe=")
    filing_at = script.index("dispatcher.py file-canary")
    assert guard_at < filing_at, "the factory guard must precede the filing"

    # Both predicates, because an unconstrained repository must stay
    # unconstrained: a repo declaring no `factories` block constrains no name.
    assert "has_fabro_factories" in script
    assert "has_fabro_factory" in script
    # An unreadable config is its own outcome, never folded into "undeclared" —
    # the confusion `dispatcher_block`'s own docstring warns about.
    assert "LivespecConfigUnreadableError" in script
    assert "could not be read" in script
    # And a probe that cannot run at all reports itself, not a verdict.
    assert "NOT a verdict about" in script
