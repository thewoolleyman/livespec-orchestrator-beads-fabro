"""The materialized generated-record-file resolution program, as an artifact.

Scenario 238's refresh behaviour is produced by the implement-work-item graph's
own command scripts against a RELEASED payload, so Scenario 54 puts it beyond
any sandbox capability and Scenario 137 forbids proving it with a fixture: the
work-item's Definition of Done captures all three behaviours on an operator
host. What is left for this tier is what a host capture cannot see — the
properties of the SHIPPED BYTES, and the decisions the program makes over a real
git tree whose declaration this test writes.

A program that resolves correctly in a sandbox where this package happens to be
importable is broken in exactly the way no behavioural case reaches: the governed
clone carries no copy of this package, so the program is loaded here from the
bytes the prepare step writes and is required to answer with nothing but the
standard library.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_FILE = "_dispatcher_record_file_regeneration.py"


def _module() -> Any:
    """The module under test, imported inside the test body.

    The file is asserted FIRST so the Red is a genuine assertion failure rather
    than a collection error: at Red the module does not exist, and a top-level
    import of it would die before any assertion ran.
    """
    assert (_COMMANDS_DIR / _MODULE_FILE).is_file()
    from livespec_orchestrator_beads_fabro.commands import (
        _dispatcher_record_file_regeneration,
    )

    return _dispatcher_record_file_regeneration


def _materialized(*, tmp_path: Path) -> ModuleType:
    """The program as a module, loaded from the bytes the prepare step writes."""
    module = _module()
    path = tmp_path / module.RECORD_FILE_PROGRAM_FILENAME
    _ = path.write_text(module.record_file_program_source(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("livespec_record_file_resolution", path)
    assert spec is not None
    assert spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _git(*, repo: Path, args: list[str]) -> None:
    _ = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _initialized(*, root: Path) -> Path:
    root.mkdir()
    _git(repo=root, args=["init", "--quiet", "--initial-branch", "master"])
    _git(repo=root, args=["config", "user.name", "Test"])
    _git(repo=root, args=["config", "user.email", "test@example.com"])
    return root


def _repo(*, tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    """A real git repository whose committed declaration names `entries`."""
    repo = _initialized(root=tmp_path / "repo")
    _ = (repo / ".livespec.jsonc").write_text(
        "// a committed declaration\n" + json.dumps({"dispatcher": {"record_files": entries}}),
        encoding="utf-8",
    )
    return repo


def _commit(*, repo: Path, message: str) -> None:
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "--quiet", "--no-verify", "-m", message])


def _generator_script(*, repo: Path, name: str, body: str) -> None:
    script = repo / name
    _ = script.write_text(body, encoding="utf-8")
    script.chmod(0o755)


def _copying_generator(*, repo: Path) -> None:
    """A generator that derives the register from the registry, as the real one does."""
    _generator_script(
        repo=repo,
        name="generate.sh",
        body="#!/bin/sh\nexec cp registry.json register.json\n",
    )


def test_the_program_carries_no_livespec_import(tmp_path: Path) -> None:
    """The governed clone has no copy of this package, so the program needs none.

    The discriminating property, and the one a host capture cannot report: a
    program that imported the package would resolve perfectly in this repository
    and fail on every sandbox, where the failure reads as a Dispatcher that never
    materialized it.
    """
    module = _module()
    source = module.record_file_program_source()
    assert "livespec_orchestrator_beads_fabro" not in source
    _ = _materialized(tmp_path=tmp_path)


def test_the_prepare_step_quotes_its_heredoc_delimiter(tmp_path: Path) -> None:
    """The program is written through a heredoc the shell expands nothing inside.

    The program carries dollar-bearing text of its own, so an unquoted delimiter
    would substitute into the program's own source at prepare time and land bytes
    nobody wrote.
    """
    module = _module()
    block = module.record_file_program_prepare_steps_block()
    assert "<<'LIVESPEC_RECORD_FILE_PROGRAM'" in block
    assert module.RECORD_FILE_PROGRAM_FILENAME in block
    assert json.dumps(module.record_file_program_source())[1:-1] in block
    _ = tmp_path


def test_the_path_expansion_resolves_the_shared_sandbox_plugins_root() -> None:
    """The node and the prepare step resolve ONE root, spelled once."""
    module = _module()
    from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
        sandbox_plugins_root_expansion,
    )

    expansion = module.record_file_program_path_expansion()
    assert expansion.startswith(sandbox_plugins_root_expansion())
    assert expansion.endswith(module.RECORD_FILE_PROGRAM_FILENAME)


def test_a_conflicted_generated_record_file_is_written_from_its_generator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--resolve` runs the generator and stages its output, never a text merge.

    The register's rows are the discriminating evidence: a hand merge of the
    conflicted text keeps whichever side it chose, while the generator's output
    over the tree carries both sides' rows because it derives them from the
    registry the merge already resolved.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "register.json", "format": "json-array", "generator": ["./generate.sh"]}],
    )
    _copying_generator(repo=repo)
    _ = (repo / "registry.json").write_text('["a", "b"]\n', encoding="utf-8")
    _ = (repo / "register.json").write_text('["a", "b"]\n', encoding="utf-8")
    _commit(repo=repo, message="base")
    _ = (repo / "register.json").write_text("<<<<<<< conflicted\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--resolve", "register.json"]) == 0
    assert (repo / "register.json").read_text(encoding="utf-8") == '["a", "b"]\n'
    narrated = capsys.readouterr().err
    assert "register.json" in narrated
    assert "./generate.sh" in narrated


def test_a_conflicted_path_that_is_not_a_declared_record_file_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A conflict outside the declaration takes the refresh-repair route unchanged.

    The fail-CLOSED direction, and the one worth a case of its own: a resolution
    that regenerated the declared half of a wider conflict would leave the rest
    of the conflict in the tree and report success.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "register.json", "generator": ["./generate.sh"]}],
    )
    _generator_script(repo=repo, name="generate.sh", body="#!/bin/sh\nexit 0\n")
    _ = (repo / "register.json").write_text("[]\n", encoding="utf-8")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    status = program.main(
        ["--state-dir", str(state), "--resolve", "register.json", "module.py"],
    )
    assert status != 0
    assert "module.py" in capsys.readouterr().err


def test_a_conflicted_declared_record_file_naming_no_generator_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only the entry-wise merge resolves an ungenerated record file, and it is elsewhere.

    The clause merges such a file entry by entry, which work-item bd-ib-davaxq
    owns and which is implemented nowhere; a resolution that wrote nothing for it
    and reported success would publish a head still carrying its conflict
    markers.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[
            {"path": "registry.json", "format": "json-array", "key": ["id"]},
            {"path": "register.json", "generator": ["./generate.sh"]},
        ],
    )
    _generator_script(repo=repo, name="generate.sh", body="#!/bin/sh\nexit 0\n")
    _ = (repo / "registry.json").write_text("[]\n", encoding="utf-8")
    _ = (repo / "register.json").write_text("[]\n", encoding="utf-8")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    status = program.main(
        ["--state-dir", str(state), "--resolve", "registry.json", "register.json"],
    )
    assert status != 0
    assert "registry.json" in capsys.readouterr().err


def test_a_generator_that_exits_non_zero_is_not_a_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The clause makes a generated file resolvable exactly when its generator exits zero."""
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "register.json", "generator": ["./generate.sh"]}],
    )
    _generator_script(repo=repo, name="generate.sh", body="#!/bin/sh\nexit 3\n")
    _ = (repo / "register.json").write_text("[]\n", encoding="utf-8")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--resolve", "register.json"]) != 0
    assert "./generate.sh" in capsys.readouterr().err


def test_a_generator_writing_no_file_is_not_a_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A generator that exits zero and writes nothing resolves nothing.

    The one zero-exit outcome that is not a resolution, and it fails in the
    expensive direction: the conflicted file would be staged as whatever the
    conflict left behind, markers and all.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "absent.json", "generator": ["./generate.sh"]}],
    )
    _generator_script(repo=repo, name="generate.sh", body="#!/bin/sh\nexit 0\n")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--resolve", "absent.json"]) != 0
    assert "absent.json" in capsys.readouterr().err


def test_the_brief_carries_one_regenerate_line_per_conflicted_generated_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--brief` names each generated file and the argv the fix turn must run.

    The second Host-captured behaviour's observable: a brief that named the
    conflicted path without its generator would leave the `fix` turn to merge the
    register's text, which is the loss this work-item exists to stop.
    """
    module = _module()
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "register.json", "generator": ["just", "generate register"]}],
    )
    _ = (repo / "register.json").write_text("[]\n", encoding="utf-8")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--brief", "register.json", "module.py"]) == 0
    written = (state / module.RECORD_FILE_BRIEF_FILENAME).read_text(encoding="utf-8")
    assert written == "regenerate: register.json via just 'generate register'\n"


def test_a_head_whose_generated_file_was_hand_edited_fails_with_its_gate_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--check-head` names `generated-record-file:<path>` and restores the tree.

    The third Host-captured behaviour's observable. The restoration is asserted
    beside the target because the check RUNS the generator to take its reading,
    so a check that left its own output in the tree would hand the
    repository-declared gate a head nobody committed.
    """
    module = _module()
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "register.json", "generator": ["./generate.sh"]}],
    )
    _copying_generator(repo=repo)
    _ = (repo / "registry.json").write_text('["a", "b"]\n', encoding="utf-8")
    _ = (repo / "register.json").write_text('["a"]\n', encoding="utf-8")
    _commit(repo=repo, message="hand-edited register")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--check-head"]) != 0
    targets = (state / module.RECORD_FILE_TARGETS_FILENAME).read_text(encoding="utf-8")
    assert targets.strip() == "generated-record-file:register.json"
    brief = (state / module.RECORD_FILE_BRIEF_FILENAME).read_text(encoding="utf-8")
    assert brief == "regenerate: register.json via ./generate.sh\n"
    assert (repo / "register.json").read_text(encoding="utf-8") == '["a"]\n'
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert porcelain.stdout == ""


def test_a_head_whose_generated_file_matches_its_generator_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary refreshed head reaches the repository-declared gate unchanged."""
    module = _module()
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "register.json", "generator": ["./generate.sh"]}],
    )
    _copying_generator(repo=repo)
    _ = (repo / "registry.json").write_text('["a", "b"]\n', encoding="utf-8")
    _ = (repo / "register.json").write_text('["a", "b"]\n', encoding="utf-8")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--check-head"]) == 0
    assert (state / module.RECORD_FILE_TARGETS_FILENAME).read_text(encoding="utf-8") == ""


def test_a_repository_declaring_no_record_files_checks_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent declaration declares no record files, which is an answer.

    Every repository in this fleet is in this state today, so a check that read
    an absent key as a fault would refuse every refresh in the fleet.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _initialized(root=tmp_path / "bare")
    _ = (repo / ".livespec.jsonc").write_text('{"dispatcher": {}}', encoding="utf-8")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--check-head"]) == 0


def test_an_unreadable_declaration_holds_rather_than_resolving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A declaration nothing can parse resolves nothing, and says which reading failed.

    The fail-closed direction the empty-declaration case above cannot cover: both
    answers are "no generated file is declared here", and a resolution that could
    not tell them apart would hand-merge a register whose declaration it simply
    failed to read.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _initialized(root=tmp_path / "broken")
    _ = (repo / ".livespec.jsonc").write_text("{not json", encoding="utf-8")
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--resolve", "register.json"]) != 0
    assert "declaration" in capsys.readouterr().err


def test_an_entry_whose_path_is_unusable_holds_the_whole_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An entry naming no usable repository-relative path stops the resolution.

    The pre-dispatch refusal grades `generator` alone, so an entry whose `path`
    is absent, absolute or parent-bearing still reaches a refresh. Dropping such
    an entry quietly is the fail-OPEN reading: the file would read as undeclared,
    which is exactly the state in which a `fix` turn hand-merges it.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        entries=[{"path": "../outside.json", "generator": ["./generate.sh"]}],
    )
    _commit(repo=repo, message="base")
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--check-head"]) != 0
    assert "declaration" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no-mode"),
        pytest.param(["--state-dir"], id="state-dir-without-value"),
        pytest.param(["--resolve", "register.json"], id="mode-without-state-dir"),
        pytest.param(["--state-dir", "/tmp", "--resolve"], id="resolve-without-paths"),
    ],
)
def test_an_invocation_naming_no_mode_and_state_directory_is_refused(
    tmp_path: Path, argv: list[str]
) -> None:
    """Both inputs are required, because neither has a safe default.

    A mode defaulted to `--resolve` would regenerate on an invocation that meant
    to ask a question, and a state directory defaulted anywhere would write the
    brief where no stage reads it — which reads downstream as a brief that named
    no generated file.
    """
    program = _materialized(tmp_path=tmp_path)
    assert program.main(argv) != 0
