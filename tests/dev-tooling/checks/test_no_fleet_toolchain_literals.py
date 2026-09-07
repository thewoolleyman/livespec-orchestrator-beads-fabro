"""Tests for the fleet-toolchain literal ban.

The variant cases seed a throwaway root carrying a real `dispatcher.workflows`
table: one registered directory conformant, one carrying a fleet literal. The
assertion that matters is that the finding names THAT directory while the bundle
beside it still scans clean, which no single-payload gate could produce.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "no_fleet_toolchain_literals.py"

_PACKAGE_RELPATH = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro"
_PAYLOAD_RELPATH = ".claude-plugin/.fabro/workflows/implement-work-item"
_GROOM_VARIANT_RELPATH = ".fabro/workflows/groom-work-item"
_FIXTURE_RELPATH = "dev-tooling/checks/fixtures/fleet_toolchain_literal_control.py.txt"
_CONFORMANT_PAYLOAD = 'script = "uv sync"\n'
_SCHEMA_SOURCE = (
    "from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (\n"
    "    MERGE_MODE_DEFAULT,\n"
    ")\n"
    "\n"
    "DEFAULT = MERGE_MODE_DEFAULT\n"
)


def _load_check() -> ModuleType:
    assert _CHECK_PATH.is_file()
    spec = importlib.util.spec_from_file_location(
        "no_fleet_toolchain_literals_under_test",
        _CHECK_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_matcher() -> ModuleType:
    """The sibling matcher, as the check itself resolved it."""
    _ = _load_check()
    return sys.modules["_fleet_toolchain_literals_matcher"]


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _write_workflow(*, directory: Path, config: str = _CONFORMANT_PAYLOAD) -> None:
    """A COMPLETE workflow directory: the two files the completeness control requires."""
    _write(path=directory / "workflow.toml", text=config)
    _write(path=directory / "workflow.fabro", text='digraph Variant { start [label="Start"] }\n')


def _register_variants(*, root: Path, variants: dict[str, str]) -> None:
    """Declare a `dispatcher.workflows` table in the synthetic root's config."""
    entries = ", ".join(f'"{name}": "{declared}"' for name, declared in variants.items())
    _write(
        path=root / ".livespec.jsonc",
        text=(
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
            f'{{"workflows": {{{entries}}}}}}}}}\n'
        ),
    )


def _conforming_repo(*, root: Path, check: ModuleType) -> None:
    """A synthetic tree every positive control passes against."""
    package = root / _PACKAGE_RELPATH
    for anchor in check.DISCOVERY_ANCHORS:
        _write(path=package / anchor, text="VALUE = 1\n")
    _write(path=package / check.SCHEMA_MODULE, text=_SCHEMA_SOURCE)
    _write_workflow(directory=root / _PAYLOAD_RELPATH)
    _write(path=root / _FIXTURE_RELPATH, text='ARGV = ["mise", "exec"]\n')


def test_the_repository_carries_no_fleet_toolchain_literal_at_all() -> None:
    """The realized ban: no residue in the package, and nothing excusing one either."""
    check = _load_check()

    assert check.all_findings(repo_root=_REPO_ROOT) == []
    assert check.package_findings(repo_root=_REPO_ROOT) == []
    assert check.control_failures(repo_root=_REPO_ROOT) == []


def test_the_gate_carries_no_allow_list_of_any_kind() -> None:
    """The C7 deletion, asserted on the gate's OWN surface rather than on prose.

    The retired names are checked one at a time rather than by scanning for a
    keyword: a `hasattr` on a name that never existed passes for the wrong
    reason, so each name asserted here is one this module genuinely used to
    export. `MEASURED_EXEMPTIONS` and its stale-entry control were the package
    half; `PAYLOAD_ALLOWLIST` was the payload half, retired earlier.
    """
    check = _load_check()
    retired = (
        "MEASURED_EXEMPTIONS",
        "PAYLOAD_ALLOWLIST",
        "stale_exemptions",
        "unexempted_findings",
    )

    assert [name for name in retired if hasattr(check, name)] == []
    assert [name for name in check.__all__ if name in retired] == []
    # The scan's ONE skip is the module the schema designates, and it is named by
    # the schema rather than listed here, which is what the designation control
    # below keeps honest.
    assert check.FLEET_DEFAULTS_MODULE == "commands/_dispatcher_integration_defaults.py"


def test_main_passes_on_the_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    check = _load_check()
    monkeypatch.chdir(_REPO_ROOT)

    assert check.main() == 0


def test_source_findings_flag_argv_and_shell_command_literals() -> None:
    matcher = _load_matcher()

    findings = matcher.source_findings(
        source="\n".join(
            [
                'ARGV = ["mise", "exec", "--", "just", "check"]',
                'SHELL = ["sh", "-lc", "lefthook install"]',
                'MODULE = "livespec_dev_tooling"',
                'TIMER = "livespec-step-timer"',
                'REF = "refs/heads/master"',
                'BRANCH = "main"',
                "",
            ]
        ),
        relpath="commands/_dispatcher_probe.py",
    )

    assert [(finding.lineno, finding.token, finding.literal) for finding in findings] == [
        (1, "just", "just"),
        (1, "mise", "mise"),
        (2, "lefthook", "lefthook install"),
        (3, "livespec_dev_tooling", "livespec_dev_tooling"),
        (4, "livespec-step-timer", "livespec-step-timer"),
        (5, "master", "refs/heads/master"),
        (6, "main", "main"),
    ]


def test_source_findings_skip_docstrings_all_entries_and_prose() -> None:
    matcher = _load_matcher()

    assert (
        matcher.source_findings(
            source="\n".join(
                [
                    '"""The janitor no longer prepends this fleet\'s mise exec -- wrapper."""',
                    "",
                    "from __future__ import annotations",
                    "",
                    '__all__: list[str] = ["main"]',
                    "",
                    "",
                    "class Empty:",
                    "    VALUE = 1",
                    "",
                    "",
                    "def main() -> int:",
                    '    reason = "the checkout is not on master and lefthook never ran"',
                    "    number = 1",
                    "    return len(reason) + number",
                    "",
                ]
            ),
            relpath="commands/_dispatcher_prose.py",
        )
        == []
    )
    assert (
        matcher.source_findings(
            source='__all__ = ["main"]\n',
            relpath="commands/_dispatcher_unannotated_all.py",
        )
        == []
    )
    assert matcher.source_findings(source="", relpath="commands/_empty.py") == []


def test_literal_token_reads_only_the_token_and_ref_shapes() -> None:
    matcher = _load_matcher()

    assert matcher.literal_token(literal="  mise  ") == "mise"
    assert matcher.literal_token(literal="mise exec -- just check") == "mise"
    assert matcher.literal_token(literal='branch="x"; just check') == "just"
    assert matcher.literal_token(literal="sh -c lefthook install") == "lefthook"
    assert matcher.literal_token(literal="origin/master") == "master"
    assert matcher.literal_token(literal="refs/remotes/origin/main") == "main"
    assert matcher.literal_token(literal="run the mise wrapper on master first") is None
    assert matcher.literal_token(literal="mistress") is None


def test_text_token_matches_whole_words_and_only_command_position_just() -> None:
    matcher = _load_matcher()

    assert matcher.text_token(line='    script = "mise exec -- just check"') == "mise"
    assert matcher.text_token(line="  it is just a prompt sentence about the branch") is None
    assert matcher.text_token(line="just check-coverage") == "just"
    assert matcher.text_token(line="master") == "master"
    assert matcher.text_token(line="a plain prompt line") is None


def test_text_findings_report_one_finding_per_carrying_line() -> None:
    matcher = _load_matcher()

    findings = matcher.text_findings(
        text="prose only\nrun lefthook install\n",
        relpath=".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml",
    )

    assert [(finding.lineno, finding.token) for finding in findings] == [(2, "lefthook")]


def test_package_findings_skip_the_fleet_defaults_module(tmp_path: Path) -> None:
    check = _load_check()
    package = tmp_path / _PACKAGE_RELPATH
    _write(path=package / check.FLEET_DEFAULTS_MODULE, text='ARGV = ["mise", "trust"]\n')
    _write(path=package / "commands/_dispatcher_other.py", text='ARGV = ["mise", "trust"]\n')

    findings = check.package_findings(repo_root=tmp_path)

    assert [finding.relpath for finding in findings] == ["commands/_dispatcher_other.py"]


def test_payload_paths_select_only_payload_suffixes(tmp_path: Path) -> None:
    check = _load_check()
    payload = tmp_path / _PAYLOAD_RELPATH
    _write(path=payload / "workflow.fabro", text="node\n")
    _write(path=payload / "prompts/implement.md", text="prose\n")
    _write(path=payload / "notes.txt", text="ignored\n")

    assert [path.name for path in check.payload_paths(repo_root=tmp_path)] == [
        "implement.md",
        "workflow.fabro",
    ]


def test_all_findings_excuse_nothing_in_either_tree(tmp_path: Path) -> None:
    """The site that USED to be excused is a finding now, and reads like any other.

    `_dispatcher_fabro_argv.py` is deliberately the probe: it carried the largest
    measured residue and its exemption was the first entry of the retired list,
    so a leftover allow-list would show up here as that one file going missing
    from the findings while its unmeasured sibling reported normally.
    """
    check = _load_check()
    package = tmp_path / _PACKAGE_RELPATH
    _write(path=package / "commands/_dispatcher_fabro_argv.py", text='ARGV = ["mise"]\n')
    _write(path=package / "commands/_dispatcher_new.py", text='ARGV = ["mise"]\n')
    payload = f"{_PAYLOAD_RELPATH}/workflow.toml"
    _write(path=tmp_path / payload, text="run lefthook install\n")

    findings = check.all_findings(repo_root=tmp_path)

    assert [finding.relpath for finding in findings] == [
        "commands/_dispatcher_fabro_argv.py",
        "commands/_dispatcher_new.py",
        payload,
    ]


def test_control_failures_report_an_unwalked_tree_and_a_missing_fixture(tmp_path: Path) -> None:
    check = _load_check()

    failures = check.control_failures(repo_root=tmp_path)

    assert (
        sum("discovery control" in failure for failure in failures)
        == len(check.DISCOVERY_ANCHORS) + 1
    )
    assert any("designation control" in failure for failure in failures)
    assert any("the positive-control fixture is missing" in failure for failure in failures)


def test_control_failures_report_a_schema_that_designates_nothing(tmp_path: Path) -> None:
    check = _load_check()
    _conforming_repo(root=tmp_path, check=check)
    _write(path=tmp_path / _PACKAGE_RELPATH / check.SCHEMA_MODULE, text="VALUE = 1\n")

    failures = check.control_failures(repo_root=tmp_path)

    assert [failure for failure in failures if "designation control" in failure] != []


def test_control_failures_report_a_fixture_that_produces_no_finding(tmp_path: Path) -> None:
    check = _load_check()
    _conforming_repo(root=tmp_path, check=check)
    _write(path=tmp_path / _FIXTURE_RELPATH, text='REASON = "prose about mise only"\n')

    failures = check.control_failures(repo_root=tmp_path)

    assert [failure for failure in failures if "no fleet-toolchain literal was found" in failure]


def test_control_failures_are_empty_for_a_conforming_tree(tmp_path: Path) -> None:
    check = _load_check()
    _conforming_repo(root=tmp_path, check=check)

    assert check.control_failures(repo_root=tmp_path) == []


def test_main_returns_nonzero_when_a_positive_control_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = _load_check()
    monkeypatch.chdir(tmp_path)

    assert check.main() == 1


def test_main_returns_nonzero_for_a_reintroduced_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = _load_check()
    _conforming_repo(root=tmp_path, check=check)
    _write(
        path=tmp_path / _PACKAGE_RELPATH / "commands/_dispatcher_new.py",
        text='ARGV = ["mise", "exec", "--", "just", "check"]\n',
    )
    monkeypatch.chdir(tmp_path)

    assert check.main() == 1


# ---------------------------------------------------------------------------
# Every REGISTERED variant is scanned, and every finding names its directory.
# ---------------------------------------------------------------------------


def test_the_repositorys_registered_variant_is_scanned_beside_the_bundle() -> None:
    """The real registry reaches the real scan, and the scan reaches nothing else.

    Both halves matter and they fail in opposite directions. If the registry
    were ignored, the groom variant's files would be absent from the walk and a
    fleet literal committed there would never be found; if the walk strayed
    outside the declared directories, findings would be reported against files
    no registry entry names.
    """
    check = _load_check()
    declared = {
        payload.where
        for payload in sys.modules["_checked_workflow_payloads"].checked_payloads(
            repo_root=_REPO_ROOT
        )
    }

    assert declared == {_PAYLOAD_RELPATH, _GROOM_VARIANT_RELPATH}

    walked = [
        path.relative_to(_REPO_ROOT).as_posix()
        for path in check.payload_paths(repo_root=_REPO_ROOT)
    ]

    # The instrument must be able to return a hit before its scope claim means
    # anything: both directories really do contribute files to the walk.
    assert any(path.startswith(f"{_PAYLOAD_RELPATH}/") for path in walked)
    assert any(path.startswith(f"{_GROOM_VARIANT_RELPATH}/") for path in walked)
    assert all(any(path.startswith(f"{where}/") for where in declared) for path in walked)


def test_a_registered_variant_with_a_fleet_literal_fails_while_the_bundle_passes(
    tmp_path: Path,
) -> None:
    check = _load_check()
    _conforming_repo(root=tmp_path, check=check)
    _register_variants(
        root=tmp_path,
        variants={"conformant": "variants/conformant", "literal": "variants/literal"},
    )
    _write_workflow(directory=tmp_path / "variants/conformant")
    _write_workflow(directory=tmp_path / "variants/literal", config='script = "mise exec -- x"\n')

    findings = check.payload_findings(repo_root=tmp_path)

    # The bundle and the conformant variant are the controls: the scan reached
    # all three directories, and only the one carrying the literal reports.
    assert len(check.payload_paths(repo_root=tmp_path)) == 6
    assert [(finding.relpath, finding.token) for finding in findings] == [
        ("variants/literal/workflow.toml", "mise")
    ]
    assert check.control_failures(repo_root=tmp_path) == []


def test_a_registered_variant_that_scans_to_nothing_fails_rather_than_reporting_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check = _load_check()
    _conforming_repo(root=tmp_path, check=check)
    _register_variants(root=tmp_path, variants={"absent": "variants/absent"})
    monkeypatch.chdir(tmp_path)

    failures = check.control_failures(repo_root=tmp_path)

    assert not (tmp_path / "variants" / "absent").exists()
    # Per directory: the missing variant fails its own controls while the
    # bundle standing beside it reports neither, and the scan is not clean.
    assert failures == [
        "completeness control: variants/absent: the directory has no workflow.fabro, "
        "so it is not a complete workflow",
        "completeness control: variants/absent: the directory has no workflow.toml, "
        "so it is not a complete workflow",
        "discovery control: the walk of variants/absent reached no file",
    ]
    assert check.payload_findings(repo_root=tmp_path) == []
    assert check.main() == 1


def test_an_incomplete_registered_variant_is_a_finding_naming_that_directory(
    tmp_path: Path,
) -> None:
    check = _load_check()
    _conforming_repo(root=tmp_path, check=check)
    _register_variants(root=tmp_path, variants={"partial": "variants/partial"})
    _write(path=tmp_path / "variants/partial/workflow.fabro", text="digraph P { a }\n")

    failures = check.control_failures(repo_root=tmp_path)

    assert not (tmp_path / "variants/partial/workflow.toml").exists()
    # A half-written directory still WALKS to a file, so the discovery control
    # is satisfied and the completeness control is the one that must fire.
    assert check.payload_paths(repo_root=tmp_path) != []
    assert failures == [
        "completeness control: variants/partial: the directory has no workflow.toml, "
        "so it is not a complete workflow"
    ]
