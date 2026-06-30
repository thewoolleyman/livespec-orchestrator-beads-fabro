"""Tests for the GitHub App installation-token mint.

The pure helpers and the mint orchestration (in `commands/_app_token.py`) are
unit-tested directly with injected fake seams; the production openssl signer is
exercised against a real generated RSA key, the production urllib seam against a
localhost stub server, and the `mint_app_token` CLI via monkeypatched env — so
every line is covered without a real GitHub call.
"""

from __future__ import annotations

import base64
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import mint_app_token as cli
from livespec_orchestrator_beads_fabro.commands._app_token import (
    MintSeams,
    ResolvedToken,
    b64url,
    http_get,
    http_post,
    jwt_signing_input,
    mint_installation_token,
    normalize_pem,
    openssl_sign_rs256,
    resolve_github_token,
    resolve_installation_id,
)
from livespec_orchestrator_beads_fabro.errors import AppTokenMintError

_FLAT_PEM = (
    "-----BEGIN RSA PRIVATE KEY-----"
    "MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu"
    "-----END RSA PRIVATE KEY-----"
)


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _seams(*, sign: Any, http_get: Any, http_post: Any) -> MintSeams:
    return MintSeams(sign=sign, http_get=http_get, http_post=http_post)


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
def test_b64url_strips_padding() -> None:
    assert b64url(b"\xff\xff") == "__8"


def test_normalize_pem_passes_multiline_through() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nAAAA\n-----END RSA PRIVATE KEY-----"
    out = normalize_pem(pem)
    assert out.startswith("-----BEGIN RSA PRIVATE KEY-----\n")
    assert out.endswith("-----END RSA PRIVATE KEY-----\n")


def test_normalize_pem_reconstructs_a_flattened_key() -> None:
    lines = normalize_pem(_FLAT_PEM).strip().splitlines()
    assert lines[0] == "-----BEGIN RSA PRIVATE KEY-----"
    assert lines[-1] == "-----END RSA PRIVATE KEY-----"
    assert all(len(line) <= 64 for line in lines)
    assert len(lines) >= 3


def test_normalize_pem_accepts_escaped_newlines() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\\nAAAA\\n-----END RSA PRIVATE KEY-----"
    assert "\n" in normalize_pem(pem)


def test_normalize_pem_returns_unmatched_text_unchanged() -> None:
    assert normalize_pem("not a pem") == "not a pem"


def test_jwt_signing_input_encodes_the_claims() -> None:
    header_b64, payload_b64 = jwt_signing_input(app_id="42", issued_at=1_000_000).split(".")
    assert json.loads(_b64url_decode(header_b64)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(_b64url_decode(payload_b64)) == {
        "iat": 1_000_000 - 60,
        "exp": 1_000_000 + 540,
        "iss": "42",
    }


# --------------------------------------------------------------------------
# Production openssl signer (real key)
# --------------------------------------------------------------------------
def _generate_rsa_pem() -> str:
    completed = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, check=True)
    return completed.stdout.decode("ascii")


def test_openssl_sign_produces_a_verifiable_signature(tmp_path: Path) -> None:
    pem = _generate_rsa_pem()
    signing_input = "header.payload"
    signature = openssl_sign_rs256(signing_input, pem)
    assert signature
    (tmp_path / "key.pem").write_text(pem, encoding="ascii")
    (tmp_path / "sig.bin").write_bytes(signature)
    subprocess.run(
        [
            "openssl",
            "rsa",
            "-in",
            str(tmp_path / "key.pem"),
            "-pubout",
            "-out",
            str(tmp_path / "pub.pem"),
        ],
        capture_output=True,
        check=True,
    )
    verify = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(tmp_path / "pub.pem"),
            "-signature",
            str(tmp_path / "sig.bin"),
        ],
        input=signing_input.encode("ascii"),
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 0


def test_openssl_sign_rejects_a_bad_key() -> None:
    bad = "-----BEGIN RSA PRIVATE KEY-----\nnope\n-----END RSA PRIVATE KEY-----\n"
    with pytest.raises(AppTokenMintError, match="could not sign"):
        openssl_sign_rs256("header.payload", bad)


# --------------------------------------------------------------------------
# Production HTTP seam (localhost stub)
# --------------------------------------------------------------------------
class _StubHandler(BaseHTTPRequestHandler):
    def _emit(self) -> None:
        body = json.dumps({"method": self.command, "path": self.path}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        _ = self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler dispatch name
        self._emit()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler dispatch name
        self._emit()

    def log_message(self, *_: object) -> None:
        return


@pytest.fixture
def stub_server() -> Any:
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host!s}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_get_and_post_round_trip_json(stub_server: str) -> None:
    assert http_get(f"{stub_server}/app/installations", "jwt") == {
        "method": "GET",
        "path": "/app/installations",
    }
    assert http_post(f"{stub_server}/x/access_tokens", "jwt") == {
        "method": "POST",
        "path": "/x/access_tokens",
    }


def test_request_json_wraps_transport_errors() -> None:
    # Port 1 is not listening → urllib raises URLError → AppTokenMintError.
    with pytest.raises(AppTokenMintError, match="GitHub App API call"):
        http_get("http://127.0.0.1:1/app/installations", "jwt")


# --------------------------------------------------------------------------
# Installation resolution
# --------------------------------------------------------------------------
def _unused_http(_url: str, _jwt: str) -> Any:
    raise AssertionError("http seam must not be called")  # pragma: no cover


def test_resolve_uses_a_pinned_installation_id() -> None:
    out = resolve_installation_id(
        api_url="https://x", jwt="j", installation_id="99", http_get=_unused_http
    )
    assert out == "99"


def test_resolve_finds_the_sole_installation() -> None:
    out = resolve_installation_id(
        api_url="https://x", jwt="j", installation_id=None, http_get=lambda _u, _j: [{"id": 7}]
    )
    assert out == "7"


def test_resolve_rejects_multiple_installations() -> None:
    with pytest.raises(AppTokenMintError, match="2 installations"):
        resolve_installation_id(
            api_url="https://x",
            jwt="j",
            installation_id=None,
            http_get=lambda _u, _j: [{"id": 1}, {"id": 2}],
        )


def test_resolve_rejects_a_non_list_response() -> None:
    with pytest.raises(AppTokenMintError, match="did not return a list"):
        resolve_installation_id(
            api_url="https://x",
            jwt="j",
            installation_id=None,
            http_get=lambda _u, _j: {"message": "bad creds"},
        )


# --------------------------------------------------------------------------
# Mint orchestration (injected fakes)
# --------------------------------------------------------------------------
def _fake_sign(_signing_input: str, _pem: str) -> bytes:
    return b"signature-bytes"


def test_mint_happy_path_discovers_and_exchanges() -> None:
    token = mint_installation_token(
        app_id="42",
        private_key_pem="pem",
        issued_at=1_000_000,
        seams=_seams(
            sign=_fake_sign,
            http_get=lambda _u, _j: [{"id": 123}],
            http_post=lambda _u, _j: {"token": "ghs_minted"},
        ),
    )
    assert token == "ghs_minted"


def test_mint_passes_pinned_installation_into_the_token_url() -> None:
    seen: dict[str, str] = {}

    def capture_post(url: str, _jwt: str) -> Any:
        seen["url"] = url
        return {"token": "ghs_pinned"}

    token = mint_installation_token(
        app_id="42",
        private_key_pem="pem",
        installation_id="555",
        issued_at=1,
        seams=_seams(sign=_fake_sign, http_get=_unused_http, http_post=capture_post),
    )
    assert token == "ghs_pinned"
    assert seen["url"].endswith("/app/installations/555/access_tokens")


def test_mint_rejects_empty_app_id() -> None:
    with pytest.raises(AppTokenMintError, match="GITHUB_APP_ID is empty"):
        mint_installation_token(app_id="", private_key_pem="pem")


def test_mint_rejects_empty_private_key() -> None:
    with pytest.raises(AppTokenMintError, match="GITHUB_PRIVATE_KEY is empty"):
        mint_installation_token(app_id="42", private_key_pem="")


def test_mint_rejects_a_missing_token_field() -> None:
    with pytest.raises(AppTokenMintError, match="no access token"):
        mint_installation_token(
            app_id="42",
            private_key_pem="pem",
            issued_at=1,
            seams=_seams(
                sign=_fake_sign,
                http_get=lambda _u, _j: [{"id": 1}],
                http_post=lambda _u, _j: {},
            ),
        )


def test_mint_rejects_a_non_dict_token_response() -> None:
    with pytest.raises(AppTokenMintError, match="no access token"):
        mint_installation_token(
            app_id="42",
            private_key_pem="pem",
            issued_at=1,
            seams=_seams(
                sign=_fake_sign,
                http_get=lambda _u, _j: [{"id": 1}],
                http_post=lambda _u, _j: ["not", "a", "dict"],
            ),
        )


# --------------------------------------------------------------------------
# Credential resolution (App-preferred, PAT fallback)
# --------------------------------------------------------------------------
def test_resolve_prefers_the_app_token() -> None:
    app_token = "ghs_app"
    resolved = resolve_github_token(
        app_id="42",
        private_key_pem="pem",
        pat="pat-value",
        seams=_seams(
            sign=_fake_sign,
            http_get=lambda _u, _j: [{"id": 1}],
            http_post=lambda _u, _j: {"token": app_token},
        ),
    )
    assert resolved == ResolvedToken(token=app_token, source="github-app-installation-token")


def test_resolve_falls_back_to_the_pat_when_no_app() -> None:
    pat_token = "pat-value"
    resolved = resolve_github_token(app_id="", private_key_pem="", pat=pat_token)
    assert resolved == ResolvedToken(token=pat_token, source="livespec-family-pat")


def test_resolve_requires_some_credential() -> None:
    with pytest.raises(AppTokenMintError, match="no GitHub credential"):
        resolve_github_token(app_id="", private_key_pem="", pat="")


# --------------------------------------------------------------------------
# CLI entry point
# --------------------------------------------------------------------------
def test_main_prints_only_the_token_and_logs_source(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", " 42 ")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "pem")
    monkeypatch.delenv("GITHUB_APP_INSTALLATION_ID", raising=False)
    main_token = "ghs_from_main"

    def fake_resolve(**_: object) -> ResolvedToken:
        return ResolvedToken(token=main_token, source="github-app-installation-token")

    monkeypatch.setattr(cli, "resolve_github_token", fake_resolve)
    assert cli.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == main_token
    assert "github-token source: github-app-installation-token" in captured.err


def test_main_maps_resolution_error_to_exit_3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "")

    def fake_resolve(**_: object) -> ResolvedToken:
        raise AppTokenMintError(detail="no GitHub credential")

    monkeypatch.setattr(cli, "resolve_github_token", fake_resolve)
    assert cli.main() == 3
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert captured.out == ""
