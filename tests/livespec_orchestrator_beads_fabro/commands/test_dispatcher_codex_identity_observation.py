"""Tests for the opt-in host Codex credential identity observation."""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

_NOW = 1_000_000
# Far enough out that the alarm stays quiet, so an observation assertion is
# never confused with the pre-existing alarm exit code.
_FRESH_EXP = _NOW + 900_000

_CLAIMS_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_identity_claims.py"
)
_STATE_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_identity_state.py"
)
_OBSERVATION_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_identity_observation.py"
)
_COMMAND_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_codex_identity_command.py"
)
_OBSERVATION_KEY = "identity_observation"


def _jwt_auth_json(*, claims: object) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return json.dumps({"tokens": {"access_token": f"header.{payload}.sig"}})


def _auth_json(*, exp: int = _FRESH_EXP, session_id: str = "session-one", jti: str) -> str:
    return _jwt_auth_json(claims={"exp": exp, "session_id": session_id, "jti": jti})


def _codex_auth() -> Any:
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth"
    )


def _dispatcher() -> Any:
    return importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")


def _pin_host_auth(*, monkeypatch: pytest.MonkeyPatch, auth_json: str | None) -> None:
    codex_auth = _codex_auth()
    monkeypatch.setattr(codex_auth.time, "time", lambda: float(_NOW))
    monkeypatch.setattr(codex_auth, "read_host_codex_auth", lambda: auth_json)


def _observe(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    state_path: Path,
    auth_json: str | None,
) -> dict[str, Any]:
    _pin_host_auth(monkeypatch=monkeypatch, auth_json=auth_json)
    _ = _dispatcher().main(
        argv=["codex-cred-status", "--json", "--observe-identity-state", str(state_path)]
    )
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    observation: dict[str, Any] = payload["identity_observation"]
    return observation


def _observe_with_real_host_read(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    codex_home: Path,
    state_path: Path,
    auth_json: str,
) -> tuple[int, dict[str, Any], bytes]:
    """Drive the public CLI through its REAL host credential read.

    The stubbed reader used elsewhere cannot establish anything about the file
    on disk, and the destination guard is precisely a claim about that file.
    """
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_file = codex_home / "auth.json"
    _ = auth_file.write_text(auth_json, encoding="utf-8")
    before = auth_file.read_bytes()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(_codex_auth().time, "time", lambda: float(_NOW))

    exit_code = _dispatcher().main(
        argv=["codex-cred-status", "--json", "--observe-identity-state", str(state_path)]
    )

    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    observation: dict[str, Any] = payload[_OBSERVATION_KEY]
    return exit_code, observation, before


def test_opt_in_observation_compares_a_changed_access_token_with_the_prior_one(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert _CLAIMS_MODULE_PATH.is_file()
    assert _STATE_MODULE_PATH.is_file()
    assert _OBSERVATION_MODULE_PATH.is_file()
    assert _COMMAND_MODULE_PATH.is_file()

    state_path = tmp_path / "private" / "codex-identity.json"
    first = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(jti="token-one"),
    )
    second = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(jti="token-two"),
    )

    assert first["prior_state"] == "absent"
    assert first["token_change"] == "first-observation"
    assert "state_write" in first
    assert first["state_write"] == "recorded"
    assert second["prior_state"] == "readable"
    assert second["token_change"] == "changed"
    assert second["token_fingerprint"] != first["token_fingerprint"]


@pytest.mark.parametrize(
    "destination",
    [
        pytest.param(lambda home: home / "auth.json", id="exact"),
        pytest.param(lambda home: home / "." / "sub" / ".." / "auth.json", id="lexical-alias"),
        pytest.param(lambda home: home.parent / "home-link" / "auth.json", id="symlinked-parent"),
        pytest.param(lambda home: home / "hardlink.json", id="hardlink"),
    ],
)
def test_observation_refuses_a_destination_that_is_the_source_credential(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    destination: Any,
) -> None:
    # SYNTHETIC credential in a disposable directory throughout. Writing
    # observation state over `auth.json` destroys the host's refresh token, so
    # the guarantee under test is that the bytes do not move.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(parents=True)
    (codex_home / "sub").mkdir()
    (tmp_path / "home-link").symlink_to(codex_home, target_is_directory=True)
    auth_json = _auth_json(jti="token-one")
    _ = (codex_home / "auth.json").write_text(auth_json, encoding="utf-8")
    if destination(codex_home).name == "hardlink.json":
        (codex_home / "hardlink.json").hardlink_to(codex_home / "auth.json")

    exit_code, observation, before = _observe_with_real_host_read(
        capsys=capsys,
        monkeypatch=monkeypatch,
        codex_home=codex_home,
        state_path=destination(codex_home),
        auth_json=auth_json,
    )

    assert (codex_home / "auth.json").read_bytes() == before
    assert observation["state_write"] == "refused"
    assert "credential" in observation["state_write_detail"]
    assert observation["prior_state"] == "refused"
    assert observation["session_change"] == "unknown"
    assert observation["token_change"] == "unknown"
    # The refusal is about the destination, not the credential, so the exit code
    # still follows the lifetime alarm exactly as it did before the option.
    assert exit_code == 0


def test_a_distinct_destination_beside_the_credential_is_still_recorded(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The control the guard needs: a destination in the SAME directory as the
    # credential is perfectly fine, so the refusal keys on the path rather than
    # on proximity.
    codex_home = tmp_path / "codex-home"
    auth_json = _auth_json(jti="token-one")

    exit_code, observation, before = _observe_with_real_host_read(
        capsys=capsys,
        monkeypatch=monkeypatch,
        codex_home=codex_home,
        state_path=codex_home / "identity.json",
        auth_json=auth_json,
    )

    assert (codex_home / "auth.json").read_bytes() == before
    assert observation["state_write"] == "recorded"
    assert observation["prior_state"] == "absent"
    assert exit_code == 0


def test_the_temporary_the_writer_uses_is_guarded_too(*, tmp_path: Path) -> None:
    state_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_state"
    )

    assert "identity_state_collision" in state_module.__all__
    protected = tmp_path / "guarded.tmp"
    # The write lands on `<destination>.tmp` first and UNLINKS it before
    # opening, so a destination whose temporary is the protected path destroys
    # that file before any replace happens. Not reachable through the CLI today
    # — the credential is always named `auth.json`, which no `.tmp` sibling can
    # equal — so the guarantee is asserted where it lives.
    assert (
        state_module.identity_state_collision(
            state_path=tmp_path / "guarded", protected_path=protected
        )
        is not None
    )
    assert (
        state_module.identity_state_collision(
            state_path=tmp_path / "elsewhere", protected_path=protected
        )
        is None
    )


def test_observation_reports_the_session_and_token_identifiers_independently(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"

    _ = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(session_id="session-one", jti="token-one"),
    )
    # The signature of an ordinary refresh-token exchange: the sign-in session
    # is extended while a brand-new access token is minted under it.
    rotated = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(session_id="session-one", jti="token-two"),
    )
    reauthenticated = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(session_id="session-two", jti="token-three"),
    )

    assert "session_change" in rotated
    assert rotated["session_change"] == "unchanged"
    assert rotated["token_change"] == "changed"
    assert reauthenticated["session_change"] == "changed"
    assert reauthenticated["token_change"] == "changed"


def test_observation_reports_an_absent_claim_as_unknown_rather_than_unchanged(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"

    _ = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(session_id="session-one", jti="token-one"),
    )
    # A credential that decodes but carries no session claim: the identifier
    # cannot be compared, which is not the same fact as it having held.
    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_jwt_auth_json(claims={"exp": _FRESH_EXP, "jti": "token-one"}),
    )

    assert observation["session_change"] == "unknown"
    assert observation["token_change"] == "unchanged"


def test_observation_reports_unreadable_claims_as_unknown_on_both_identifiers(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"

    _ = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(session_id="session-one", jti="token-one"),
    )
    observation = _observe(
        capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=None
    )

    assert observation["claims_readable"] is False
    assert observation["session_change"] == "unknown"
    assert observation["token_change"] == "unknown"


def test_observation_reports_a_held_access_token_identifier_as_unchanged(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"
    auth_json = _auth_json(jti="token-one")

    first = _observe(
        capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=auth_json
    )
    second = _observe(
        capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=auth_json
    )

    assert first["token_change"] == "first-observation"
    assert second["token_change"] == "unchanged"
    assert second["token_fingerprint"] == first["token_fingerprint"]


def test_ordinary_status_writes_no_observation_state_without_the_opt_in(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert _COMMAND_MODULE_PATH.is_file()

    state_path = tmp_path / "codex-identity.json"
    _pin_host_auth(monkeypatch=monkeypatch, auth_json=_auth_json(jti="token-one"))

    exit_code = _dispatcher().main(argv=["codex-cred-status", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert "identity_observation" not in payload
    assert not state_path.exists()


def test_observation_of_an_absent_credential_reads_no_identifiers(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"

    first = _observe(capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=None)
    second = _observe(capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=None)

    assert first["claims_readable"] is False
    assert first["token_fingerprint"] is None
    assert first["expires_at_epoch"] is None
    # Nothing was recorded, so the second blind reading is STILL a first
    # observation rather than a comparison against a fabricated empty record.
    assert first["state_write"] == "withheld"
    assert second["prior_state"] == "absent"
    assert second["token_change"] == "first-observation"


def test_observation_of_an_undecodable_credential_reads_no_identifiers(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=tmp_path / "codex-identity.json",
        auth_json="{not json at all",
    )

    assert observation["claims_readable"] is False
    assert observation["token_fingerprint"] is None


def test_observation_of_a_token_payload_that_is_not_an_object_reads_no_identifiers(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A JWT whose payload decodes to a JSON scalar: the segment is valid
    # base64 and valid JSON, so only a claim-set shape check catches it.
    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=tmp_path / "codex-identity.json",
        auth_json=_jwt_auth_json(claims=5),
    )

    assert observation["claims_readable"] is False


def test_observation_of_a_token_carrying_no_identity_claim_reports_no_fingerprint(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=tmp_path / "codex-identity.json",
        auth_json=_jwt_auth_json(claims={"exp": _FRESH_EXP}),
    )

    # Decoded, so the reading is readable — the claim simply is not there.
    assert observation["claims_readable"] is True
    assert observation["token_fingerprint"] is None
    assert observation["expires_at_epoch"] == _FRESH_EXP


def test_observation_of_a_token_carrying_no_integer_expiry_reports_no_expiry(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"
    auth_json = _jwt_auth_json(claims={"exp": "soon", "jti": "token-one"})

    observation = _observe(
        capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=auth_json
    )
    # Read back, so an absent expiry survives the round trip as absent rather
    # than as some stand-in instant.
    reread = _observe(
        capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=auth_json
    )

    assert observation["expires_at_epoch"] is None
    assert observation["token_fingerprint"] is not None
    assert reread["prior_state"] == "readable"
    assert reread["token_change"] == "unchanged"


def test_an_unreadable_reading_is_withheld_so_the_preceding_one_survives(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"

    first = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(jti="token-one"),
    )
    # A transient blind moment — codex mid-login, the file briefly gone. The
    # reading itself is honestly unreadable, but RECORDING it would overwrite
    # the last good fingerprints and leave every later reading comparing
    # against nothing.
    blind = _observe(capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=None)
    recovered = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(jti="token-two"),
    )

    assert "state_write" in blind
    assert blind["state_write"] == "withheld"
    assert "unreadable" in blind["state_write_detail"]
    # The blind reading left the file alone, so this one still compares against
    # the real preceding observation rather than against the blip.
    assert recovered["token_change"] == "changed"
    assert recovered["prior_state"] == "readable"
    assert (
        json.loads(state_path.read_text(encoding="utf-8"))["token_fingerprint"]
        != (first["token_fingerprint"])
    )
    assert recovered["state_write"] == "recorded"


def test_observation_reports_a_state_file_it_could_not_write(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "not-a-directory"
    _ = blocker.write_text("", encoding="utf-8")

    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=blocker / "codex-identity.json",
        auth_json=_auth_json(jti="token-one"),
    )

    assert "state_write" in observation
    assert observation["state_write"] == "failed"
    assert "could not be written" in observation["state_write_detail"]


def test_a_prior_state_file_that_is_not_utf8_is_unreadable_rather_than_fatal(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"
    # A real decoding failure, not a JSON one: these bytes are a UTF-16 byte
    # order mark, so `read_text(encoding="utf-8")` raises before any parser is
    # reached. `UnicodeDecodeError` is a ValueError, so an OSError-only guard
    # cannot see it and the status command died on a file it was only reading.
    _ = state_path.write_bytes(b"\xff\xfe")

    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(jti="token-one"),
    )

    assert observation["prior_state"] == "unreadable"
    assert observation["session_change"] == "unknown"
    assert observation["token_change"] == "unknown"
    assert "UTF-8" in observation["prior_state_detail"]
    # The promised write outcome still arrives: the undecodable record is
    # replaced by a good one rather than leaving the path poisoned forever.
    assert observation["state_write"] == "recorded"
    assert json.loads(state_path.read_text(encoding="utf-8"))["token_fingerprint"] is not None


def test_a_credential_file_that_is_not_utf8_reads_as_absent_rather_than_fatal(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The same decoding hazard on the credential itself. `read_host_codex_auth`
    # has always documented "None when the file is missing/unreadable"; an
    # undecodable file is unreadable, and letting the error escape turned the
    # whole command — and the dispatch projection that shares this read — into a
    # traceback instead of the actionable refusal.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    _ = (codex_home / "auth.json").write_bytes(b"\xff\xfe")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(_codex_auth().time, "time", lambda: float(_NOW))

    exit_code = _dispatcher().main(
        argv=[
            "codex-cred-status",
            "--json",
            "--observe-identity-state",
            str(tmp_path / "codex-identity.json"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["present"] is False
    assert exit_code == 1
    assert payload[_OBSERVATION_KEY]["claims_readable"] is False


@pytest.mark.parametrize(
    "prior_text",
    [
        pytest.param("not json at all", id="unparseable"),
        pytest.param("[]\n", id="not-an-object"),
        pytest.param(json.dumps({"schema": "something-else", "observed_at_epoch": 1}), id="schema"),
        pytest.param(
            json.dumps({"schema": "livespec-codex-identity-observation/v1"}), id="no-when"
        ),
    ],
)
def test_observation_reports_damaged_prior_state_rather_than_declaring_stability(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    prior_text: str,
) -> None:
    state_path = tmp_path / "codex-identity.json"
    _ = state_path.write_text(prior_text, encoding="utf-8")

    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(jti="token-one"),
    )

    # Not "absent" — a file IS there — and emphatically not "unchanged": a
    # record this reading cannot parse is no evidence that anything held.
    assert observation["prior_state"] == "unreadable"
    assert observation["session_change"] == "unknown"
    assert observation["token_change"] == "unknown"
    assert observation["prior_state_detail"] != ""


def test_observation_reports_prior_state_it_cannot_open_as_unreadable(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A directory at the state path: it exists, so it is not absent, and it
    # cannot be read, so it is not a prior observation either.
    state_path = tmp_path / "codex-identity.json"
    state_path.mkdir()

    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_auth_json(jti="token-one"),
    )

    assert observation["prior_state"] == "unreadable"
    assert observation["token_change"] == "unknown"


def test_observation_state_file_is_private_and_leaves_no_temporary_behind(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "private" / "codex-identity.json"

    for jti in ("token-one", "token-two"):
        _ = _observe(
            capsys=capsys,
            monkeypatch=monkeypatch,
            state_path=state_path,
            auth_json=_auth_json(jti=jti),
        )
        # Asserted after EVERY write, because an update that replaces the file
        # is exactly where a restrictive mode gets silently widened.
        assert state_path.stat().st_mode & 0o777 == 0o600
        assert state_path.parent.stat().st_mode & 0o777 == 0o700
        assert sorted(p.name for p in state_path.parent.iterdir()) == [state_path.name]


def test_observation_persists_no_raw_token_or_claim_value(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"
    auth_json = _auth_json(session_id="session-secret", jti="token-secret")
    access_token = json.loads(auth_json)["tokens"]["access_token"]

    observation = _observe(
        capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=auth_json
    )

    stored_text = state_path.read_text(encoding="utf-8")
    stored = json.loads(stored_text)
    assert "session-secret" not in stored_text
    assert "token-secret" not in stored_text
    assert access_token not in stored_text
    assert set(stored) == {
        "expires_at_epoch",
        "observed_at_epoch",
        "schema",
        "session_fingerprint",
        "token_fingerprint",
    }
    # Only the digests the comparison needs, and the sanitized expiry instant.
    assert stored["session_fingerprint"] == observation["session_fingerprint"]
    assert stored["token_fingerprint"] == observation["token_fingerprint"]
    assert stored["expires_at_epoch"] == _FRESH_EXP
    assert stored["observed_at_epoch"] == _NOW


def test_observation_leaves_the_provider_authentication_file_byte_identical(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    auth_file = codex_home / "auth.json"
    auth_text = _auth_json(jti="token-one")
    _ = auth_file.write_text(auth_text, encoding="utf-8")
    before = auth_file.read_bytes()
    # The REAL host read, not a stub: the guarantee is about the file this
    # command opens, so a stubbed reader could not establish it.
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(_codex_auth().time, "time", lambda: float(_NOW))

    exit_code = _dispatcher().main(
        argv=[
            "codex-cred-status",
            "--json",
            "--observe-identity-state",
            str(tmp_path / "codex-identity.json"),
        ]
    )

    observation = json.loads(capsys.readouterr().out)["identity_observation"]
    assert exit_code == 0
    assert observation["claims_readable"] is True
    assert auth_file.read_bytes() == before


def test_observation_accepts_the_standard_session_claim_spelling(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"
    claims = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_claims"
    )

    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=state_path,
        auth_json=_jwt_auth_json(claims={"exp": _FRESH_EXP, "sid": "session-one", "jti": "t"}),
    )

    assert claims.SESSION_CLAIM_NAMES == ("session_id", "sid")
    assert observation["session_fingerprint"] == claims.fingerprint_identity_claim(
        value="session-one"
    )


def test_observation_explains_that_identifier_continuity_is_not_a_validity_claim(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observation_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_observation"
    )

    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=tmp_path / "codex-identity.json",
        auth_json=_auth_json(jti="token-one"),
    )

    assert "limitation" in observation
    limitation = observation["limitation"]
    assert limitation == observation_module.IDENTITY_CONTINUITY_LIMITATION
    # The observation measures identifier continuity and nothing else. Whether a
    # previously issued access token is still accepted is a question only the
    # provider can answer, so the reading must not be read as answering it.
    assert "does not establish" in limitation
    assert "previously issued access token" in limitation
    assert "remains valid" in limitation


def test_human_status_output_explains_the_same_limitation(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observation_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_observation"
    )
    _pin_host_auth(monkeypatch=monkeypatch, auth_json=_auth_json(jti="token-one"))

    exit_code = _dispatcher().main(
        argv=[
            "codex-cred-status",
            "--observe-identity-state",
            str(tmp_path / "codex-identity.json"),
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "identity_limitation: " in out
    assert f"identity_limitation: {observation_module.IDENTITY_CONTINUITY_LIMITATION}" in out


def test_human_status_output_carries_the_observation_lines(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "codex-identity.json"
    _pin_host_auth(monkeypatch=monkeypatch, auth_json=_auth_json(jti="token-one"))

    exit_code = _dispatcher().main(
        argv=["codex-cred-status", "--observe-identity-state", str(state_path)]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "identity_prior_state: absent" in out
    assert "identity_session_change: first-observation" in out
    assert "identity_token_change: first-observation" in out
    assert f"identity_state_path: {state_path}" in out


@given(first=st.text(min_size=1), second=st.text(min_size=1))
def test_identity_fingerprints_are_one_way_and_decide_equality(
    *,
    first: str,
    second: str,
) -> None:
    claims = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_claims"
    )

    first_digest = claims.fingerprint_identity_claim(value=first)
    second_digest = claims.fingerprint_identity_claim(value=second)

    assert (first_digest == second_digest) == (first == second)
    # Fixed-width hexadecimal whatever went in: the digest carries the
    # equality the comparison needs and none of the value's own shape.
    assert len(first_digest) == 32
    assert set(first_digest) <= set("0123456789abcdef")
