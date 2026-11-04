"""Where the materialized resolution LOOKS for the declaration it reads.

THE WRONG-POPULATION CASE, and it is the one the sibling module structurally
cannot catch. `tests/.../test_dispatcher_record_file_regeneration.py` writes the
declaration into its fixture in whatever shape the reader expects and then asks
the reader to find it, so a reader pointed at a key no real `.livespec.jsonc`
carries passes every case there while being incapable of ever finding a live
declaration. AGENTS.md calls this an instrument that cannot return a hit
reporting no hits: valid output, exit 0, a plausible answer, and no error.

Measured on this repository on 2026-10-22: `.livespec.jsonc` carries its
dispatcher block at `livespec-orchestrator-beads-fabro.dispatcher`, NESTED under
the plugin block, which is where `_config.dispatcher_block` reads it from. A
program reading a TOP-LEVEL `dispatcher` key finds nothing in every governed
repository in the fleet — so every conflicted generated register would read as
undeclared and be hand-merged, which is the exact loss the work-item exists to
stop, reached through the one state nothing announces.

So these cases read the shape off the REPOSITORY'S OWN COMMITTED FILE rather
than off a fixture this module authored. A fixture asserts agreement with
itself; the committed file is the population the program is aimed at.

THE ABSENT-FILE ARM IS HERE TOO, because it is the same question answered for a
repository that carries no configuration at all. A missing file DECLARES
NOTHING, exactly as a missing key does, and that is an answer: a reading that
held on it would refuse every refresh in a clone whose configuration had not
been written, including every scratch clone the publication harnesses drive.
Only a file that EXISTS and will not parse is unreadable, which is the arm the
sibling module owns.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    RECORD_FILE_TARGETS_FILENAME,
    record_file_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_files import (
    RECORD_FILES_KEY,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG = _REPO_ROOT / ".livespec.jsonc"
_DISPATCHER_KEY = "dispatcher"
_COMMENT = re.compile(r'("(?:\\.|[^"\\])*")|(//[^\n]*)')


def _materialized(*, tmp_path: Path) -> ModuleType:
    path = tmp_path / RECORD_FILE_PROGRAM_FILENAME
    _ = path.write_text(record_file_program_source(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("livespec_declaration_shape", path)
    assert spec is not None
    assert spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _git(*, repo: Path, args: list[str]) -> None:
    _ = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _clone(*, root: Path) -> Path:
    root.mkdir()
    _git(repo=root, args=["init", "--quiet", "--initial-branch", "master"])
    _git(repo=root, args=["config", "user.name", "Test"])
    _git(repo=root, args=["config", "user.email", "test@example.com"])
    _git(repo=root, args=["config", "commit.gpgsign", "false"])
    return root


def _commit(*, repo: Path) -> None:
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "--quiet", "-m", "base"])


def test_this_repositorys_own_committed_file_nests_the_dispatcher_block() -> None:
    """The control. Every case below is only about a shape this establishes.

    Without it the nesting assertion is a claim about a fixture, which is the
    failure this module exists to close.
    """
    stripped = _COMMENT.sub(lambda match: match.group(1) or "", _CONFIG.read_text(encoding="utf-8"))
    document = json.loads(stripped)
    assert _DISPATCHER_KEY not in document, sorted(document)
    assert isinstance(document[PLUGIN_BLOCK], dict)
    assert _DISPATCHER_KEY in document[PLUGIN_BLOCK]


def test_the_program_reads_the_declaration_where_a_real_repository_carries_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A declaration nested under the plugin block is the one the program finds.

    Written in the repository's OWN shape, established by the control above, and
    asserted through an observable only a FOUND declaration can produce: the
    hand-edited register's gate target. A reader pointed at a top-level key
    reports a clean head here and says nothing at all.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _clone(root=tmp_path / "repo")
    _ = (repo / ".livespec.jsonc").write_text(
        "// nested exactly as this repository's own file nests it\n"
        + json.dumps(
            {
                PLUGIN_BLOCK: {
                    _DISPATCHER_KEY: {
                        RECORD_FILES_KEY: [
                            {"path": "register.json", "generator": ["./generate.sh"]}
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    script = repo / "generate.sh"
    _ = script.write_text("#!/bin/sh\nexec cp registry.json register.json\n", encoding="utf-8")
    script.chmod(0o755)
    _ = (repo / "registry.json").write_text('["a", "b"]\n', encoding="utf-8")
    _ = (repo / "register.json").write_text('["a"]\n', encoding="utf-8")
    _commit(repo=repo)
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--check-head"]) != 0
    targets = (state / RECORD_FILE_TARGETS_FILENAME).read_text(encoding="utf-8")
    assert targets.strip() == "generated-record-file:register.json"


def test_a_clone_carrying_no_configuration_file_declares_no_record_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent file is an ANSWER, not a reading that could not be taken.

    Every publication harness drives a scratch clone with no configuration at
    all, and so does a clone whose configuration has not been written yet. A
    program that held on the absence would refuse the refresh of each one before
    the repository-declared gate, which is a refusal about the harness rather
    than about any register.
    """
    program = _materialized(tmp_path=tmp_path)
    repo = _clone(root=tmp_path / "bare")
    _ = (repo / "README.md").write_text("no configuration here\n", encoding="utf-8")
    _commit(repo=repo)
    monkeypatch.chdir(repo)
    state = tmp_path / "state"
    state.mkdir()
    assert program.main(["--state-dir", str(state), "--check-head"]) == 0
    assert (state / RECORD_FILE_TARGETS_FILENAME).read_text(encoding="utf-8") == ""
