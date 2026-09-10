"""Tests for the factory-graph validity gate.

The gate exists because two outages (2026-07-16, 2026-09-09) merged a
`workflow.fabro` whose node had only conditional outgoing edges, and both times
the change carried DOT-structure tests that stood in for an actual
`fabro validate`. So the assertions below never stand in for the engine either:
every one drives the check's own code path against a stub binary that IMPLEMENTS
the `all_conditional_edges` rule, and the decisive test runs the check over this
repository's REAL committed graphs with that stub.

Two stubs, deliberately. The rule-faithful one proves the gate passes a good
graph and fails a bad one; the BLIND one — which exits 0 on anything — proves the
gate's own matcher control catches an instrument that cannot return a hit, which
is the failure mode a check reporting an absence dies of.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "fabro_graph_validity.py"
_BUNDLE = (".claude-plugin", ".fabro", "workflows", "implement-work-item")

# A stub `fabro` that models the ONE rule these outages broke: a node whose every
# outgoing edge carries a condition has no fallthrough and is rejected. Written
# in sh + awk rather than Python so the spawned child never self-instruments
# under `pytest --cov`.
_RULE_FAITHFUL_STUB = """#!/bin/sh
awk '
/^[ \\t]*[A-Za-z_][A-Za-z0-9_]*[ \\t]*->/ {
    total[$1]++
    if ($0 ~ /condition=/) conditional[$1]++
}
END {
    bad = 0
    for (node in total) {
        if (total[node] == conditional[node]) {
            printf "error [node: %s]: no unconditional edge (all_conditional_edges)\\n", node
            bad = 1
        }
    }
    if (bad) { print "Validation failed"; exit 1 }
    print "Validation OK"
}
' "$2"
"""

# A stub that cannot return a hit: it accepts every graph it is handed.
_BLIND_STUB = "#!/bin/sh\nexit 0\n"

_VALID_GRAPH = """digraph Probe {
    start -> a
    a -> b [label="ok", condition="outcome=succeeded"]
    a -> c
    b -> exit
    c -> exit
}
"""

# `a` has only conditional edges, exactly as the merged graphs did. `b` keeps a
# single bracket-free fallthrough so a negative control can still be built.
_INVALID_GRAPH = """digraph Probe {
    start -> a
    a -> b [condition="outcome=succeeded"]
    a -> c [condition="outcome=failed"]
    b -> d [condition="outcome=succeeded"]
    b -> exit
    c -> exit
    d -> exit
}
"""

# Valid, and unmutatable: no node routes conditionally, so no negative control
# exists for it.
_UNMUTATABLE_GRAPH = """digraph Probe {
    start -> a
    a -> exit
}
"""


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fabro_graph_validity", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="check")
def _check() -> ModuleType:
    return _load_check()


def _install_stub(*, root: Path, body: str) -> Path:
    binary = root / "stub-fabro"
    _ = binary.write_text(body, encoding="utf-8")
    binary.chmod(0o755)
    return binary


def _use_stub(*, monkeypatch: pytest.MonkeyPatch, root: Path, body: str) -> Path:
    binary = _install_stub(root=root, body=body)
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(binary))
    monkeypatch.delenv("LIVESPEC_FABRO_GRAPH_VALIDATION", raising=False)
    return binary


def _seed_payload(*, root: Path, graph: str, with_run_config: bool = True) -> Path:
    directory = root.joinpath(*_BUNDLE)
    directory.mkdir(parents=True, exist_ok=True)
    _ = (directory / "workflow.fabro").write_text(graph, encoding="utf-8")
    if with_run_config:
        _ = (directory / "workflow.toml").write_text("[run]\n", encoding="utf-8")
    return directory


def test_this_repositorys_real_graphs_pass_and_their_mutants_are_rejected(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The decisive case: every committed graph, through a rule-faithful engine."""
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)

    found = check.report(repo_root=_REPO_ROOT)

    assert found.findings == []
    assert found.warnings == []


def test_a_graph_the_engine_rejects_is_a_finding_naming_the_payload(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_INVALID_GRAPH)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)

    found = check.report(repo_root=root)

    assert len(found.findings) == 1
    assert "REJECTED workflow.fabro" in found.findings[0]
    assert "all_conditional_edges" in found.findings[0]
    assert found.warnings == []


def test_a_valid_graph_reports_nothing(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)

    assert check.report(repo_root=root).findings == []


def test_an_engine_that_accepts_everything_fails_the_matcher_control(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A blind instrument must fail the control, not certify the graph."""
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_BLIND_STUB)

    findings = check.report(repo_root=root).findings

    assert len(findings) == 1
    assert findings[0].startswith("matcher control:")
    assert "not rejected as such" in findings[0]


def test_a_graph_with_no_mutatable_edge_cannot_be_controlled(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_UNMUTATABLE_GRAPH)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)

    findings = check.report(repo_root=root).findings

    assert len(findings) == 1
    assert "no negative control could be built" in findings[0]


def test_a_half_written_payload_is_named_rather_than_skipped(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH, with_run_config=False)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)

    findings = check.report(repo_root=root).findings

    assert any("completeness control" in finding for finding in findings)


def test_a_payload_directory_without_a_graph_reports_only_its_incompleteness(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    root.joinpath(*_BUNDLE).mkdir(parents=True)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)

    findings = check.report(repo_root=root).findings

    assert len(findings) == 2
    assert all("completeness control" in finding for finding in findings)


def test_an_unenumerated_sibling_graph_is_a_finding(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A graph added beside the bundle without registration must not go unvalidated."""
    root = tmp_path / "repo"
    directory = _seed_payload(root=root, graph=_VALID_GRAPH)
    stray = directory.parent / "smuggled-work-item"
    stray.mkdir()
    _ = (stray / "workflow.fabro").write_text(_INVALID_GRAPH, encoding="utf-8")
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)

    findings = check.report(repo_root=root).findings

    assert len(findings) == 1
    assert findings[0].startswith("enumeration control:")
    assert "smuggled-work-item" in findings[0]


def test_an_absent_binary_warns_loudly_and_does_not_block_by_default(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH)
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(tmp_path / "absent" / "fabro"))
    monkeypatch.delenv("LIVESPEC_FABRO_GRAPH_VALIDATION", raising=False)

    found = check.report(repo_root=root)

    assert found.findings == []
    assert len(found.warnings) == 2
    assert "was NOT validated" in found.warnings[0]
    assert "NO factory graph was validated" in found.warnings[1]


def test_the_lever_can_make_an_absent_binary_fatal(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH)
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(tmp_path / "absent" / "fabro"))
    monkeypatch.setenv("LIVESPEC_FABRO_GRAPH_VALIDATION", check.FAIL_WHEN_ABSENT)

    found = check.report(repo_root=root)

    assert len(found.findings) == 2
    assert found.warnings == []


def test_a_lever_value_outside_the_closed_space_is_a_finding(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A typo must not select a weaker mode."""
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)
    monkeypatch.setenv("LIVESPEC_FABRO_GRAPH_VALIDATION", "warn")

    findings = check.report(repo_root=root).findings

    assert len(findings) == 1
    assert findings[0].startswith("lever control:")


def test_a_bare_binary_name_resolves_through_path(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = _install_stub(root=tmp_path, body=_BLIND_STUB)
    renamed = tmp_path / "myfabro"
    _ = binary.rename(renamed)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "myfabro")

    assert check.resolved_binary(repo_root=tmp_path) == str(renamed)


def test_a_bare_name_that_is_nowhere_on_path_resolves_to_nothing(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "definitely-not-a-real-binary-xyz")

    assert check.resolved_binary(repo_root=tmp_path) is None


def test_a_non_executable_path_resolves_to_nothing(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plain = tmp_path / "not-executable"
    _ = plain.write_text("", encoding="utf-8")
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(plain))

    assert check.resolved_binary(repo_root=tmp_path) is None


def test_mutant_text_skips_edges_that_cannot_carry_the_control(check: ModuleType) -> None:
    """An attributed edge, a node with no conditional sibling, and a node with two
    fallthroughs are each passed over; the first eligible edge is the one rewritten."""
    graph = (
        "digraph Probe {\n"
        '    start -> a [label="attributed"]\n'
        "    two -> x\n"
        "    two -> y\n"
        '    two -> z [condition="outcome=failed"]\n'
        '    good -> p [condition="outcome=failed"]\n'
        "    good -> q\n"
        "}\n"
    )

    mutated = check.mutant_text(text=graph)

    assert mutated is not None
    assert '    good -> q [condition="outcome=succeeded"]' in mutated
    assert "    two -> x\n" in mutated


def test_main_exits_zero_on_a_clean_repository(
    check: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)
    monkeypatch.chdir(root)

    assert check.main() == 0
    assert capsys.readouterr().err == ""


def test_main_exits_one_and_logs_every_finding(
    check: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_INVALID_GRAPH)
    _use_stub(monkeypatch=monkeypatch, root=tmp_path, body=_RULE_FAITHFUL_STUB)
    monkeypatch.chdir(root)

    assert check.main() == 1
    assert "all_conditional_edges" in capsys.readouterr().err


def test_main_logs_the_absence_at_error_level_while_exiting_zero(
    check: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The skip is loud: exit 0, but the record says the graphs were never looked at."""
    root = tmp_path / "repo"
    _seed_payload(root=root, graph=_VALID_GRAPH)
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(tmp_path / "absent" / "fabro"))
    monkeypatch.delenv("LIVESPEC_FABRO_GRAPH_VALIDATION", raising=False)
    monkeypatch.chdir(root)

    assert check.main() == 0
    captured = capsys.readouterr().err
    assert "NO factory graph was validated" in captured
    assert '"level": "error"' in captured
