"""Re-resolving the credential per round, so a rotation reaches a parked loop.

Covers the defect measured on this host 2026-10-08 (`bd-ib-o6aeji`): four
dispatch loops parked on `credential-reprobe-refused` from 08:54Z and 11:42Z,
re-probing every 300 seconds, kept journaling `exhausted` at 23:05Z, 23:08Z and
23:10Z — after the maintainer had rotated the Claude credential at roughly
23:00Z and other repositories' dispatches had started running on the same
factory within minutes. The cause was that every round re-probed the value the
credential wrapper injected when the loop was LAUNCHED, so a rotation could
never reach a parked loop and the four had to be stopped and re-dispatched by
hand.

THE PROBE IS KEYED ON THE TOKEN, and that is the whole instrument. A probe
scripted by CALL INDEX returns `usable` on its second call whether the
implementation re-resolved anything or re-probed the stale value, so it cannot
tell the repair from the defect. Keying the classification on the token VALUE
makes the stale reading unable to pass: a build that keeps reading the
launch-time environment probes the stale token on every round and leaves the
wait only when its budget runs out.

THE NEW MODULE IS REACHED THROUGH `importlib` inside the test body rather than
by a module-level import, so the Red commit of this slice fails on a genuine
assertion (`module_path.is_file()`) instead of dying at collection on a
`ModuleNotFoundError`, which would prove only that the module is missing.
"""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_policy_settings
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_ROTATION_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_rotation"
_REPROBE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe"
_CADENCE_KEY = "credential_reprobe_interval_seconds"
# The wrapper the incident's dispatch target declares, as argv rather than as a
# command line: the reader returns the declaration verbatim and nothing here
# ever executes it.
_WRAPPER = ("/data/projects/1password-env-wrapper/with-livespec-env.sh", "--")
_STALE_TOKEN = "stale-oauth-token"
_ROTATED_TOKEN = "rotated-oauth-token"


def _module(*, name: str) -> Any:
    """A module under test, imported inside the body (see the module docstring)."""
    return importlib.import_module(name)


def _rotation_module_path() -> Path:
    return Path(_dispatcher_policy_settings.__file__).parent / "_dispatcher_credential_rotation.py"


def _repo(*, tmp_path: Path, cadence: int) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "credential_wrapper": list(_WRAPPER),
                "livespec-orchestrator-beads-fabro": {"dispatcher": {_CADENCE_KEY: cadence}},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _journal(*, repo: Path) -> JournalFile:
    return JournalFile(path=repo / "journal.jsonl")


def _refused(*, journal: JournalFile, stage: str) -> list[dict[str, Any]]:
    """Every refused-probe record on the journal, which each case here writes."""
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    return [record for record in records if record["stage"] == stage]


class _TokenKeyedProbe:
    """A probe whose verdict is a function of the TOKEN, never of the call index.

    Every token but the rotated one classifies `exhausted`, which is the one
    condition the wait governs; the rotated one classifies `usable`. A build
    that re-probes the launch-time value therefore never leaves the wait on a
    usable result.
    """

    def __init__(self) -> None:
        self.tokens: list[str] = []

    def __call__(self, *, token: str) -> ClaudeCredentialStatus:
        self.tokens.append(token)
        usable = token == _ROTATED_TOKEN
        return ClaudeCredentialStatus(
            condition="usable" if usable else "exhausted",
            present=True,
            usable=usable,
            http_status=200 if usable else 429,
            error_type=None if usable else "rate_limit_error",
            input_tokens=None,
            output_tokens=None,
            message="token-keyed probe stand-in",
            remedy="token-keyed probe stand-in",
        )


class _Wrapper:
    """A stand-in for the one bounded wrapper invocation, scripted per round.

    The empty string is what the production reader returns for every value that
    did not arrive, so a scripted `""` is a wrapper that supplied nothing.
    """

    def __init__(self, *, values: list[str]) -> None:
        self.values = values
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def __call__(
        self,
        *,
        wrapper: tuple[str, ...],
        env_name: str,
        environ: Mapping[str, str],
    ) -> str:
        _ = environ
        self.calls.append((wrapper, env_name))
        return self.values[min(len(self.calls) - 1, len(self.values) - 1)]


def test_a_rotated_credential_reaches_the_parked_wait_on_its_next_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Red assertion of this slice, then the behaviour it exists for.

    The wrapper injects the stale value on the first round — nothing has
    rotated yet — and the rotated value on the second, which is the rotation
    landing while the loop is parked. One refused probe is journaled and the
    wait returns, so admission resumes WITHOUT the loop being restarted; the
    launch-time environment is asserted UNCHANGED, because a build that
    repaired this by rewriting its own process environment would satisfy
    everything else here while leaving a mutation no caller asked for.
    """
    assert _rotation_module_path().is_file()

    rotation = _module(name=_ROTATION_MODULE)
    reprobe = _module(name=_REPROBE_MODULE)
    repo = _repo(tmp_path=tmp_path, cadence=3)
    journal = _journal(repo=repo)
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _STALE_TOKEN)
    wrapper = _Wrapper(values=[_STALE_TOKEN, _ROTATED_TOKEN])
    monkeypatch.setattr(rotation, "read_wrapper_credential", wrapper)
    probe = _TokenKeyedProbe()
    slept: list[float] = []

    result = reprobe.await_usable_credential(
        repo=repo, journal=journal, budget=5, probe=probe, sleep=slept.append
    )

    assert result is None
    assert probe.tokens == [_STALE_TOKEN, _ROTATED_TOKEN]
    assert slept == [3]
    assert len(_refused(journal=journal, stage=reprobe.CREDENTIAL_REPROBE_STAGE)) == 1
    # The wrapper was consulted once per round, for the selected credential.
    assert wrapper.calls == [(_WRAPPER, CLAUDE_OAUTH_TOKEN_ENV)] * 2
    assert os.environ[CLAUDE_OAUTH_TOKEN_ENV] == _STALE_TOKEN


def test_consecutive_refused_rows_show_whether_the_credential_value_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each refused row carries a non-secret identity of the value it probed.

    Asserted in BOTH directions over one wait, because either direction alone
    is satisfied by a build nobody would want: an implementation stamping a
    CONSTANT satisfies the two rows that must agree while making a rotation
    invisible, and one stamping a per-round NONCE satisfies the two that must
    differ while reporting a change that never happened. Rows 1 and 2 probe
    different values and must differ; rows 2 and 3 probe the same value and
    must agree.

    The identity is also compared against the module's own primitive rather
    than merely being present, since "some opaque string is in the row" says
    nothing about whether it identifies THIS credential; and every row is
    searched for the credential values themselves, because the row's whole
    purpose is to be legible in an audit journal an operator reads.
    """
    rotation = _module(name=_ROTATION_MODULE)
    reprobe = _module(name=_REPROBE_MODULE)
    repo = _repo(tmp_path=tmp_path, cadence=1)
    journal = _journal(repo=repo)
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _STALE_TOKEN)
    first = "first-rate-limited-token"
    second = "second-rate-limited-token"
    monkeypatch.setattr(
        rotation,
        "read_wrapper_credential",
        _Wrapper(values=[first, second, second, _ROTATED_TOKEN]),
    )

    reprobe.await_usable_credential(
        repo=repo,
        journal=journal,
        budget=9,
        probe=_TokenKeyedProbe(),
        sleep=lambda _seconds: None,
    )

    rows = _refused(journal=journal, stage=reprobe.CREDENTIAL_REPROBE_STAGE)
    assert len(rows) == 3
    assert rows[0].get("credential_identity") is not None
    assert rows[0]["credential_identity"] != rows[1]["credential_identity"]
    assert rows[1]["credential_identity"] == rows[2]["credential_identity"]
    assert rows[0]["credential_identity"] == rotation.credential_identity(token=first)
    assert rows[1]["credential_identity"] == rotation.credential_identity(token=second)
    assert [row["credential_source"] for row in rows] == [rotation.WRAPPER_SOURCE] * 3
    serialized = json.dumps(rows)
    assert first not in serialized
    assert second not in serialized
    assert _STALE_TOKEN not in serialized
