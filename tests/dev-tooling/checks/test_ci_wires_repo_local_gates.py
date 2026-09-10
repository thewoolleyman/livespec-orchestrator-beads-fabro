"""Tests for the repo-local gate CI-wiring guard.

The guard reports an ABSENCE — a check slug missing from the CI workflow's
unconditional metadata batch or from the doc-only pre-push target list — so a
guard that scans the wrong file or the wrong step prints exactly what a wired
repository prints. Every assertion below is therefore made against a workflow
and scripts seeded on disk and read back through the guard's own file path,
plus two controls: the batch anchor must be found, and every guarded slug must
name a real justfile recipe.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "ci_wires_repo_local_gates.py"

_GATES = (
    "check-no-fleet-toolchain-literals",
    "check-seam-equivalence",
    "check-fabro-graph-validity",
)


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_wires_repo_local_gates", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="check")
def _check() -> ModuleType:
    return _load_check()


def _workflow(*, slugs: tuple[str, ...], anchored: bool = True) -> str:
    name = "Run the batched metadata checks" if anchored else "Run something else"
    lines = "".join(f'          just {slug} || failed="$failed {slug}"\n' for slug in slugs)
    return (
        "jobs:\n  meta:\n    steps:\n"
        f'      - name: {name}\n        run: |\n          failed=""\n{lines}'
        '          if [ -n "$failed" ]; then exit 1; fi\n'
        "      - name: Later step\n        run: echo done\n"
    )


def _doc_only(*, slugs: tuple[str, ...], commented: tuple[str, ...] = ()) -> str:
    """Render a targets block; each `commented` slug is named ONLY in comments.

    Every commented slug is named twice — once on a whole-line comment and once
    as a trailing comment after a real target — so a parse that ignores only one
    of the two comment forms still reads the slug as a wired target.
    """
    lines = [f"    {slug}\n" for slug in slugs]
    lines += [f"    # deliberately absent: {slug}\n" for slug in commented]
    lines += [f"    check-unguarded  # nor {slug}\n" for slug in commented]
    body = "".join(lines)
    return f'#!/usr/bin/env bash\ntargets=(\n{body})\nfor target in "${{targets[@]}}"; do just "$target"; done\n'


def _justfile(*, slugs: tuple[str, ...]) -> str:
    return "".join(f"{slug}:\n    uv run python dev-tooling/checks/x.py\n\n" for slug in slugs)


def _seed(
    *,
    root: Path,
    workflow_slugs: tuple[str, ...],
    doc_only_slugs: tuple[str, ...],
    recipe_slugs: tuple[str, ...],
    anchored: bool = True,
    commented_doc_only_slugs: tuple[str, ...] = (),
) -> None:
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(_workflow(slugs=workflow_slugs, anchored=anchored), encoding="utf-8")
    script = root / "dev-tooling" / "just-check-pre-commit-doc-only.sh"
    script.parent.mkdir(parents=True)
    _ = script.write_text(
        _doc_only(slugs=doc_only_slugs, commented=commented_doc_only_slugs), encoding="utf-8"
    )
    _ = (root / "justfile").write_text(_justfile(slugs=recipe_slugs), encoding="utf-8")


def test_the_guarded_slugs_are_the_repo_local_payload_gates_and_the_guard_itself(
    check: ModuleType,
) -> None:
    assert set(check.REQUIRED_SLUGS) == {*_GATES, "check-ci-wires-repo-local-gates"}


def test_a_fully_wired_repository_reports_nothing(check: ModuleType, tmp_path: Path) -> None:
    slugs = tuple(check.REQUIRED_SLUGS)
    _seed(root=tmp_path, workflow_slugs=slugs, doc_only_slugs=slugs, recipe_slugs=slugs)

    assert check.findings(repo_root=tmp_path) == []


def test_a_slug_missing_from_the_ci_batch_is_named(check: ModuleType, tmp_path: Path) -> None:
    slugs = tuple(check.REQUIRED_SLUGS)
    _seed(root=tmp_path, workflow_slugs=slugs[1:], doc_only_slugs=slugs, recipe_slugs=slugs)

    findings = check.findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert slugs[0] in findings[0]
    assert "ci.yml" in findings[0]


def test_a_slug_missing_from_the_doc_only_targets_is_named(
    check: ModuleType, tmp_path: Path
) -> None:
    slugs = tuple(check.REQUIRED_SLUGS)
    _seed(root=tmp_path, workflow_slugs=slugs, doc_only_slugs=slugs[:-1], recipe_slugs=slugs)

    findings = check.findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert slugs[-1] in findings[0]
    assert "doc-only" in findings[0]


def test_a_slug_named_only_in_a_comment_is_absent_from_the_doc_only_list(
    check: ModuleType, tmp_path: Path
) -> None:
    """A comment naming a guarded slug must not read as a wired target.

    The false-present path this closes: a note inside the targets block saying
    which slugs are deliberately absent would otherwise satisfy the very check
    that exists to report their absence.
    """
    slugs = tuple(check.REQUIRED_SLUGS)
    _seed(
        root=tmp_path,
        workflow_slugs=slugs,
        doc_only_slugs=slugs[:-1],
        recipe_slugs=slugs,
        commented_doc_only_slugs=(slugs[-1],),
    )

    findings = check.findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert slugs[-1] in findings[0]
    assert "doc-only" in findings[0]


def test_a_missing_batch_anchor_is_a_control_failure_not_a_clean_report(
    check: ModuleType, tmp_path: Path
) -> None:
    slugs = tuple(check.REQUIRED_SLUGS)
    _seed(
        root=tmp_path,
        workflow_slugs=slugs,
        doc_only_slugs=slugs,
        recipe_slugs=slugs,
        anchored=False,
    )

    findings = check.findings(repo_root=tmp_path)

    assert findings and all("control" in finding for finding in findings)


def test_a_guarded_slug_without_a_justfile_recipe_is_a_control_failure(
    check: ModuleType, tmp_path: Path
) -> None:
    slugs = tuple(check.REQUIRED_SLUGS)
    _seed(root=tmp_path, workflow_slugs=slugs, doc_only_slugs=slugs, recipe_slugs=slugs[:-1])

    findings = check.findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert "control" in findings[0]
    assert slugs[-1] in findings[0]


def test_main_returns_one_on_findings_and_zero_when_wired(
    check: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slugs = tuple(check.REQUIRED_SLUGS)
    _seed(root=tmp_path, workflow_slugs=slugs[1:], doc_only_slugs=slugs, recipe_slugs=slugs)
    monkeypatch.setattr(check, "_REPO_ROOT", tmp_path)
    assert check.main() == 1

    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    _ = workflow.write_text(_workflow(slugs=slugs), encoding="utf-8")
    assert check.main() == 0


def test_this_repository_wires_every_guarded_slug(check: ModuleType) -> None:
    """The load-bearing case: the committed workflow and scripts are wired."""
    assert check.findings(repo_root=_REPO_ROOT) == []
