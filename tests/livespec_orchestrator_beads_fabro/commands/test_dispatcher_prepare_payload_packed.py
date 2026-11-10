"""Every plain-text prepare payload rides gzip+base64, and still lands byte for byte.

The dispatch overlay is collected as the run's `workflow.toml`, and the engine
caps that ONE file at 512 KiB (Fabro `MAX_WORKFLOW_VERSION_FILE_BYTES`). After
orchestrator v0.312.3 the livespec-dev-tooling overlay measured 524,343 bytes and
every dispatch there was refused before listing; about 185 KB of it was helper
programs carried as plain JSON-escaped text in their steps' `env` values, while
the one payload already packed -- the gh-refresh bundle -- cost a third of its
raw size.

So every payload is packed the way that bundle is, and each step decodes its own
value. These tests hold both halves on the WHOLE rendered overlay rather than on
a list of helpers: every payload value is single-line base64, and every
payload-bearing step this test can run in a throwaway plugins root writes exactly
the bytes of its source of record, with the mode it had before.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_subject import (
    DOD_GATE_SUBJECT_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PAYLOAD_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PUBLICATION_BODY_FILENAME,
    PublicationMetadata,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_guard import (
    REVIEW_GUARD_PROGRAM_FILENAME,
    review_guard_program_source,
)

from tests.prepare_step_support import env_of, steps_in

_COMMITTED = '[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n'
# Text carrying every character an earlier transport broke on: shell syntax, a
# non-BMP emoji (a TOML surrogate-pair hazard), a multi-byte letter and DEL.
_HAZARDS = "$(touch /tmp/never) `date` ${HOME} \\n \U0001f916 é \x7f\n"
_BODY = f"Work-item bd-x {_HAZARDS}\n## Definition of Done\n\n- one.\n"
_SUBJECT = f"## Subject\n\n{_HAZARDS}" * 40
_BASE64_LINE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _overlay(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
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
        dod_gate_subject=_SUBJECT,
    )
    assert overlay is not None
    return overlay


def test_every_prepare_payload_value_is_single_line_base64(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No payload rides as plain text, so none pays JSON escaping in the collected file."""
    overlay = _overlay(tmp_path=tmp_path, monkeypatch=monkeypatch)
    payloads = {
        f"{index}:{name}": value
        for index, step in enumerate(steps_in(block=overlay))
        for name, value in step.env.items()
        if name.startswith(PAYLOAD_ENV_VAR)
    }
    plain = sorted(name for name, value in payloads.items() if not _BASE64_LINE.match(value))
    facts = [len(payloads) >= 20, plain == []]
    assert all(facts), (len(payloads), plain)


def test_the_payload_steps_land_their_sources_byte_for_byte_with_their_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running each step the way the engine's shell does materializes the exact source."""
    overlay = _overlay(tmp_path=tmp_path, monkeypatch=monkeypatch)
    plugins_root = tmp_path / "plugins"
    clone = tmp_path / "clone"
    clone.mkdir()
    _ = subprocess.run(["git", "init", "-q", str(clone)], check=True)
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins_root),
    }
    runnable = [
        step
        for step in steps_in(block=overlay)
        if step.env and ".livespec-gh-refresh" not in step.script
    ]
    failures = [
        f"{step.script}\n{completed.stderr}"
        for step in runnable
        for completed in [
            subprocess.run(
                ["sh", "-c", "umask 022\n" + step.script],
                cwd=clone,
                env=env_of(step=step, base=base),
                capture_output=True,
                text=True,
                check=False,
            )
        ]
        if completed.returncode != 0
    ]
    expected = {
        REVIEW_GUARD_PROGRAM_FILENAME: review_guard_program_source(),
        RECORD_FILE_MERGE_PROGRAM_FILENAME: record_file_merge_program_source(),
        PUBLICATION_BODY_FILENAME: _BODY,
        DOD_GATE_SUBJECT_FILENAME: _SUBJECT,
    }
    mismatched = sorted(
        name
        for name, text in expected.items()
        if (plugins_root / name).read_bytes() != text.encode("utf-8")
    )
    modes = {
        name: (plugins_root / name).stat().st_mode & 0o777
        for name in (*expected, PUBLICATION_PUSH_PROGRAM_FILENAME)
    }
    facts = [
        len(runnable) >= 15,
        failures == [],
        mismatched == [],
        modes == {**dict.fromkeys(expected, 0o644), PUBLICATION_PUSH_PROGRAM_FILENAME: 0o700},
    ]
    assert all(facts), (len(runnable), failures, mismatched, modes)
