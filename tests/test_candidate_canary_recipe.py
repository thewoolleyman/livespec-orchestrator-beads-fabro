"""The candidate-canary recipe files a fresh canary and dispatches it to a factory.

Assertion under test: *a just recipe files a fresh canary work-item from the
fixture template and dispatches it to a named factory*.

Two layers, because the assertion spans both and neither layer alone establishes
it. The COMMITTED WIRING layer reads the recipe and the script it shells to: a
recipe that files nothing, or a script that files without dispatching, satisfies
the words and not the operation. The FILING layer drives the real seam against
the hermetic in-memory tenant, so "files a fresh canary from the fixture
template" is measured by the record that lands rather than by the script's
intent.

`--factory` is asserted as an argument the script FORWARDS rather than a default
it resolves. A canary is frequently evidence about a particular engine, and a
dispatch that silently took `dispatcher.default_factory` would be a perfectly
normal green run against the wrong build — the wrong-population trap this
repository's own instrument-aim discipline is written around.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import take_candidate_canary as canary
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.io import IOFailure
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_REPO_ROOT = Path(__file__).resolve().parents[1]
_JUSTFILE = _REPO_ROOT / "justfile"
_SCRIPT_RELPATH = "orchestrator-image/take-candidate-canary.sh"
_SCRIPT = _REPO_ROOT / _SCRIPT_RELPATH
_TEMPLATE_RELPATH = "orchestrator-image/candidate-canary-work-item-template.md"
_MARKER_RELPATH = "orchestrator-image/candidate-canary-log.md"
_RECIPE = "take-candidate-canary"
_TENANT = "livespec-canary-fixture"
_FACTORY = "hp"


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_TENANT,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _governed_repo(*, tmp_path: Path) -> Path:
    """A throwaway repo carrying only what the filing seam reads.

    Opens on the committed script's presence so the Red moment of this file is a
    genuine assertion failure about the recipe's own deliverable rather than an
    attribute error about the module the recipe shells to.
    """
    assert _SCRIPT.is_file(), f"no committed candidate-canary script at {_SCRIPT}"
    repo = tmp_path / "governed"
    (repo / "orchestrator-image").mkdir(parents=True)
    (repo / "SPECIFICATION").mkdir()
    for relpath in (_TEMPLATE_RELPATH, _MARKER_RELPATH):
        (repo / relpath).write_text(
            (_REPO_ROOT / relpath).read_text(encoding="utf-8"), encoding="utf-8"
        )
    # The reference line resolves against the governed tree's OWN H2 set, so the
    # heading the fixture names has to exist here too.
    (repo / "SPECIFICATION" / "constraints.md").write_text(
        "## Fabro runtime constraints\n\nThe engine is external.\n", encoding="utf-8"
    )
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": _TENANT,
                        "prefix": _TENANT,
                        "server_user": _TENANT,
                        "database": _TENANT,
                        "bd_path": "bd",
                        "fake": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


# --------------------------------------------------------------------------
# The committed wiring: recipe -> script -> file then dispatch.
# --------------------------------------------------------------------------


def test_the_committed_recipe_shells_to_the_candidate_canary_script() -> None:
    assert _SCRIPT.is_file(), f"no committed candidate-canary script at {_SCRIPT}"
    justfile = _JUSTFILE.read_text(encoding="utf-8")

    assert f"\n{_RECIPE} *ARGS:\n" in justfile
    # The recipe takes the factory name as an argument, so it must declare
    # per-recipe positional arguments; without the attribute `just` refuses the
    # parameter and the operator never reaches the script.
    assert f"[positional-arguments]\n{_RECIPE} *ARGS:\n" in justfile
    assert f'bash {_SCRIPT_RELPATH} "$@"' in justfile


def test_the_committed_script_files_from_the_template_then_dispatches_to_the_named_factory() -> (
    None
):
    assert _SCRIPT.is_file(), f"no committed candidate-canary script at {_SCRIPT}"
    script = _SCRIPT.read_text(encoding="utf-8")

    assert "--factory" in script
    # The filing leg, then the dispatch leg. Both legs, in that order: a script
    # that files without dispatching leaves a fresh fixture item stranded in the
    # ledger, which is worse than not taking the canary at all.
    filing = script.index("bin/take_candidate_canary.py")
    dispatching = script.index("bin/dispatcher.py")
    assert filing < dispatching
    assert "dispatch" in script[dispatching:]
    assert _TEMPLATE_RELPATH in script
    assert canary.CANARY_TEMPLATE_RELPATH == _TEMPLATE_RELPATH
    assert canary.CANARY_MARKER_RELPATH == _MARKER_RELPATH


# --------------------------------------------------------------------------
# The filing seam: a fresh record rendered from the committed template.
# --------------------------------------------------------------------------


def test_filing_lands_a_fresh_ready_canary_rendered_from_the_committed_template(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)
    config = _config(repo_root=repo)

    filed = canary.file_candidate_canary(
        path=config, repo_root=repo, factory=_FACTORY, now_iso="2026-10-13T00:00:00Z"
    )

    assert is_successful(filed)
    record = unsafe_perform_io(filed.unwrap())
    assert record.status == "ready"
    assert record.item_id.startswith(f"{_TENANT}-")
    stored = materialize_work_items(records=read_work_items(path=config))[record.item_id]
    assert record.item_id in stored.title
    assert _FACTORY in stored.description
    assert "@@" not in stored.description


def test_each_filing_mints_its_own_fresh_work_item(tmp_path: Path) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)
    config = _config(repo_root=repo)

    first = canary.file_candidate_canary(
        path=config, repo_root=repo, factory=_FACTORY, now_iso="2026-10-13T00:00:00Z"
    )
    second = canary.file_candidate_canary(
        path=config, repo_root=repo, factory=_FACTORY, now_iso="2026-10-13T00:00:01Z"
    )

    assert unsafe_perform_io(first.unwrap()).item_id != unsafe_perform_io(second.unwrap()).item_id


# --------------------------------------------------------------------------
# The command-line surface the script shells to.
# --------------------------------------------------------------------------


def test_the_cli_prints_the_minted_id_on_stdout_for_the_dispatch_leg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)

    code = canary.main(argv=["--factory", _FACTORY, "--project-root", str(repo)])

    captured = capsys.readouterr()
    assert code == 0
    # EXACTLY the id on stdout: the script reads it as the dispatch target, so a
    # human-readable preamble there would be passed to `--item`.
    assert captured.out.splitlines() == [captured.out.strip()]
    assert captured.out.strip().startswith(f"{_TENANT}-")
    assert _FACTORY in captured.err


def test_the_cli_defaults_its_project_root_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)

    code = canary.main(argv=["--factory", _FACTORY])

    assert code == 0
    assert capsys.readouterr().out.strip().startswith(f"{_TENANT}-")


def test_a_refused_filing_is_reported_and_prints_no_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        canary,
        "file_captured_work_item",
        lambda **_kwargs: IOFailure(WorkItemNotFoundError(item_id="bd-missing")),
    )

    code = canary.main(argv=["--factory", _FACTORY, "--project-root", str(repo)])

    captured = capsys.readouterr()
    assert code != 0
    assert captured.out == ""
    assert "bd-missing" in captured.err
