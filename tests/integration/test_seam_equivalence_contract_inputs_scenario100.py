"""The typed-workflow-inputs seam check, run over a payload seeded on disk.

Binds `SPECIFICATION/scenarios.md` Scenario 100's three seam-equivalence
sub-scenarios -- a workflow token the Dispatcher renders no input for, a rendered
input no workflow position reads, and a token sitting where the pinned engine
does not expand it. Each is driven through the SHIPPED `check-seam-equivalence`
gate over a throwaway repository holding the REAL committed payload beside a
committed governed-repository declaration, so what is measured is the gate an
adopter's CI actually runs rather than a rule function taking two sets.

WHY THE GOVERNED FIXTURE IS IN SCOPE HERE. The rendered half of the equality is
`contract_run_inputs` over a contract resolved from the repository's OWN
`.livespec.jsonc`, so the check reads a governed repository on every run and the
adopter-and-member-fixtures bullet of `SPECIFICATION/constraints.md` applies:
both legs are seeded, and the clean case asserts that neither declaration
perturbs the equality -- a member resting on fleet defaults and an adopter
declaring every point through the schema must produce the SAME rendered input
NAMES, because the names are the schema's and only the values are theirs.

EVERY EDIT IS READ BACK OFF DISK BEFORE IT IS JUDGED. A `str.replace` that
matched nothing returns the original text and raises nothing, so a seeded defect
that never landed would report exactly what a conformant payload reports -- the
mutation-never-applied trap. The assertions therefore prove the persisted bytes
changed before asking the check what it makes of them.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.integration.governed_repo_fixtures import (
    REPO_ROOT,
    GovernedRepo,
    over_both_fixtures,
)

_CHECK_PATH = REPO_ROOT / "dev-tooling" / "checks" / "seam_equivalence.py"

# The one input whose only reading position is the publish prompt's merge-method
# flag, which is what lets a single edit remove it from the referenced set
# without disturbing any other token.
_SINGLE_POSITION_INPUT = "merge_mode"
_MERGE_MODE_DECLARATION = 'merge_mode = "rebase"\n'
_MERGE_METHOD_TOKEN = "--{{ inputs.merge_mode }}"
_A_NODE_TIMEOUT = 'timeout="1800s"'
_TEMPLATED_TIMEOUT = 'timeout="{{ inputs.sandbox_check_suite }}"'


@pytest.fixture(name="check")
def _check_fixture() -> ModuleType:
    """The gate module, loaded by path exactly as the `justfile` target runs it."""
    assert _CHECK_PATH.is_file()
    spec = importlib.util.spec_from_file_location(
        "seam_equivalence_over_governed_repos", _CHECK_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed(*, root: Path, check: ModuleType, governed: GovernedRepo) -> Path:
    """A throwaway repository: the REAL payload beside this fixture's declaration."""
    payload = check.payload_dir(repo_root=root)
    _ = shutil.copytree(check.payload_dir(repo_root=REPO_ROOT), payload)
    _ = (root / ".livespec.jsonc").write_text(governed.config_text, encoding="utf-8")
    control = check.fixture_path(repo_root=root)
    control.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(check.fixture_path(repo_root=REPO_ROOT), control)
    return payload


def _reported(*, check: ModuleType, root: Path) -> list[tuple[str, str]]:
    """Every finding the gate composes for a seeded repository, as kind and subject."""
    return [(finding.kind, finding.subject) for finding in check.payload_findings(repo_root=root)]


def _gate_exit(*, check: ModuleType, root: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """The exit code `just check-seam-equivalence` would return for that repository."""
    monkeypatch.chdir(root)
    return check.main()


@over_both_fixtures
def test_the_committed_payload_agrees_with_a_governed_repository_declaration(
    governed: GovernedRepo,
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control: the gate CAN report clean, on both legs.

    Without it every assertion below would be equally consistent with a gate
    that refuses everything it is handed.
    """
    root = tmp_path / "clean"
    _ = _seed(root=root, check=check, governed=governed)

    assert _reported(check=check, root=root) == []
    assert check.control_failures(repo_root=root) == []
    assert _gate_exit(check=check, root=root, monkeypatch=monkeypatch) == 0


@over_both_fixtures
def test_the_seam_check_reports_each_way_the_integration_input_surfaces_disagree(
    governed: GovernedRepo,
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One seeded payload per ratified disagreement, each judged through the gate."""
    unrendered = _seed(root=tmp_path / "token", check=check, governed=governed)
    run_config = unrendered / "workflow.toml"
    _ = run_config.write_text(
        run_config.read_text(encoding="utf-8").replace(_MERGE_MODE_DECLARATION, "", 1),
        encoding="utf-8",
    )

    # The merge-method token lives in the `pr` command stage's own script since
    # v121, where the retired publication PROMPT used to carry it. Editing the
    # graph is therefore editing the one position that still reads it, and the
    # read-back below is what proves the edit landed rather than matching nothing.
    unread = _seed(root=tmp_path / "input", check=check, governed=governed)
    publication = unread / "workflow.fabro"
    _ = publication.write_text(
        publication.read_text(encoding="utf-8").replace(_MERGE_METHOD_TOKEN, "--rebase", 1),
        encoding="utf-8",
    )

    misplaced = _seed(root=tmp_path / "position", check=check, governed=governed)
    graph = misplaced / "workflow.fabro"
    _ = graph.write_text(
        graph.read_text(encoding="utf-8").replace(_A_NODE_TIMEOUT, _TEMPLATED_TIMEOUT, 1),
        encoding="utf-8",
    )

    # Read the persisted bytes back first: an edit that matched nothing would
    # leave a conformant payload and the gate would rightly report clean.
    assert _MERGE_MODE_DECLARATION not in run_config.read_text(encoding="utf-8")
    assert "inputs.merge_mode" not in publication.read_text(encoding="utf-8")
    assert _TEMPLATED_TIMEOUT in graph.read_text(encoding="utf-8")

    assert _reported(check=check, root=tmp_path / "token") == [
        ("token-without-rendered-input", _SINGLE_POSITION_INPUT)
    ]
    assert _reported(check=check, root=tmp_path / "input") == [
        ("rendered-input-without-token", _SINGLE_POSITION_INPUT)
    ]
    assert _reported(check=check, root=tmp_path / "position") == [
        ("non-rendered-position", "sandbox_check_suite")
    ]
    for name in ("token", "input", "position"):
        assert _gate_exit(check=check, root=tmp_path / name, monkeypatch=monkeypatch) == 1
