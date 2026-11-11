"""Every prepare payload is per-dispatch data, rides gzip+base64, and lands byte for byte.

The dispatch overlay is collected as the run's `workflow.toml`, and the engine
caps that ONE file at 512 KiB (Fabro `MAX_WORKFLOW_VERSION_FILE_BYTES`). After
orchestrator v0.312.3 the livespec-dev-tooling overlay measured 524,343 bytes and
every dispatch there was refused before listing, because helper programs rode
the overlay as step `env` payloads. Option D (bd-ib-jrawlp, research note 004
decision 6) moved every helper program behind the one helper-fetch step, so the
packed `LIVESPEC_PREPARE_PAYLOAD` path remains ONLY for per-dispatch data: the
pull-request body and the dod_gate subject.

These tests hold that on the WHOLE rendered overlay: the payload-bearing steps
are exactly those two, each value is single-line base64, and running each step
the way the engine's shell does writes exactly the dispatch's own bytes.
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

from tests.prepare_step_support import env_of, steps_in, unpacked

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
    """Only per-dispatch data rides as a payload, and none of it as plain text."""
    overlay = _overlay(tmp_path=tmp_path, monkeypatch=monkeypatch)
    payloads = {
        f"{index}:{name}": value
        for index, step in enumerate(steps_in(block=overlay))
        for name, value in step.env.items()
        if name.startswith(PAYLOAD_ENV_VAR)
    }
    plain = sorted(name for name, value in payloads.items() if not _BASE64_LINE.match(value))
    texts = sorted(unpacked(value=value) for name, value in payloads.items() if name not in plain)
    facts = [plain == [], texts == sorted([_BODY, _SUBJECT])]
    assert all(facts), (sorted(payloads), plain)


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
    runnable = [step for step in steps_in(block=overlay) if PAYLOAD_ENV_VAR in step.env]
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
        PUBLICATION_BODY_FILENAME: _BODY,
        DOD_GATE_SUBJECT_FILENAME: _SUBJECT,
    }
    mismatched = sorted(
        name
        for name, text in expected.items()
        if (plugins_root / name).read_bytes() != text.encode("utf-8")
    )
    modes = {name: (plugins_root / name).stat().st_mode & 0o777 for name in expected}
    facts = [
        len(runnable) == len(expected),
        failures == [],
        mismatched == [],
        modes == dict.fromkeys(expected, 0o644),
    ]
    assert all(facts), (len(runnable), failures, mismatched, modes)
