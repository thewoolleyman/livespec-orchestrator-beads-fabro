"""Tests for the `orchestrator` contract CLI (spec-reader / gap-capture / drift-capture).

Per livespec/SPECIFICATION/contracts.md §"Orchestrator CLI contract —
the three named CLIs" and §"CLI shape conventions". The hermetic
`FakeBeadsClient` is the backend (autouse fixture sets
`LIVESPEC_BEADS_FAKE=1` and resets the singleton); injected reference
CLIs are exercised through real subprocesses built from
`sys.executable -c` stubs.
"""

import io
import json
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import (
    CliContext,
    InjectedCliError,
    PayloadInvalidError,
    PayloadMissingError,
    load_payload,
    parse_cli_argv,
    require_str,
    resolve_spec_version,
)
from livespec_orchestrator_beads_fabro.commands.orchestrator import main
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _stored_items() -> list[WorkItem]:
    return list(materialize_work_items(records=read_work_items(path=_config())).values())


def _make_spec_tree(*, root: Path) -> Path:
    spec = root / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    (spec / "history" / "v002").mkdir()
    (spec / "proposed_changes").mkdir()
    _ = (spec / "spec.md").write_text("# Spec\n", encoding="utf-8")
    _ = (spec / "contracts.md").write_text("# Contracts\n", encoding="utf-8")
    (spec / "research").mkdir()
    _ = (spec / "research" / "notes.md").write_text("notes\n", encoding="utf-8")
    _ = (spec / "proposed_changes" / "pending.md").write_text("pending\n", encoding="utf-8")
    return spec


def _fake_spec_reader_cli(*, version: object) -> list[str]:
    code = f"import json, sys; sys.stdout.write(json.dumps({{'version': {version!r}}}))"
    return [sys.executable, "-c", code]


def _recorder_propose_change_cli(*, record_path: Path, exit_code: int = 0) -> list[str]:
    code = (
        "import json, pathlib, sys\n"
        f"out = pathlib.Path({str(record_path)!r})\n"
        "findings = None\n"
        "if '--findings-json' in sys.argv:\n"
        "    findings_path = sys.argv[sys.argv.index('--findings-json') + 1]\n"
        "    findings = pathlib.Path(findings_path).read_text(encoding='utf-8')\n"
        "out.write_text(json.dumps({'argv': sys.argv[1:], 'findings': findings}))\n"
        "sys.stderr.write('recorder narration')\n"
        f"sys.exit({exit_code})\n"
    )
    return [sys.executable, "-c", code]


def _gaps_payload_file(*, root: Path, gaps: list[dict[str, object]]) -> Path:
    path = root / "gaps.json"
    _ = path.write_text(json.dumps({"gaps": gaps}), encoding="utf-8")
    return path


def _drifts_payload_file(*, root: Path, drifts: list[dict[str, object]]) -> Path:
    path = root / "drifts.json"
    _ = path.write_text(json.dumps({"drifts": drifts}), encoding="utf-8")
    return path


def _drift(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "topic": "drift-topic",
        "name": "Drift proposal",
        "target_spec_files": ["SPECIFICATION/contracts.md"],
        "summary": "summary prose",
        "motivation": "motivation prose",
        "proposed_changes": "change prose",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Parser surface
# ---------------------------------------------------------------------------


def test_main_without_subcommand_exits_usage_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        _ = main([])
    assert excinfo.value.code == 2


def test_main_unknown_subcommand_exits_usage_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        _ = main(["frobnicate"])
    assert excinfo.value.code == 2


def test_gap_capture_requires_gaps_json_flag() -> None:
    with pytest.raises(SystemExit) as excinfo:
        _ = main(["gap-capture"])
    assert excinfo.value.code == 2


def test_drift_capture_requires_propose_change_cli_flag(tmp_path: Path) -> None:
    payload = _drifts_payload_file(root=tmp_path, drifts=[])
    with pytest.raises(SystemExit) as excinfo:
        _ = main(["drift-capture", "--drifts-json", str(payload)])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# spec-reader
# ---------------------------------------------------------------------------


def test_spec_reader_missing_spec_tree_exits_precondition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["spec-reader", "--project-root", str(tmp_path)])
    assert rc == 3
    assert "spec tree not found" in capsys.readouterr().err


def test_spec_reader_json_categorizes_every_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    rc = main(["spec-reader", "--project-root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == 2
    assert payload["categories"]["spec"] == {"spec.md": "# Spec\n"}
    assert payload["categories"]["contracts"] == {"contracts.md": "# Contracts\n"}
    assert payload["categories"]["research"] == {"research/notes.md": "notes\n"}
    all_paths = [path for files in payload["categories"].values() for path in files]
    assert "proposed_changes/pending.md" not in all_paths


def test_spec_reader_category_filter_selects_one_category(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    rc = main(["spec-reader", "--project-root", str(tmp_path), "--category", "spec", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload["categories"]) == ["spec"]


def test_spec_reader_category_filter_unknown_yields_empty(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    rc = main(["spec-reader", "--project-root", str(tmp_path), "--category", "nope", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["categories"] == {}


def test_spec_reader_human_output_lists_categories(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    rc = main(["spec-reader", "--project-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "spec version: v002" in out
    assert "category: spec" in out
    assert "  spec.md" in out


def test_spec_reader_human_output_empty_tree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "SPECIFICATION").mkdir()
    rc = main(["spec-reader", "--project-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "spec version: v000" in out
    assert "(no spec files)" in out


def test_spec_reader_defaults_project_root_to_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = main(["spec-reader", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["version"] == 2


def test_spec_reader_explicit_spec_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = _make_spec_tree(root=tmp_path)
    rc = main(
        ["spec-reader", "--spec-target", str(spec), "--project-root", str(tmp_path), "--json"]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["version"] == 2


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def test_parse_cli_argv_accepts_json_string_array() -> None:
    assert parse_cli_argv(raw='["python3", "x.py"]', flag="--f") == ["python3", "x.py"]


@pytest.mark.parametrize(
    "raw",
    ["not json", '{"a": 1}', "[]", '["ok", 3]', '["ok", ""]'],
)
def test_parse_cli_argv_rejects_non_argv_values(
    raw: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parse_cli_argv(raw=raw, flag="--f") is None
    assert "--f requires a JSON array" in capsys.readouterr().err


def test_load_payload_reads_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"gaps": []}'))
    assert load_payload(source="-") == {"gaps": []}


def test_load_payload_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PayloadMissingError):
        _ = load_payload(source=str(tmp_path / "absent.json"))


def test_load_payload_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    _ = path.write_text("{nope", encoding="utf-8")
    with pytest.raises(PayloadInvalidError):
        _ = load_payload(source=str(path))


@pytest.mark.parametrize("obj", [{}, {"k": 3}, {"k": ""}])
def test_require_str_rejects_missing_or_empty(obj: dict[str, object]) -> None:
    with pytest.raises(PayloadInvalidError):
        _ = require_str(obj=obj, key="k", where="payload")


def test_require_str_returns_value() -> None:
    assert require_str(obj={"k": "v"}, key="k", where="payload") == "v"


def test_resolve_spec_version_internal_reader(tmp_path: Path) -> None:
    spec = _make_spec_tree(root=tmp_path)
    context = CliContext(project_root=tmp_path, spec_root=spec)
    version = resolve_spec_version(spec_reader_cli=None, context=context)
    assert version == 2


def test_resolve_spec_version_injected_reader(tmp_path: Path) -> None:
    spec = _make_spec_tree(root=tmp_path)
    version = resolve_spec_version(
        spec_reader_cli=_fake_spec_reader_cli(version=7),
        context=CliContext(project_root=tmp_path, spec_root=spec),
    )
    assert version == 7


def test_resolve_spec_version_injected_reader_failure_raises(tmp_path: Path) -> None:
    failing = [sys.executable, "-c", "import sys; sys.exit(5)"]
    with pytest.raises(InjectedCliError, match="exit 5"):
        _ = resolve_spec_version(
            spec_reader_cli=failing,
            context=CliContext(project_root=tmp_path, spec_root=tmp_path / "SPECIFICATION"),
        )


def test_resolve_spec_version_injected_reader_non_json_stdout_raises(tmp_path: Path) -> None:
    chatty = [sys.executable, "-c", "print('hello')"]
    with pytest.raises(InjectedCliError, match="not a JSON object"):
        _ = resolve_spec_version(
            spec_reader_cli=chatty,
            context=CliContext(project_root=tmp_path, spec_root=tmp_path / "SPECIFICATION"),
        )


def test_resolve_spec_version_injected_reader_json_array_stdout_raises(tmp_path: Path) -> None:
    arrayish = [sys.executable, "-c", "import sys; sys.stdout.write('[1, 2]')"]
    with pytest.raises(InjectedCliError, match="not a JSON object"):
        _ = resolve_spec_version(
            spec_reader_cli=arrayish,
            context=CliContext(project_root=tmp_path, spec_root=tmp_path / "SPECIFICATION"),
        )


@pytest.mark.parametrize("version", ["'oops'", "True"])
def test_resolve_spec_version_injected_reader_non_int_version_raises(
    tmp_path: Path,
    version: str,
) -> None:
    code = f"import json, sys; sys.stdout.write(json.dumps({{'version': {version}}}))"
    with pytest.raises(InjectedCliError, match="no integer `version` key"):
        _ = resolve_spec_version(
            spec_reader_cli=[sys.executable, "-c", code],
            context=CliContext(project_root=tmp_path, spec_root=tmp_path / "SPECIFICATION"),
        )


# ---------------------------------------------------------------------------
# gap-capture
# ---------------------------------------------------------------------------


def test_gap_capture_creates_gap_tied_work_items(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _gaps_payload_file(
        root=tmp_path,
        gaps=[
            {"gap_id": "gap-aaa", "title": "First gap", "description": "prose", "priority": 1},
            {"gap_id": "gap-bbb", "title": "Second gap"},
        ],
    )
    rc = main(
        ["gap-capture", "--gaps-json", str(payload), "--project-root", str(tmp_path), "--json"]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["spec_version"] == 2
    assert out["dry_run"] is False
    assert [entry["gap_id"] for entry in out["created"]] == ["gap-aaa", "gap-bbb"]
    assert out["skipped_existing"] == []
    items = {item.gap_id: item for item in _stored_items()}
    assert items["gap-aaa"].origin == "gap-tied"
    assert items["gap-aaa"].priority == 1
    assert items["gap-aaa"].title == "First gap"
    assert "captured against spec version v002" in items["gap-aaa"].description
    assert items["gap-bbb"].priority == 2
    assert items["gap-bbb"].status == "open"


def test_gap_capture_skips_existing_and_payload_duplicates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    first = _gaps_payload_file(root=tmp_path, gaps=[{"gap_id": "gap-aaa", "title": "First"}])
    assert main(["gap-capture", "--gaps-json", str(first), "--project-root", str(tmp_path)]) == 0
    _ = capsys.readouterr()
    again = tmp_path / "again.json"
    _ = again.write_text(
        json.dumps(
            {
                "gaps": [
                    {"gap_id": "gap-aaa", "title": "First again"},
                    {"gap_id": "gap-ccc", "title": "Fresh"},
                    {"gap_id": "gap-ccc", "title": "Fresh duplicate"},
                ],
            },
        ),
        encoding="utf-8",
    )
    rc = main(["gap-capture", "--gaps-json", str(again), "--project-root", str(tmp_path), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert [entry["gap_id"] for entry in out["created"]] == ["gap-ccc"]
    assert out["skipped_existing"] == ["gap-aaa", "gap-ccc"]
    assert len([item for item in _stored_items() if item.gap_id == "gap-ccc"]) == 1


def test_gap_capture_dry_run_writes_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _gaps_payload_file(root=tmp_path, gaps=[{"gap_id": "gap-aaa", "title": "First"}])
    rc = main(
        ["gap-capture", "--gaps-json", str(payload), "--project-root", str(tmp_path), "--dry-run"],
    )
    assert rc == 0
    assert "would create" in capsys.readouterr().out
    assert _stored_items() == []


def test_gap_capture_human_output_names_created_and_skipped(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _gaps_payload_file(
        root=tmp_path,
        gaps=[
            {"gap_id": "gap-aaa", "title": "First"},
            {"gap_id": "gap-aaa", "title": "Dup"},
        ],
    )
    rc = main(["gap-capture", "--gaps-json", str(payload), "--project-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "created livespec-impl-beads-" in out
    assert "(gap gap-aaa)" in out
    assert "skipped existing gap gap-aaa" in out


def test_gap_capture_empty_gaps_list_is_a_no_op(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _gaps_payload_file(root=tmp_path, gaps=[])
    rc = main(["gap-capture", "--gaps-json", str(payload), "--project-root", str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out == ""
    assert _stored_items() == []


def test_gap_capture_reads_payload_from_stdin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    stdin_payload = json.dumps({"gaps": [{"gap_id": "gap-ddd", "title": "Stdin gap"}]})
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_payload))
    rc = main(["gap-capture", "--gaps-json", "-", "--project-root", str(tmp_path), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert [entry["gap_id"] for entry in out["created"]] == ["gap-ddd"]


def test_gap_capture_missing_payload_file_exits_precondition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    rc = main(
        [
            "gap-capture",
            "--gaps-json",
            str(tmp_path / "absent.json"),
            "--project-root",
            str(tmp_path),
        ],
    )
    assert rc == 3
    assert "payload file not found" in capsys.readouterr().err


def test_gap_capture_unparseable_payload_exits_validation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    path = tmp_path / "bad.json"
    _ = path.write_text("{nope", encoding="utf-8")
    rc = main(["gap-capture", "--gaps-json", str(path), "--project-root", str(tmp_path)])
    assert rc == 4
    assert "not valid JSON" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ([1, 2], "payload must be a JSON object"),
        ({"gaps": "nope"}, "payload.gaps must be a list"),
        ({"gaps": ["nope"]}, "payload.gaps[0] must be a JSON object"),
        (
            {"gaps": [{"gap_id": "g", "title": "t", "description": 3}]},
            "description must be a string",
        ),
        (
            {"gaps": [{"gap_id": "g", "title": "t", "priority": "high"}]},
            "priority must be an integer",
        ),
        (
            {"gaps": [{"gap_id": "g", "title": "t", "priority": True}]},
            "priority must be an integer",
        ),
        ({"gaps": [{"title": "t"}]}, "gap_id must be a non-empty string"),
        ({"gaps": [{"gap_id": "g"}]}, "title must be a non-empty string"),
    ],
)
def test_gap_capture_rejects_malformed_payloads(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: object,
    detail: str,
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    path = tmp_path / "payload.json"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    rc = main(["gap-capture", "--gaps-json", str(path), "--project-root", str(tmp_path)])
    assert rc == 4
    assert detail in capsys.readouterr().err
    assert _stored_items() == []


def test_gap_capture_uses_injected_spec_reader_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _gaps_payload_file(root=tmp_path, gaps=[{"gap_id": "gap-eee", "title": "Injected"}])
    rc = main(
        [
            "gap-capture",
            "--gaps-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--spec-reader-cli",
            json.dumps(_fake_spec_reader_cli(version=7)),
            "--json",
        ],
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["spec_version"] == 7
    (item,) = _stored_items()
    assert "captured against spec version v007" in item.description


def test_gap_capture_invalid_spec_reader_cli_value_exits_usage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _gaps_payload_file(root=tmp_path, gaps=[])
    rc = main(
        [
            "gap-capture",
            "--gaps-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--spec-reader-cli",
            "not-json",
        ],
    )
    assert rc == 2
    assert "--spec-reader-cli requires a JSON array" in capsys.readouterr().err


def test_gap_capture_failing_injected_spec_reader_exits_precondition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _gaps_payload_file(root=tmp_path, gaps=[{"gap_id": "gap-fff", "title": "T"}])
    failing = [sys.executable, "-c", "import sys; sys.exit(5)"]
    rc = main(
        [
            "gap-capture",
            "--gaps-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--spec-reader-cli",
            json.dumps(failing),
        ],
    )
    assert rc == 3
    assert "injected CLI" in capsys.readouterr().err
    assert _stored_items() == []


# ---------------------------------------------------------------------------
# drift-capture
# ---------------------------------------------------------------------------


def test_drift_capture_routes_to_propose_change_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = _make_spec_tree(root=tmp_path)
    payload = _drifts_payload_file(root=tmp_path, drifts=[_drift()])
    record_path = tmp_path / "record.json"
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            json.dumps(_recorder_propose_change_cli(record_path=record_path)),
            "--json",
        ],
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["routed"] == [{"topic": "drift-topic", "exit_code": 0}]
    assert out["failed"] == []
    record = json.loads(record_path.read_text(encoding="utf-8"))
    argv = record["argv"]
    assert argv[0] == "drift-topic"
    assert argv[argv.index("--project-root") + 1] == str(tmp_path)
    assert argv[argv.index("--spec-target") + 1] == str(spec)
    findings = json.loads(record["findings"])
    assert findings["findings"][0]["name"] == "Drift proposal"
    assert findings["findings"][0]["target_spec_files"] == ["SPECIFICATION/contracts.md"]
    assert findings["findings"][0]["summary"] == "summary prose"
    assert findings["findings"][0]["motivation"] == "motivation prose"
    assert findings["findings"][0]["proposed_changes"] == "change prose"


def test_drift_capture_failing_child_exits_precondition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _drifts_payload_file(root=tmp_path, drifts=[_drift()])
    record_path = tmp_path / "record.json"
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            json.dumps(_recorder_propose_change_cli(record_path=record_path, exit_code=7)),
            "--json",
        ],
    )
    assert rc == 3
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["failed"] == ["drift-topic"]
    assert "exited 7" in captured.err
    assert "recorder narration" in captured.err


def test_drift_capture_dry_run_invokes_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _drifts_payload_file(root=tmp_path, drifts=[_drift()])
    record_path = tmp_path / "record.json"
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            json.dumps(_recorder_propose_change_cli(record_path=record_path)),
            "--dry-run",
        ],
    )
    assert rc == 0
    assert "would route drift-topic: ok" in capsys.readouterr().out
    assert not record_path.exists()


def test_drift_capture_human_output_marks_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _drifts_payload_file(root=tmp_path, drifts=[_drift()])
    record_path = tmp_path / "record.json"
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            json.dumps(_recorder_propose_change_cli(record_path=record_path, exit_code=7)),
        ],
    )
    assert rc == 3
    assert "routed drift-topic: FAILED (exit 7)" in capsys.readouterr().out


def test_drift_capture_empty_drifts_list_is_a_no_op(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _drifts_payload_file(root=tmp_path, drifts=[])
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            json.dumps(["true"]),
        ],
    )
    assert rc == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (["nope"], "payload must be a JSON object"),
        ({"drifts": "nope"}, "payload.drifts must be a list"),
        ({"drifts": ["nope"]}, "payload.drifts[0] must be a JSON object"),
        ({"drifts": [_drift(target_spec_files=[])]}, "target_spec_files"),
        ({"drifts": [_drift(target_spec_files=[3])]}, "target_spec_files"),
        ({"drifts": [_drift(target_spec_files=["ok", ""])]}, "target_spec_files"),
        ({"drifts": [_drift(topic="")]}, "topic must be a non-empty string"),
        ({"drifts": [_drift(summary=None)]}, "summary must be a non-empty string"),
    ],
)
def test_drift_capture_rejects_malformed_payloads(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: object,
    detail: str,
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    path = tmp_path / "payload.json"
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(path),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            json.dumps(["true"]),
        ],
    )
    assert rc == 4
    assert detail in capsys.readouterr().err


def test_drift_capture_invalid_propose_change_cli_value_exits_usage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _drifts_payload_file(root=tmp_path, drifts=[])
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            "[]",
        ],
    )
    assert rc == 2
    assert "--propose-change-cli requires a JSON array" in capsys.readouterr().err


def test_drift_capture_uses_injected_spec_reader_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _make_spec_tree(root=tmp_path)
    payload = _drifts_payload_file(root=tmp_path, drifts=[])
    rc = main(
        [
            "drift-capture",
            "--drifts-json",
            str(payload),
            "--project-root",
            str(tmp_path),
            "--propose-change-cli",
            json.dumps(["true"]),
            "--spec-reader-cli",
            json.dumps(_fake_spec_reader_cli(version=9)),
            "--json",
        ],
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["spec_version"] == 9
