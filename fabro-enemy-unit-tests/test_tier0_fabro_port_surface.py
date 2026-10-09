"""Tier 0 Enemy Unit Tests for the facade verbs the live suite never ran.

Nine verbs the Dispatcher calls had no Enemy Unit Test as of 2026-10-09, so
nothing about them was evidence: a pinned-versus-candidate comparison came
back green having never touched the export, the capability read, the
server-API face or the credential resolution. Seven of them are read-only and
spend no run time, so they belong here beside the other tier 0 reads; `cancel`
needs a live run and is in `test_tier1_fabro_port_lifecycle.py`.

Like its tier 0 siblings this suite sits outside `tests/` so the hermetic
`just check` aggregate never needs a live Fabro server or credentials. Invoke
it explicitly:

    just fabro-enemy-tier0

TWO OF THESE CASES ASSERT A REFUSAL, which needs saying because a refusal is
easy to earn by never reaching the server at all. `questions` and
`answer_question` are driven against a run id the factory does not hold, and
both assert a NON-ZERO HTTP STATUS rather than merely `succeeded is False`: a
status of 0 is this port's own "no response was received", so it is exactly
what a wrong host, a dead proxy or an unresolvable name produces. Requiring a
real status code is what separates "the server considered the request and
declined" from "the request never arrived".

`auth_login` IS DRIVEN UNDER A SCRATCH HOME, deliberately. `fabro auth login`
writes `~/.fabro/auth.json`, which on an operator host is the live factory
credential every other client on the box shares. Pointing `HOME` at `tmp_path`
means the verb runs against the real server with a real argv while being
structurally unable to touch that file — and the case asserts the scratch file
was not written either, so a build that somehow accepted a bogus token would
fail here rather than quietly succeed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, cast

import pytest
from _tier0_support import (
    TIMEOUT_SECONDS,
    _assert_success,
    _completed_run_id,
    _FabroTier0Config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_auth import (
    FABRO_AUTH_FILE_RELATIVE,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import SYSTEM_INFO_PATH

__all__: list[str] = []

_DUMP_TIMEOUT_SECONDS = 300.0
# A run id the factory cannot hold: the ULID alphabet with a shape no run uses.
_ABSENT_RUN_ID = "01ENEMYUNITTESTABSENTRUN0"
_ABSENT_QUESTION_ID = "00000000-0000-0000-0000-000000000000"
_BOGUS_DEV_TOKEN = "fabro-enemy-unit-test-not-a-credential"
_HTTP_UNAUTHORIZED = 401
_CLIENT_ERROR_FLOOR = 400
_CAPABILITIES_KEY = "capabilities"
_SECRET_SET_NAME = "LIVESPEC_EUT_NATIVE_SECRET_CHANNEL"
_SECRET_SET_VALUE = "fabro-enemy-unit-test-not-a-credential"


def test_system_info_reports_this_factory_build_and_its_capability_list(
    *,
    port: FabroPort,
) -> None:
    """The read the ACP capability gate FAILS CLOSED on when it cannot be made.

    The gate refuses a chain carrying `config_options` unless this answer
    advertises the capability, and it treats an unreadable answer as "not
    advertised". So the shape matters as much as the content: a payload that
    is not a mapping, or that carries `capabilities` as something other than a
    list, is indistinguishable at the gate from a server that declined.
    """
    result = port.server_api().system_info(timeout_seconds=TIMEOUT_SECONDS)

    assert result.succeeded, f"status {result.status}: {result.error or result.body}"
    assert isinstance(result.payload, dict)
    payload = cast("dict[str, Any]", result.payload)
    advertised = payload.get(_CAPABILITIES_KEY)
    # An ABSENT key is a legitimate answer from an older build; a key carrying
    # a non-list is not, and the gate cannot tell the two apart.
    assert advertised is None or isinstance(advertised, list)
    assert SYSTEM_INFO_PATH.startswith("/api/")


def test_client_version_reports_the_client_build_alone(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    """`fabro --version` asks no server; `fabro version` asks this one.

    The dispatch record stamps WHICH BINARY drove it, and reads that from the
    local flag precisely so a dispatch never puts a network call on its own
    path. A build whose `--version` reached out would make the two verbs
    interchangeable, and this is the assertion that would notice.
    """
    client = port.client_version(timeout_seconds=TIMEOUT_SECONDS)

    _assert_success(command=client.command)
    assert config.expected_client_version in client.text
    assert config.expected_client_commit in client.text
    # The discriminating observation: the SERVER's own build and url, which
    # `version` reports, are absent here.
    assert "server" not in client.text.lower()
    assert config.server_url not in client.text


def test_secret_set_stores_a_noncredential_canary_without_echoing_it(
    *,
    port: FabroPort,
) -> None:
    """The candidate vault accepts a value through stdin and does not echo it.

    The key and value are deliberately fixed, recognisable non-credentials: an
    explicit Enemy Unit Test run overwrites one dedicated canary entry rather
    than accumulating secrets, and no operator credential enters this process.
    Older engines without the native secret channel fail this assertion, which
    is the capability delta the pinned-versus-candidate comparison must expose.
    """
    with tempfile.TemporaryFile() as handle:
        _ = handle.write(_SECRET_SET_VALUE.encode("utf-8"))
        _ = handle.seek(0)
        result = port.secret_set(
            secret_name=_SECRET_SET_NAME,
            stdin=handle.fileno(),
            timeout_seconds=TIMEOUT_SECONDS,
        )

    _assert_success(command=result)
    assert _SECRET_SET_VALUE not in result.stdout
    assert _SECRET_SET_VALUE not in result.stderr


def test_dump_exports_a_completed_run_into_the_requested_directory(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
    tmp_path: Path,
) -> None:
    """The export the preserve-by-reference pointer promises is retrievable.

    A pointer is a PROMISE that a failed run's work can still be fetched, and
    both the writer and the reader of that promise rest on this verb behaving
    as assumed. The assertion is on FILES ON DISK rather than the exit code: a
    `dump` that exited 0 and wrote nothing would satisfy the writer's own
    success test while leaving every pointer it produced undigested.
    """
    run_id = config.completed_run_id or _completed_run_id(port=port)
    export_dir = tmp_path / "export"

    result = port.dump(
        run_id=run_id,
        output_dir=export_dir,
        timeout_seconds=_DUMP_TIMEOUT_SECONDS,
    )

    _assert_success(command=result.command)
    assert export_dir.is_dir()
    exported = sorted(path for path in export_dir.rglob("*") if path.is_file())
    assert exported, f"fabro dump exited 0 but exported no file into {export_dir}"


def test_dump_of_a_run_the_factory_does_not_hold_fails_rather_than_exports_nothing(
    *,
    port: FabroPort,
    tmp_path: Path,
) -> None:
    """The dangling half of the same promise.

    The pointer reader calls a non-zero exit `dangling` and an empty export
    `unverifiable`, which are different verdicts with different remedies. That
    split is only correct while the engine REFUSES an absent run instead of
    exporting an empty directory for it.
    """
    export_dir = tmp_path / "absent"

    result = port.dump(
        run_id=_ABSENT_RUN_ID,
        output_dir=export_dir,
        timeout_seconds=_DUMP_TIMEOUT_SECONDS,
    )

    assert result.command.exit_code != 0
    assert not sorted(path for path in export_dir.rglob("*") if path.is_file())


def test_the_server_api_face_carries_this_ports_own_factory(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
) -> None:
    """`server_api()` cannot reach a factory its CLI port was not built for.

    This is the whole reason the reconciler goes through the port: the two
    transports speak to ONE target, so a cancel cannot land on a factory the
    inspect came from.
    """
    face = port.server_api()

    assert face.target is port.target
    assert face.target.server_url == config.server_url


def test_bearer_token_resolution_matches_what_the_server_accepts(
    *,
    port: FabroPort,
) -> None:
    """The credential the port resolves is the one this server honours.

    Driven against a run the factory does not hold, so the discriminator is
    the STATUS rather than the body: with a credential resolved the server
    gets far enough to say the run is unknown, and without one it refuses at
    the door with 401. Those two outcomes have completely different remedies
    and the reconciler journals them by name, so conflating them is how "no
    credential resolved" comes to read as "a healthy server declined the act".
    """
    face = port.server_api()
    token = face.bearer_token()

    result = face.questions(run_id=_ABSENT_RUN_ID, timeout_seconds=TIMEOUT_SECONDS)

    # A status of 0 is this port's "no response arrived at all", which is what
    # a wrong host produces; requiring a real code is what proves the server
    # considered the request.
    assert result.status >= _CLIENT_ERROR_FLOOR, f"status {result.status}: {result.error}"
    if token is None:
        assert result.status == _HTTP_UNAUTHORIZED
    else:
        assert result.status != _HTTP_UNAUTHORIZED


def test_answering_a_question_the_factory_does_not_hold_is_declined_not_accepted(
    *,
    port: FabroPort,
) -> None:
    """The answer route refuses an unknown question rather than reporting success.

    The reconciler reads any non-2xx as "this route did not work" and falls
    through to the DESTRUCTIVE last resort. An engine that accepted an answer
    for a question it does not hold would make that fallback unreachable while
    nothing was actually answered.
    """
    result = port.server_api().answer_question(
        run_id=_ABSENT_RUN_ID,
        question_id=_ABSENT_QUESTION_ID,
        option_key="A",
        timeout_seconds=TIMEOUT_SECONDS,
    )

    assert not result.succeeded
    assert result.status >= _CLIENT_ERROR_FLOOR, f"status {result.status}: {result.error}"


def test_auth_login_refuses_a_bogus_dev_token_and_writes_no_credential(
    *,
    config: _FabroTier0Config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`fabro auth login` reaches this server and declines an invalid token.

    Run under a SCRATCH HOME: the verb's whole effect is to write
    `~/.fabro/auth.json`, which on an operator host is the live factory
    credential. The scratch file is asserted absent afterwards, so an engine
    that accepted the bogus token fails here instead of persisting it.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    port = FabroPort(
        fabro_bin=config.fabro_bin,
        target=FabroTarget(server_url=config.server_url, dev_token=_BOGUS_DEV_TOKEN),
        runner=ShellCommandRunner(),
        cwd=tmp_path,
    )

    result = port.auth_login(timeout_seconds=TIMEOUT_SECONDS)

    assert result is not None
    assert result.command.exit_code != 0
    written = tmp_path / FABRO_AUTH_FILE_RELATIVE
    assert not written.is_file() or _BOGUS_DEV_TOKEN not in json.dumps(
        json.loads(written.read_text(encoding="utf-8"))
    )


def test_auth_login_is_a_local_no_op_for_a_factory_declaring_no_dev_token(
    *,
    config: _FabroTier0Config,
    tmp_path: Path,
) -> None:
    """No declared token means no subprocess, which is the Dispatcher's path.

    Every dispatch calls `auth_login` unconditionally and discards the result,
    so on the ordinary factory — which declares no dev token — this must cost
    nothing at all. This is the control for the case above: without it, that
    refusal is equally consistent with a verb that refuses every invocation.
    """
    port = FabroPort(
        fabro_bin=config.fabro_bin,
        target=FabroTarget(server_url=config.server_url),
        runner=_RefusingRunner(),
        cwd=tmp_path,
    )

    assert port.auth_login(timeout_seconds=TIMEOUT_SECONDS) is None


class _RefusingRunner:
    """A runner that fails the test if the port spawns anything through it."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> Any:
        _ = (cwd, timeout_seconds, env, stdin)
        pytest.fail(f"auth_login spawned a subprocess with no declared dev token: {argv}")
