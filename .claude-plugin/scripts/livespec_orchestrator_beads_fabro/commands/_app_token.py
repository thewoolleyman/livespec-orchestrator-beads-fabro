"""GitHub App installation-token mint logic (the tested core of `mint-app-token`).

ALL token-mint logic lives here as Python (NOT shell): RS256 JWT signing,
installation discovery, the token exchange, and the railway of expected failures
(`AppTokenMintError`) vs caller bugs. `commands/mint_app_token.py` is the thin
CLI over `mint_installation_token`; `orchestrator-entrypoint.sh` is thin glue
that runs that CLI and exports the printed token as `GH_TOKEN`.

WHY an App token: it carries the App's permissions (the livespec-pr-bot App:
Pull requests + Contents = write) on every repo the App is installed on — unlike
the family PAT, which lacks `Pull requests: write` on some repos and so cannot
self-publish. ADOPTERS point `GITHUB_APP_ID` + `GITHUB_PRIVATE_KEY` at their own
App; nothing livespec-specific is baked in.

The signer and the two HTTP calls are bundled in an injectable `MintSeams` so the
orchestration is unit-tested with fakes; the production seams default to openssl
(RS256) and urllib (the GitHub REST API).
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.errors import AppTokenMintError

__all__: list[str] = [
    "DEFAULT_API",
    "MintSeams",
    "ResolvedToken",
    "b64url",
    "http_get",
    "http_post",
    "jwt_signing_input",
    "mint_installation_token",
    "normalize_pem",
    "openssl_sign_rs256",
    "resolve_github_token",
    "resolve_installation_id",
]

DEFAULT_API = "https://api.github.com"
_API_VERSION = "2022-11-28"
# iat is backdated for clock skew; the JWT lives well under GitHub's 10-min cap.
_JWT_SKEW_SECONDS = 60
_JWT_TTL_SECONDS = 540
_HTTP_TIMEOUT_SECONDS = 30.0

SignRs256 = Callable[[str, str], bytes]
HttpJson = Callable[[str, str], Any]


def b64url(raw: bytes) -> str:
    """URL-safe base64 without padding (the JWS/JWT encoding)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def normalize_pem(raw: str) -> str:
    """Return a valid PEM with real line structure.

    A secrets manager may deliver the key flattened to one line (newlines
    stripped or turned into spaces / literal backslash-n); openssl needs real
    PEM line structure, so de-whitespace the base64 body and re-wrap at 64
    columns. A key that already carries real newlines passes through unchanged.
    """
    text = raw.replace("\\n", "\n").strip()
    if "\n" in text:
        return text + "\n"
    match = re.match(r"(-----BEGIN [A-Z0-9 ]+-----)(.*)(-----END [A-Z0-9 ]+-----)", text)
    if match is None:
        return text
    begin, body, end = match.group(1), match.group(2), match.group(3)
    compact = "".join(body.split())
    wrapped = "\n".join(compact[i : i + 64] for i in range(0, len(compact), 64))
    return f"{begin}\n{wrapped}\n{end}\n"


def jwt_signing_input(*, app_id: str, issued_at: int) -> str:
    """The unsigned `header.payload` of the App JWT (pure; caller injects time)."""
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode("utf-8"))
    payload = b64url(
        json.dumps(
            {
                "iat": issued_at - _JWT_SKEW_SECONDS,
                "exp": issued_at + _JWT_TTL_SECONDS,
                "iss": app_id,
            }
        ).encode("utf-8")
    )
    return f"{header}.{payload}"


def openssl_sign_rs256(signing_input: str, pem: str) -> bytes:
    """Production signer: RS256 over `signing_input` with the App private key.

    openssl reads the key from a file, so the normalized PEM is written to a
    mode-600 temp file (the scoped transient-materialization pattern the
    Dispatcher's run-config overlay also uses) and removed immediately. A key
    openssl cannot load is an EXPECTED misconfiguration → `AppTokenMintError`.
    """
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)  # noqa: SIM115
    key_path = Path(handle.name)
    try:
        key_path.chmod(0o600)
        _ = handle.write(pem)
        handle.close()
        completed = subprocess.run(  # noqa: S603
            ["openssl", "dgst", "-sha256", "-sign", str(key_path)],  # noqa: S607
            input=signing_input.encode("utf-8"),
            capture_output=True,
            check=False,
        )
    finally:
        key_path.unlink()
    if completed.returncode != 0:
        raise AppTokenMintError(
            detail=f"openssl could not sign with the private key (exit {completed.returncode})"
        )
    return completed.stdout


def _request_json(*, url: str, jwt: str, method: str) -> Any:
    """JWT-authenticated GitHub REST call → parsed JSON.

    An App-API rejection (e.g. a 401 from a bad App id / clock-skewed JWT) or a
    transport error is an EXPECTED failure → `AppTokenMintError`.
    """
    request = urllib.request.Request(  # noqa: S310 - https GitHub API, fixed scheme
        url,
        data=b"{}" if method == "POST" else None,
        method=method,
        headers={
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "livespec-orchestrator-mint-app-token",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AppTokenMintError(detail=f"GitHub App API call to {url} failed: {exc}") from exc


def http_get(url: str, jwt: str) -> Any:
    """Production HTTP GET seam (JWT-authenticated)."""
    return _request_json(url=url, jwt=jwt, method="GET")


def http_post(url: str, jwt: str) -> Any:
    """Production HTTP POST seam (JWT-authenticated)."""
    return _request_json(url=url, jwt=jwt, method="POST")


@dataclass(frozen=True, kw_only=True, slots=True)
class MintSeams:
    """The injectable side-effecting seams of the mint (defaulted to production)."""

    sign: SignRs256
    http_get: HttpJson
    http_post: HttpJson


_DEFAULT_SEAMS = MintSeams(sign=openssl_sign_rs256, http_get=http_get, http_post=http_post)


def resolve_installation_id(
    *, api_url: str, jwt: str, installation_id: str | None, http_get: HttpJson
) -> str:
    """Return the installation id: the pinned one, else the App's sole install."""
    if installation_id is not None and installation_id != "":
        return installation_id
    payload = http_get(f"{api_url}/app/installations", jwt)
    if not isinstance(payload, list):
        raise AppTokenMintError(
            detail=(
                "the App /installations API did not return a list; "
                "set GITHUB_APP_INSTALLATION_ID"
            )
        )
    installations = cast("list[object]", payload)
    if len(installations) != 1:
        raise AppTokenMintError(
            detail=(
                f"the App has {len(installations)} installations; set "
                "GITHUB_APP_INSTALLATION_ID to pin the one to mint for"
            )
        )
    return str(cast("dict[str, Any]", installations[0])["id"])


def mint_installation_token(
    *,
    app_id: str,
    private_key_pem: str,
    api_url: str = DEFAULT_API,
    installation_id: str | None = None,
    issued_at: int | None = None,
    seams: MintSeams = _DEFAULT_SEAMS,
) -> str:
    """Mint and return a GitHub App installation token (the railway entry point).

    Composes the pure JWT assembly with the injected signer + HTTP seams. Raises
    `AppTokenMintError` for every EXPECTED failure (bad credentials, ambiguous
    installations, an empty token); caller bugs propagate as built-ins.
    """
    if app_id == "":
        raise AppTokenMintError(detail="GITHUB_APP_ID is empty")
    if private_key_pem == "":
        raise AppTokenMintError(detail="GITHUB_PRIVATE_KEY is empty")
    stamp = issued_at if issued_at is not None else int(time.time())
    signing_input = jwt_signing_input(app_id=app_id, issued_at=stamp)
    signature = seams.sign(signing_input, normalize_pem(private_key_pem))
    jwt = f"{signing_input}.{b64url(signature)}"
    resolved = resolve_installation_id(
        api_url=api_url, jwt=jwt, installation_id=installation_id, http_get=seams.http_get
    )
    minted = seams.http_post(f"{api_url}/app/installations/{resolved}/access_tokens", jwt)
    token = cast("dict[str, Any]", minted).get("token") if isinstance(minted, dict) else None
    if not isinstance(token, str) or token == "":
        raise AppTokenMintError(detail=f"installation {resolved} returned no access token")
    return token


@dataclass(frozen=True, kw_only=True, slots=True)
class ResolvedToken:
    """The factory's resolved GitHub credential plus its (non-secret) source."""

    token: str
    source: str


def resolve_github_token(
    *,
    app_id: str,
    private_key_pem: str,
    pat: str,
    api_url: str = DEFAULT_API,
    installation_id: str | None = None,
    seams: MintSeams = _DEFAULT_SEAMS,
) -> ResolvedToken:
    """Choose the factory's GitHub credential — App installation token preferred.

    The App is the PR-capable credential, so when App credentials are configured
    it is used and a mint failure is fatal (NOT silently downgraded to the
    PR-incapable PAT — that would re-break self-publish). The PAT is the fallback
    ONLY for adopters who have not configured an App. This App-vs-PAT decision
    lives here (tested Python), so the shell entrypoint stays branch-free glue.
    """
    if app_id != "" and private_key_pem != "":
        token = mint_installation_token(
            app_id=app_id,
            private_key_pem=private_key_pem,
            api_url=api_url,
            installation_id=installation_id,
            seams=seams,
        )
        return ResolvedToken(token=token, source="github-app-installation-token")
    if pat != "":
        return ResolvedToken(token=pat, source="livespec-family-pat")
    raise AppTokenMintError(
        detail=(
            "no GitHub credential: set GITHUB_APP_ID + GITHUB_PRIVATE_KEY (recommended) "
            "or LIVESPEC_FAMILY_GITHUB_TOKEN"
        )
    )
