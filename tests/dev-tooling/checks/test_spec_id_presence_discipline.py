"""Tests for the overloaded-spec-id presence-test guard.

The guard reports an ABSENCE, so this module carries the two controls the
work-item makes non-optional:

- a POSITIVE CONTROL over a checked-in fixture that the check is REQUIRED to
  find, so a broken pattern or a mis-scoped walk cannot masquerade as a clean
  repo;
- a NEGATIVE CONTROL that reintroduces a presence test at a REAL call site and
  PROVES its own mutation landed — by reading the mutated file back off disk
  and asserting on its content — before asserting the check fired.

Every recorded result below is verified by reading the persisted artifact back
and asserting on its content; no assertion is made against the return value of
a write call.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "spec_id_presence_discipline.py"
_PACKAGE_RELPATH = (".claude-plugin", "scripts", "livespec_orchestrator_beads_fabro")

# The real call site the negative control mutates, and the correct predicate it
# replaces with the attractive wrong one.
_MUTATION_TARGET = "commands/_dispatcher_calibration.py"
_CORRECT_PREDICATE = "is_spec_commitment(spec_id=item.spec_commitment_hint)"
_WRONG_PREDICATE = "item.spec_commitment_hint is not None"


def _load_check() -> ModuleType:
    assert _CHECK_PATH.is_file()
    spec = importlib.util.spec_from_file_location(
        "spec_id_presence_discipline_under_test",
        _CHECK_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="check")
def _check_fixture() -> ModuleType:
    return _load_check()


def _seed_package(*, repo_root: Path, relpaths: tuple[str, ...]) -> Path:
    """Copy real package modules into a throwaway repo root, preserving layout."""
    source_package = _REPO_ROOT.joinpath(*_PACKAGE_RELPATH)
    target_package = repo_root.joinpath(*_PACKAGE_RELPATH)
    for relpath in relpaths:
        target = target_package / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(source_package / relpath, target)
    return target_package


def _seed_fixture(*, repo_root: Path, check: ModuleType) -> Path:
    source = check.fixture_path(repo_root=_REPO_ROOT)
    target = check.fixture_path(repo_root=repo_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(source, target)
    return target


# ---------------------------------------------------------------------------
# The package as it stands.
# ---------------------------------------------------------------------------


def test_the_check_is_installed_where_the_justfile_target_invokes_it() -> None:
    assert _CHECK_PATH.is_file()


def test_package_carries_no_unallowed_presence_test(check: ModuleType) -> None:
    assert check.unallowed_findings(repo_root=_REPO_ROOT) == []


def test_controls_hold_against_the_real_repo(check: ModuleType) -> None:
    assert check.control_failures(repo_root=_REPO_ROOT) == []


def test_main_passes_against_the_real_repo(
    check: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(_REPO_ROOT)

    assert check.main() == 0


# ---------------------------------------------------------------------------
# The allowlist is measured, not guessed.
# ---------------------------------------------------------------------------


def test_every_allowlist_entry_is_a_site_that_actually_fires(check: ModuleType) -> None:
    firing = {finding.relpath for finding in check.package_findings(repo_root=_REPO_ROOT)}

    assert sorted(check.ALLOWLIST - firing) == []


def test_allowlist_omits_sites_measured_not_to_need_it(check: ModuleType) -> None:
    firing = {finding.relpath for finding in check.package_findings(repo_root=_REPO_ROOT)}

    # `store.py` reads the column through an optional-string accessor and
    # `list_work_items.py` compares it for equality against a caller-supplied
    # filter value. Neither is a presence test, so neither may be allowlisted.
    assert "store.py" not in firing
    assert "store.py" not in check.ALLOWLIST
    assert "commands/list_work_items.py" not in firing
    assert "commands/list_work_items.py" not in check.ALLOWLIST


def test_discovery_anchors_are_reached_by_the_package_walk(check: ModuleType) -> None:
    root = check.package_dir(repo_root=_REPO_ROOT)
    walked = {path.relative_to(root).as_posix() for path in check.module_paths(root=root)}

    assert set(check.DISCOVERY_ANCHORS) <= walked


# ---------------------------------------------------------------------------
# The walk reads a LIVE tree, so it must tolerate that tree changing.
# ---------------------------------------------------------------------------


class _ListedEntries:
    """A `scandir` result whose entries were listed BEFORE the directory changed.

    Listing eagerly is what makes the race deterministic: the walk receives a
    directory entry that existed a moment ago and is gone by the time it opens
    it, which is exactly the sequence the live `__pycache__` hit.
    """

    def __init__(self, *, entries: list[os.DirEntry[str]]) -> None:
        self._entries = iter(entries)

    def __next__(self) -> os.DirEntry[str]:
        return next(self._entries)

    def __enter__(self) -> _ListedEntries:
        return self

    def __exit__(self, *_details: object) -> None:
        return None


def _scandir_removing(
    *,
    doomed: Path,
    removed: list[Path],
) -> Callable[[Path | str], _ListedEntries | Iterator[os.DirEntry[str]]]:
    """A `scandir` that deletes `doomed` the moment its parent is listed.

    The production race is a concurrent process removing a directory between
    the walk listing it and the walk opening it. Reproducing that by timing
    would be flaky, so it is driven off the walk's own `scandir` call instead:
    the removal is appended to `removed`, which lets the test PROVE the vanish
    fired during collection rather than trusting that it did.
    """
    real = os.scandir

    def hooked(path: Path | str) -> _ListedEntries | Iterator[os.DirEntry[str]]:
        entries = real(path)
        if str(path) != str(doomed.parent):
            return entries
        with entries:
            listed = list(entries)
        shutil.rmtree(doomed)
        removed.append(doomed)
        return _ListedEntries(entries=listed)

    return hooked


def _seed_walk_tree(*, root: Path, throwaway: str) -> Path:
    """Two modules, one non-module file, and a throwaway directory holding a third."""
    (root / "commands").mkdir(parents=True)
    _ = (root / "store.py").write_text("", encoding="utf-8")
    _ = (root / "commands" / "_plan_anchor.py").write_text("", encoding="utf-8")
    _ = (root / "commands" / "CLAUDE.md").write_text("", encoding="utf-8")
    doomed = root / "commands" / throwaway
    doomed.mkdir()
    _ = (doomed / "stale.py").write_text("", encoding="utf-8")
    return doomed


def test_module_paths_skips_pycache_directories(check: ModuleType, tmp_path: Path) -> None:
    # The pruning arm ISOLATED, with nothing vanishing: a `.py` under
    # `__pycache__` is never a scanned module, and the walk must not descend
    # there at all — that descent is the one that races.
    root = tmp_path / "package"
    doomed = _seed_walk_tree(root=root, throwaway="__pycache__")

    walked = {path.relative_to(root).as_posix() for path in check.module_paths(root=root)}

    assert doomed.is_dir()
    assert walked == {"store.py", "commands/_plan_anchor.py"}


def test_module_paths_survives_a_pycache_vanishing_mid_walk(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Master run 34530040885 went red on a pure version bump because a
    # concurrently-removed `__pycache__` raised `FileNotFoundError` out of the
    # walk. A `FileNotFoundError` escaping this call is that failure.
    root = tmp_path / "package"
    doomed = _seed_walk_tree(root=root, throwaway="__pycache__")
    removed: list[Path] = []
    monkeypatch.setattr(os, "scandir", _scandir_removing(doomed=doomed, removed=removed))

    walked = {path.relative_to(root).as_posix() for path in check.module_paths(root=root)}

    # PROOF THE VANISH LANDED, and landed DURING collection: without it this
    # test would pass by never exercising the race, printing exactly the green
    # a tolerant walk prints.
    assert removed == [doomed]
    assert not doomed.exists()
    assert walked == {"store.py", "commands/_plan_anchor.py"}


def test_module_paths_returns_the_remaining_modules_when_a_directory_vanishes_mid_walk(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The tolerance arm ISOLATED: an ORDINARY directory vanishes, so pruning
    # cannot account for the pass. The walk must drop the subtree it can no
    # longer open and still report every module it did reach.
    root = tmp_path / "package"
    doomed = _seed_walk_tree(root=root, throwaway="nested")
    removed: list[Path] = []
    monkeypatch.setattr(os, "scandir", _scandir_removing(doomed=doomed, removed=removed))

    walked = {path.relative_to(root).as_posix() for path in check.module_paths(root=root)}

    assert removed == [doomed]
    assert not doomed.exists()
    assert walked == {"store.py", "commands/_plan_anchor.py"}


# ---------------------------------------------------------------------------
# POSITIVE CONTROL — the fixture the check is required to find.
# ---------------------------------------------------------------------------


def test_positive_control_fixture_holds_bare_presence_tests_not_mere_mentions(
    check: ModuleType,
) -> None:
    fixture = check.fixture_path(repo_root=_REPO_ROOT)
    persisted = fixture.read_text(encoding="utf-8")

    # Read back off disk and asserted on by CONTENT: the fixture must carry
    # real presence tests, not merely name the field.
    assert "item.spec_commitment_hint is not None" in persisted
    assert "bool(item.spec_commitment_hint)" in persisted
    # The two idiomatic shapes a first cut of the matcher let through. They
    # are in the CONTROL so a regression of that fix fails here, not silently.
    assert "hint: str | None = item.spec_commitment_hint" in persisted
    assert "if inline := item.spec_id:" in persisted
    findings = check.path_findings(paths=[fixture], root=fixture.parent)
    assert {finding.form for finding in findings} == {
        "bool-call",
        "none-comparison",
        "truthiness",
    }
    assert "(inline := item.spec_id)" in {finding.expression for finding in findings}


def test_positive_control_fails_the_build_when_the_matcher_reports_no_hit(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _seed_package(repo_root=tmp_path, relpaths=check.DISCOVERY_ANCHORS)
    blinded = check.fixture_path(repo_root=tmp_path)
    blinded.parent.mkdir(parents=True, exist_ok=True)
    _ = blinded.write_text('"""A fixture that mentions spec_id and tests nothing."""\n', "utf-8")
    monkeypatch.chdir(tmp_path)

    # Read the persisted fixture back: it names the field, so a name-only
    # instrument would still be satisfied; the check must not be.
    assert "spec_id" in blinded.read_text(encoding="utf-8")
    assert [
        failure for failure in check.control_failures(repo_root=tmp_path) if "matcher" in failure
    ]
    assert check.main() == 1


def test_positive_control_fails_the_build_when_the_fixture_is_missing(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _seed_package(repo_root=tmp_path, relpaths=check.DISCOVERY_ANCHORS)
    monkeypatch.chdir(tmp_path)

    assert not check.fixture_path(repo_root=tmp_path).exists()
    assert check.main() == 1


def test_discovery_control_fails_when_the_walk_misses_an_anchor(
    check: ModuleType,
    tmp_path: Path,
) -> None:
    _ = _seed_package(repo_root=tmp_path, relpaths=("store.py",))
    _ = _seed_fixture(repo_root=tmp_path, check=check)

    failures = check.control_failures(repo_root=tmp_path)

    assert [failure for failure in failures if "commands/_plan_anchor.py" in failure]
    assert not [failure for failure in failures if "matcher" in failure]


# ---------------------------------------------------------------------------
# NEGATIVE CONTROL — a real call site, mutated, with proof the mutation landed.
# ---------------------------------------------------------------------------


def test_negative_control_catches_a_presence_test_reintroduced_at_a_real_call_site(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _seed_package(
        repo_root=tmp_path,
        relpaths=(*check.DISCOVERY_ANCHORS, _MUTATION_TARGET),
    )
    _ = _seed_fixture(repo_root=tmp_path, check=check)
    mutated = package / _MUTATION_TARGET
    before = mutated.read_text(encoding="utf-8")

    _ = mutated.write_text(before.replace(_CORRECT_PREDICATE, _WRONG_PREDICATE), encoding="utf-8")

    # PROOF THE MUTATION LANDED, read back off disk — a replace that silently
    # matched nothing would leave a byte-identical file and produce exactly the
    # green a working guard produces.
    after = mutated.read_text(encoding="utf-8")
    assert after != before
    assert after.count(_WRONG_PREDICATE) == 1
    assert _CORRECT_PREDICATE not in after

    # Only now is the guard's verdict evidence of anything.
    findings = check.unallowed_findings(repo_root=tmp_path)
    assert [(finding.relpath, finding.form) for finding in findings] == [
        (_MUTATION_TARGET, "none-comparison")
    ]
    assert check.control_failures(repo_root=tmp_path) == []
    monkeypatch.chdir(tmp_path)
    assert check.main() == 1


def test_unmutated_seed_of_the_same_call_site_is_clean(
    check: ModuleType,
    tmp_path: Path,
) -> None:
    # The negative control's own control: the identical seed, unmutated, must
    # pass — otherwise the finding above would prove nothing about the edit.
    package = _seed_package(
        repo_root=tmp_path,
        relpaths=(*check.DISCOVERY_ANCHORS, _MUTATION_TARGET),
    )
    _ = _seed_fixture(repo_root=tmp_path, check=check)

    assert _CORRECT_PREDICATE in (package / _MUTATION_TARGET).read_text(encoding="utf-8")
    assert check.unallowed_findings(repo_root=tmp_path) == []


# ---------------------------------------------------------------------------
# Matcher behaviour.
# ---------------------------------------------------------------------------


def test_matcher_recognises_every_presence_form(check: ModuleType) -> None:
    source = "\n".join(
        [
            "def probe(*, item, record):",
            "    if item.spec_commitment_hint is not None:",
            "        return 1",
            "    if None == record['spec_id']:",
            "        return 2",
            "    if bool(record.get('spec_commitment_hint')):",
            "        return 3",
            "    alias = item.spec_id",
            "    if not alias:",
            "        return 4",
            "    while alias:",
            "        break",
            "    assert alias",
            "    filtered = [row for row in record if item.spec_id]",
            "    ternary = 5 if item.spec_id else 6",
            "    if (walrus := record.get('spec_id')) and walrus:",
            "        return 7",
            "    return len(filtered) + ternary",
            "",
        ]
    )

    findings = check.source_findings(source=source, relpath="probe.py")

    assert [(finding.lineno, finding.form) for finding in findings] == [
        (2, "none-comparison"),
        (4, "none-comparison"),
        (6, "bool-call"),
        (9, "truthiness"),
        (11, "truthiness"),
        (13, "truthiness"),
        (14, "truthiness"),
        (15, "truthiness"),
        # Both halves of the boolean fire: the walrus itself reads the field,
        # and `walrus` is an alias of that read.
        (16, "truthiness"),
        (16, "truthiness"),
    ]


def test_matcher_catches_an_annotated_alias_and_a_walrus_read(check: ModuleType) -> None:
    # Two forms a reviewer measured as escaping the first cut of the matcher.
    # An ANNOTATED assignment is the idiomatic way to alias a `str | None`
    # field, and a WALRUS reads the field inline; either reintroduces a bare
    # presence test in a shape the original scan reported as clean.
    source = "\n".join(
        [
            "def probe(*, item, record):",
            "    annotated: str | None = item.spec_commitment_hint",
            "    if annotated is not None:",
            "        return 1",
            "    declared: str | None",
            "    if (hint := item.spec_id):",
            "        return 2",
            "    if (subscripted := record['spec_id']) is None:",
            "        return 3",
            "    if bool(walrus := item.spec_id):",
            "        return 4",
            "    return declared",
            "",
        ]
    )

    findings = check.source_findings(source=source, relpath="probe.py")

    assert [(finding.lineno, finding.form, finding.expression) for finding in findings] == [
        (3, "none-comparison", "annotated is not None"),
        (6, "truthiness", "(hint := item.spec_id)"),
        (8, "none-comparison", "(subscripted := record['spec_id']) is None"),
        (10, "bool-call", "bool((walrus := item.spec_id))"),
    ]


def test_matcher_ignores_reads_that_are_not_presence_tests(check: ModuleType) -> None:
    source = "\n".join(
        [
            '"""Prose naming spec_id and spec_commitment_hint is invisible."""',
            "def probe(*, item, record, wanted):",
            "    # A comment testing item.spec_id is not None is invisible too.",
            "    equality = item.spec_commitment_hint == wanted",
            "    chained = wanted < item.spec_id < record",
            "    ordered = item.spec_id < wanted",
            "    unrelated = record['gap_id']",
            "    other_get = record.get('gap_id')",
            "    payload = {'spec_id': item.spec_commitment_hint}",
            "    if item.gap_id is not None:",
            "        return payload",
            "    if record:",
            "        return equality",
            "    return [chained, ordered, unrelated, other_get]",
            "",
        ]
    )

    assert check.source_findings(source=source, relpath="probe.py") == []


def test_matcher_ignores_an_alias_of_something_other_than_the_field(check: ModuleType) -> None:
    source = "\n".join(
        [
            "def probe(*, item):",
            "    hint = item.gap_id",
            "    annotated: str | None = item.gap_id",
            "    first, second = item.spec_id, item.gap_id",
            "    if hint or annotated:",
            "        return first",
            "    return second",
            "",
        ]
    )

    assert check.source_findings(source=source, relpath="probe.py") == []


def test_findings_carry_the_unparsed_expression_and_sort_stably(check: ModuleType) -> None:
    source = "\n".join(
        [
            "def probe(*, item):",
            "    return bool(item.spec_id) or item.spec_commitment_hint is None",
            "",
        ]
    )

    findings = check.source_findings(source=source, relpath="probe.py")

    assert [(finding.form, finding.expression) for finding in findings] == [
        ("bool-call", "bool(item.spec_id)"),
        ("none-comparison", "item.spec_commitment_hint is None"),
    ]
    assert {finding.relpath for finding in findings} == {"probe.py"}
