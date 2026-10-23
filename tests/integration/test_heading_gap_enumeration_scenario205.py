"""Scenario 205, from the heading enumeration through to the filed work-item.

Binds `SPECIFICATION/scenarios.md` "## Scenario 205 — Gap detection enumerates
headings without an exercising test", whose heading-coverage entry owed an
integration-tier test.

THE TIER IS THE JOIN, and it is the whole reason this module exists beside the
unit-tier file
`tests/livespec_orchestrator_beads_fabro/commands/test_detect_impl_gaps.py`.
That file grades the enumeration's own payload; this one carries ONE uncovered
heading all the way through — the shipped `detect-impl-gaps` entry point over a
real spec tree and a real coverage registry on disk, then the filing
composition, then the REAL store write, then the labels read back off the beads
seam. The gap-id the filed record is asserted to carry is the one the DETECTION
emitted, never a value recomputed here, because that identity is the only thing
holding the two halves together: a renamed heading, a different payload
separator or a changed hash all keep each half internally consistent while the
filed label stops naming the heading anybody could find.

THE COVERED HEADING IS THE CONTROL, and it is not decoration. "Exactly one gap"
is otherwise equally consistent with a build that enumerates nothing it should
not AND with one that enumerates every heading and happened to be handed a tree
with one — so the fixture's second heading names an EXISTING, RESOLVABLE test
node and must produce no gap. Its counterpart is materialized as a real module
with a real function, because "names an existing test" is a claim about the
tree: an entry pointing at nothing must not read as covering, and only a
resolvable counterpart can tell the two apart.

AND THE UNCOVERED HEADING CARRIES FOUR NORMATIVE CLAUSES, which is how the
scenario's "no MUST or SHOULD clause is enumerated" becomes observable at all.
A heading with no clauses under it satisfies that `Then` for free.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._heading_gap_filing import heading_gap_work_item
from livespec_orchestrator_beads_fabro.commands._heading_gaps import SpecHeading
from livespec_orchestrator_beads_fabro.commands.detect_impl_gaps import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig

_UNCOVERED = "## The lane projection the console consumes"
_COVERED = "## The lane function the projection calls"
_COVERING_TEST = "tests.integration.test_present.test_present_case"
_DANGLING_TEST = "tests.integration.test_vanished.test_vanished_case"
_CAPTURED_AT = "2026-10-23T00:00:00Z"

# Four normative clauses under the UNCOVERED heading, so "one gap, not one per
# clause" is a reading the fixture can actually falsify.
_SPEC_MD = (
    "# Title\n"
    "\n"
    f"{_UNCOVERED}\n"
    "\n"
    "A consumer MUST read the projected lane.\n"
    "A consumer SHOULD NOT re-derive it.\n"
    "A producer MUST NOT omit the reason.\n"
    "A producer SHOULD emit null for an absent reason.\n"
    "\n"
    f"{_COVERED}\n"
    "\n"
    "Prose.\n"
)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _governed_tree(*, project_root: Path, covering_test: str) -> None:
    """A governed spec tree with one covered heading and one uncovered one."""
    spec = project_root / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    _ = (spec / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    coverage = project_root / "tests" / "heading-coverage.json"
    coverage.parent.mkdir(parents=True, exist_ok=True)
    _ = coverage.write_text(
        json.dumps(
            [
                {
                    "spec_root": "SPECIFICATION",
                    "spec_file": "spec.md",
                    "heading": _COVERED,
                    "test": covering_test,
                }
            ]
        ),
        encoding="utf-8",
    )
    module = project_root / "tests" / "integration" / "test_present.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    _ = module.write_text("def test_present_case() -> None:\n    pass\n", encoding="utf-8")


def _detected(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    covering_test: str = _COVERING_TEST,
) -> tuple[list[str], str]:
    """Run the shipped enumerator over a fresh tree, returning its gap ids and stderr."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    _governed_tree(project_root=tmp_path, covering_test=covering_test)

    exit_code = main(argv=["--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload: Any = json.loads(captured.out)
    # The ratified machine surface is a one-key object, and the two doctor
    # invariants subprocess it — so a second key here is a wire-format change
    # for them rather than extra information.
    assert list(payload) == ["gap_ids"]
    return list(payload["gap_ids"]), captured.err


def _filed_record(*, gap_id: str) -> dict[str, Any]:
    """File the detected gap through the real store, and read the row back."""
    item = heading_gap_work_item(
        gap=SpecHeading(
            spec_root="SPECIFICATION",
            spec_file="spec.md",
            heading=_UNCOVERED,
            gap_id=gap_id,
        ),
        prefix=_config().prefix,
        rank="m",
        captured_at=_CAPTURED_AT,
    )
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return cast("dict[str, Any]", client.show_issue(issue_id=item.id))


def test_scenario205_the_uncovered_heading_is_the_one_gap_and_files_naming_its_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One gap for the uncovered heading, none for the covered one, filed under its id."""
    gap_ids, stderr = _detected(tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    # EXACTLY ONE, which is at once "the uncovered heading is a gap", "the
    # covered one is not" and "no MUST or SHOULD clause is enumerated": four
    # clauses sit under that heading, so a clause enumerator reports five.
    assert len(gap_ids) == 1
    # The covered entry resolves, so it carries no finding either — a build
    # surfacing one for every entry would fail here rather than at a gap count.
    assert _COVERING_TEST not in stderr

    record = _filed_record(gap_id=gap_ids[0])

    labels = set(record["labels"])
    # `origin` and `gap_id` are FIELDS on the composed record and become LABELS
    # only when the store writes them, so a record whose fields are right and
    # whose labels never land reads as correct at every in-memory surface —
    # and the labels are what the doctor invariants actually query.
    assert "origin:gap-tied" in labels
    assert f"gap-id:{gap_ids[0]}" in labels
    assert _UNCOVERED in record["title"]
    # The description names the coverage ENTRY to fill, by the registry's own
    # triple, so the remedy is the row an author edits rather than a heading
    # they then have to locate.
    assert "tests/heading-coverage.json" in record["description"]
    assert "SPECIFICATION" in record["description"]
    assert "spec.md" in record["description"]


def test_scenario205_the_same_tree_yields_the_same_gap_id_on_a_second_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The id must be stable, because a label anchors on it across releases.

    The two runs are over SEPARATE trees under separate roots rather than one
    tree read twice, so the id cannot be stable merely because some in-process
    state was reused.
    """
    first, _stderr = _detected(tmp_path=tmp_path / "first", monkeypatch=monkeypatch, capsys=capsys)
    second, _again = _detected(tmp_path=tmp_path / "second", monkeypatch=monkeypatch, capsys=capsys)

    assert first == second


def test_scenario205_an_entry_naming_a_test_that_does_not_exist_is_a_gap_and_a_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A renamed-away test leaves an entry nobody can read as evidence.

    The gap alone would be a CLEAN ABSENCE, indistinguishable from a heading
    nobody ever entered, so the dangling entry is named too — and the control is
    the case above, where the same registry shape with a RESOLVABLE node
    produces neither the gap nor the finding.
    """
    gap_ids, stderr = _detected(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        covering_test=_DANGLING_TEST,
    )

    assert len(gap_ids) == 2
    assert _COVERED in stderr
    assert _DANGLING_TEST in stderr
