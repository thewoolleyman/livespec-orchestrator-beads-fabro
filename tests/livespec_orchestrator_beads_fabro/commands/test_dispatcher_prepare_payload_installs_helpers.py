"""Every helper a prepare step writes is still written, byte for byte (bd-ib-coxsfu).

Moving a payload out of a step's script and into its env must leave the sandbox
with the SAME files at the SAME paths. This file renders the whole dispatch
overlay, EXECUTES each payload-bearing step the way the engine's shell does
(its script, with its own env) in a throwaway plugins root, and compares what
landed against the owning module's source of record.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_program import (
    CARRY_FORWARD_PROGRAM_FILENAME,
    carry_forward_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_PROGRAM_FILENAME,
    hook_limit_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_GATE_PROGRAM_FILENAME,
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_grade_program import (
    PROOF_GRADE_PROGRAM_FILENAME,
    PROOF_GRADE_READER_DIRECTORY,
    proof_grade_program_source,
    proof_record_reader_sources,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PUBLICATION_BODY_FILENAME,
    PublicationMetadata,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)

from tests.prepare_step_support import env_of, steps_in

_COMMITTED = '[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n'
# A body carrying the characters that broke earlier transports: shell syntax,
# a non-BMP emoji (a TOML surrogate-pair hazard) and a multi-byte letter.
_BODY = (
    "Work-item bd-x $(touch /tmp/never) `date` \U0001f916 é\n\n## Definition of Done\n\n- one.\n"
)


def _git_clone(*, root: Path) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


@pytest.fixture(name="landed")
def _landed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The plugins root after every payload-bearing, directly runnable step ran."""
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
    overlay = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token="",
        github_token="",
        siblings=None,
        publication_metadata=PublicationMetadata(title="Title (bd-x)", body=_BODY),
    )
    assert overlay is not None
    plugins_root = tmp_path / "plugins"
    clone = _git_clone(root=tmp_path / "clone")
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
    }
    payload_steps = [step for step in steps_in(block=overlay) if step.env]
    # The gh-refresh chain writes under the fixed sandbox root and needs a real
    # `gh` to wrap; `test_dispatcher_gh_refresh_worktree` executes that chain.
    runnable = [step for step in payload_steps if ".livespec-gh-refresh" not in step.script]
    assert len(runnable) >= 10
    for step in runnable:
        completed = subprocess.run(
            ["sh", "-c", step.script],
            cwd=clone,
            env=env_of(step=step, base=base),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, f"{step.script}\n{completed.stderr}"
    return plugins_root


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (PROOF_HEAD_PROGRAM_FILENAME, proof_head_program_source),
        (PUBLICATION_PUSH_PROGRAM_FILENAME, publication_push_program_source),
        (CARRY_FORWARD_PROGRAM_FILENAME, carry_forward_program_source),
        (RECORD_FILE_PROGRAM_FILENAME, record_file_program_source),
        (HOOK_LIMIT_PROGRAM_FILENAME, hook_limit_program_source),
        (COMMIT_RUNNER_PROGRAM_FILENAME, commit_runner_program_source),
        (PROOF_GRADE_PROGRAM_FILENAME, proof_grade_program_source),
    ],
)
def test_each_helper_program_lands_with_its_source_of_record(
    landed: Path, filename: str, expected: object
) -> None:
    assert callable(expected)
    assert (landed / filename).read_bytes() == expected().encode("utf-8")


def test_every_proof_record_reader_module_lands_beside_the_grade_program(landed: Path) -> None:
    sources = proof_record_reader_sources()
    assert sources
    for name, source in sources:
        assert (landed / PROOF_GRADE_READER_DIRECTORY / name).read_bytes() == source.encode("utf-8")


def test_the_pull_request_body_lands_byte_for_byte(landed: Path) -> None:
    assert (landed / PUBLICATION_BODY_FILENAME).read_bytes() == _BODY.encode("utf-8")


def test_the_plugin_gate_program_lands_complete_and_runnable_source(landed: Path) -> None:
    text = (landed / PLUGIN_GATE_PROGRAM_FILENAME).read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "__" not in text.replace("__future__", "").replace("__name__", "")
    _ = ast.parse(text)


def test_the_push_program_stays_executable_only_by_its_owner(landed: Path) -> None:
    assert (landed / PUBLICATION_PUSH_PROGRAM_FILENAME).stat().st_mode & 0o777 == 0o700
