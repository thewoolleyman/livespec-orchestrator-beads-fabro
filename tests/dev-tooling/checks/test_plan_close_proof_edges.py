"""The `plan_close_proof` surface's shapes a conforming tenant cannot reach.

Three of them, each the kind of input that makes a reader raise or report
wrongly rather than the kind a well-formed fixture produces: the PRODUCTION
ledger client the check resolves when nothing is injected, a record whose
`metadata` key is absent or not an object, and a repository holding no `plan/`
tree at all.

WHY THESE ARE NOT IN THE SIBLING MODULE. Its fixture is the ratified tenant —
four closed plan epics and their timelines — and every case there reads the
verdict off that one population. Each shape below needs a DIFFERENT population,
and folding them in would make the sibling's exact-equality assertions depend on
which edge case had been appended last.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "plan_close_proof.py"

_RUN_LEVER = "LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE"
_CRED_ENV = "BEADS_DOLT_PASSWORD"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plan_close_proof_edges_under_test", _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CHECK = _load_check()

from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton  # noqa: E402


class _Sparse:
    """A tenant whose rows carry the `omitempty` shapes a subscripting read breaks on."""

    def __init__(self, *, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.read: list[str] = []

    def list_issues(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self.records]

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        self.read.append(issue_id)
        return []


@pytest.fixture(autouse=True)
def _armed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(_RUN_LEVER, "1")
    monkeypatch.setenv(_CRED_ENV, "fixture-tenant-password")
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    reset_fake_singleton()


def _lines(*, captured: str) -> list[dict[str, Any]]:
    return [json.loads(one) for one in captured.splitlines() if one.strip()]


def test_the_production_ledger_client_is_what_an_uninjected_run_resolves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no seam supplied the check reads the ordinary store client.

    The hermetic tenant is empty, so the verdict is clean — which is exactly what
    `just check` observes on this repository's own aggregate. What the case
    establishes is that the DEFAULT path resolves and reads at all: every other
    case injects a tenant, so none of them would notice a production read that
    raised.
    """
    (tmp_path / "plan" / "archive" / "some-plan").mkdir(parents=True)

    exit_code = _CHECK.main()

    assert exit_code == 0
    assert [one for one in _lines(captured=capsys.readouterr().err) if "verdict" in one] == []


def test_a_record_carrying_no_metadata_object_is_skipped_rather_than_raising(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "plan" / "archive" / "some-plan").mkdir(parents=True)
    sparse = _Sparse(
        records=[
            # No `metadata` key at all — the sparse shape a record with no
            # metadata really has, and the one a subscripting reader raises on.
            {"id": "bd-ib-bare", "issue_type": "epic", "status": "closed"},
            # A `metadata` value that is not an object.
            {"id": "bd-ib-odd", "status": "closed", "metadata": "some-plan"},
            # A metadata object whose `plan_slug` is blank.
            {"id": "bd-ib-blank", "status": "closed", "metadata": {"plan_slug": "  "}},
            # A well-formed slug naming no directory, so nothing is in scope.
            {"id": "bd-ib-other", "status": "closed", "metadata": {"plan_slug": "no-such"}},
            # The one well-formed, in-scope-for-the-READ row, closed before the
            # proof leg's ratification date. It is what makes the timeline reader
            # a demonstrated instrument: without it, "no timeline was read"
            # would be equally consistent with a reader nothing can reach.
            {
                "id": "bd-ib-legacyedge",
                "status": "closed",
                "metadata": {"plan_slug": "some-plan"},
                "closed_at": "2026-10-01T00:00:00Z",
            },
        ]
    )

    exit_code = _CHECK.main(client=sparse)

    assert exit_code == 0
    assert [one for one in _lines(captured=capsys.readouterr().err) if "verdict" in one] == []
    # None of the four malformed rows was in scope, so no timeline was read for
    # any of them; the pre-ratification row's WAS read and then excluded by date.
    assert sparse.read == ["bd-ib-legacyedge"]


def test_a_repository_with_no_plan_tree_puts_every_epic_out_of_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sparse = _Sparse(
        records=[{"id": "bd-ib-x", "status": "closed", "metadata": {"plan_slug": "ghost"}}]
    )

    exit_code = _CHECK.main(client=sparse)

    assert exit_code == 0
    assert _CHECK.plan_record_slugs(repo_root=Path.cwd()) == frozenset()
    assert [one for one in _lines(captured=capsys.readouterr().err) if "verdict" in one] == []
