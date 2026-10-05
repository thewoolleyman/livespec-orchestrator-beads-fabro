"""Bounded, host-only EARLY renewal of the Codex credential.

Why this is not the `codex exec` the guarded refresher used to spend. Upstream
gates the ORDINARY refresh on a five-minute window: `AuthManager::auth`
refreshes only when `should_refresh_proactively` holds, and that predicate is
true only when the access token expires within
`CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES` (5)
(`codex-rs/login/src/auth/manager.rs`). A `codex exec` spent with hours of
lifetime left therefore cannot advance the expiry at all — which is why the
refresh guard was originally sized at six minutes to match that window, and
why widening the guard ALONE leaves the dead zone intact: the refresher would
become eligible across the whole interval and still decline, inside Codex's
own code, where no configuration of ours reaches.

The app-server `account/read` request is NOT window-gated. Its `refreshToken`
flag reaches `refresh_token_if_requested`, which calls
`AuthManager::refresh_token` with no expiry predicate at all
(`codex-rs/app-server/src/request_processors/account_processor.rs`); it returns
early only for external-ChatGPT, API-key and personal-access-token auth, none
of which is the managed-auth posture the orchestrator host holds. The parameter
documents itself: "When `true`, requests a proactive token refresh before
returning. In managed auth mode this triggers the normal refresh-token flow."

Host ownership is unchanged (the worker-credential-projection contract in
`SPECIFICATION/contracts.md`).
This runs on the CREDENTIAL-SOURCE host against that host's own `$CODEX_HOME`,
and it copies, writes and parses NO token: the request asks Codex to rotate its
own credential in place, and every caller grades the outcome by RE-READING
`auth.json` rather than by trusting the response. A request that could not even
be spent is therefore not a verdict about authentication — it is an absent
observation, and the re-read is what decides.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "CODEX_EARLY_RENEWAL_TIMEOUT_SECONDS",
    "UNSPENDABLE_EXIT_CODE",
    "CodexAppServerRunner",
    "CodexRenewalOutcome",
    "ReceivedLineKind",
    "classify_received_line",
    "classify_renewal_result",
    "codex_app_server_argv",
    "codex_early_renewal_request_lines",
    "request_early_codex_renewal",
    "request_id_of",
]

# The renewal rides inside a dispatch, so it must be bounded well under any
# node budget: a hung app-server would hold the dispatch open rather than
# refuse it.
CODEX_EARLY_RENEWAL_TIMEOUT_SECONDS = 120.0

# The exit code reported when the app-server could not be spawned at all. It is
# distinct from any code Codex itself returns, so a caller reading the journal
# can tell "the request was never spent" from "Codex answered non-zero".
UNSPENDABLE_EXIT_CODE = 127

_CLIENT_NAME = "livespec-orchestrator"
_CLIENT_TITLE = "livespec orchestrator credential renewal"
_CLIENT_VERSION = "1"
_INITIALIZE_ID = 1
_ACCOUNT_READ_ID = 2


class CodexAppServerRunner(Protocol):
    """Runs ONE `codex app-server` session over a JSONL request conversation.

    The contract is a bounded REQUEST/RESPONSE handshake, not a batch write.
    An implementation MUST keep stdin open and await the response matching each
    request's own id before sending the next line, then close stdin and reap.

    This is measured, not defensive. On host codex 0.160.0, against a fresh
    empty `CODEX_HOME` with `refreshToken` false (so no live credential was
    touched), writing all three lines at once and closing stdin immediately
    exited 0 having emitted only the `initialize` response for id 1 plus a
    status notification — and NO response for the `account/read` id 2. EOF
    cancels the asynchronous request. The control that keeps stdin open,
    awaits id 1, then sends `initialized` and `account/read` and awaits id 2,
    receives id 2 normally.

    So the batch shape fails in the worst available direction: the renewal is
    silently never processed while the process exits 0, which every caller
    would read as a spent request. Only the post-renewal RE-READ of
    `auth.json` would have caught it, and it would have looked like a
    credential that refused to advance.
    """

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        request_lines: list[str],
        timeout_seconds: float,
    ) -> CommandResult:
        """Drive the conversation to its last answer, then terminate and reap."""
        ...


def codex_app_server_argv() -> list[str]:
    """Return the argv for one Codex app-server session."""
    return ["codex", "app-server"]


def codex_early_renewal_request_lines() -> list[str]:
    """Render the newline-delimited JSON-RPC conversation that renews early.

    The handshake is required before the request: a client that sent
    `account/read` alone would be answered without having declared itself.
    `initialized` is a NOTIFICATION — upstream serializes it with neither an
    `id` nor a `params` field — so it is rendered without either here.
    """
    messages: list[dict[str, Any]] = [
        {
            "jsonrpc": "2.0",
            "id": _INITIALIZE_ID,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": _CLIENT_NAME,
                    "title": _CLIENT_TITLE,
                    "version": _CLIENT_VERSION,
                }
            },
        },
        {"jsonrpc": "2.0", "method": "initialized"},
        {
            "jsonrpc": "2.0",
            "id": _ACCOUNT_READ_ID,
            "method": "account/read",
            "params": {"refreshToken": True},
        },
    ]
    return [json.dumps(message) for message in messages]


def request_early_codex_renewal(
    *,
    cwd: Path,
    runner: CodexAppServerRunner,
) -> CommandResult:
    """Spend ONE bounded app-server request asking Codex to renew early."""
    return runner.run(
        argv=codex_app_server_argv(),
        cwd=cwd,
        request_lines=codex_early_renewal_request_lines(),
        timeout_seconds=CODEX_EARLY_RENEWAL_TIMEOUT_SECONDS,
    )


@dataclass(frozen=True, kw_only=True)
class CodexRenewalOutcome:
    """What one bounded early-renewal request achieved, for diagnostics.

    `answered` is the ONLY distinction that matters downstream, and it is NOT
    a verdict about the credential: it separates "Codex processed the renewal
    and the expiry still did not advance" from "the request never reached
    Codex at all". Collapsing the two is what turns a missing executable into
    a false claim that authentication failed.
    """

    answered: bool
    detail: str


def classify_renewal_result(*, result: CommandResult) -> CodexRenewalOutcome:
    """Summarize one renewal attempt without quoting anything the server said."""
    if result.exit_code == 0:
        return CodexRenewalOutcome(
            answered=True,
            detail="the renewal request was answered by the host Codex app-server",
        )
    if result.exit_code == UNSPENDABLE_EXIT_CODE:
        return CodexRenewalOutcome(
            answered=False,
            detail=result.stderr.strip() or "the renewal request could not be spent",
        )
    return CodexRenewalOutcome(
        answered=False,
        detail=f"the host Codex app-server exited {result.exit_code}",
    )


ReceivedLineKind = Literal["pending", "answered", "errored"]


def request_id_of(*, line: str) -> int | None:
    """Return the JSON-RPC id a rendered request line awaits an answer for.

    `None` means the line is a NOTIFICATION, which is answered by nothing — a
    transport that waited for a response to it would block until its deadline.
    """
    message: dict[str, Any] = json.loads(line)
    raw = message.get("id")
    return raw if isinstance(raw, int) else None


def classify_received_line(*, line: str, expected_id: int) -> ReceivedLineKind:
    """Classify one line the app-server emitted against the id being awaited.

    `pending` covers every line that is NOT the answer: a server notification,
    a response belonging to another id, and an unparseable or non-object line.
    The distinction is load-bearing rather than defensive — the server
    interleaves notifications with responses, so a reader that treated the
    first line it saw as the answer would accept a status broadcast as a
    completed renewal and report success having requested nothing.
    """
    parsed = attempt(action=lambda: json.loads(line), exceptions=(ValueError,))
    if isinstance(parsed, AttemptFailure) or not isinstance(parsed, dict):
        return "pending"
    message = cast("dict[str, Any]", parsed)
    if message.get("id") != expected_id:
        return "pending"
    return "errored" if "error" in message else "answered"
