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
    assert first["state_written"] is True
    assert second["prior_state"] == "readable"
    assert second["token_change"] == "changed"
    assert second["token_fingerprint"] != first["token_fingerprint"]


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
    # The second reading proves the recorded absence reads back as an absent
    # identifier rather than as a fingerprint of the empty string.
    second = _observe(capsys=capsys, monkeypatch=monkeypatch, state_path=state_path, auth_json=None)

    assert first["claims_readable"] is False
    assert first["token_fingerprint"] is None
    assert first["expires_at_epoch"] is None
    assert second["prior_state"] == "readable"
    assert second["token_fingerprint"] is None


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
    observation = _observe(
        capsys=capsys,
        monkeypatch=monkeypatch,
        state_path=tmp_path / "codex-identity.json",
        auth_json=_jwt_auth_json(claims={"exp": "soon", "jti": "token-one"}),
    )

    assert observation["expires_at_epoch"] is None
    assert observation["token_fingerprint"] is not None


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

    assert observation["state_written"] is False
    assert "not recorded" in observation["state_write_detail"]


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
