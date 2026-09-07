"""`mint-app-token` — thin CLI over the vendored fleet GitHub App-token primitive.

Resolution is FAIL-CLOSED per the github-app-auth design record (Pillar 2 —
tenant-scoped resolution): the credential env (GITHUB_APP_ID +
GITHUB_PRIVATE_KEY, optional GITHUB_APP_INSTALLATION_ID / GITHUB_API_URL) is
injected ONLY by the calling tenant's credential_wrapper, and there is NO
retired fleet-PAT fallback.
All signing / mint / caching logic lives in the vendored
`livespec_runtime.github_auth`; this CLI only wires env → config → provider
→ stdout, so `orchestrator-entrypoint.sh` stays branch-free glue running
`GH_TOKEN="$(mint_app_token.py)"`-shaped captures.

SECRET HYGIENE: only the token is written to stdout (for capture);
diagnostics go to stderr; env carries the inputs so no secret ever lands in
argv.

SAFE INTROSPECTION: this command emits a LIVE credential on success, so it
must be possible to ask it what it does without being handed one. Two guards
enforce that, both added after a real incident on 2026-08-02 in which an
operator ran it with `--help` and received a live installation token
(revoked immediately; the value still reached a terminal scrollback and a
session transcript):

1. argv is PARSED. Previously `main` discarded it (`_ = argv`) and the
   wrapper called `main()` with no argv at all, so `--help` could not reach
   a parser because there was neither a parser nor plumbing. Any argument —
   recognised or not — now resolves before a token is minted.
2. Minting is REFUSED when stdout is a terminal. The documented contract is
   `GH_TOKEN="$(mint-app-token)"`, where stdout is a pipe; a terminal means
   the caller is looking at the output, and a credential written there lands
   in scrollback and transcripts. There is deliberately NO override flag —
   one would reinstate exactly the footgun this closes.

`--help` is handled BEFORE the terminal guard, so asking for help at a
terminal prints help rather than a refusal. That ordering is the whole point.
"""

from __future__ import annotations

import argparse
import os
import sys

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.provider import InstallationTokenProvider
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = ["main"]

_EXIT_USAGE = 2
_EXIT_MINT_FAILED = 3


def _stdout_isatty() -> bool:
    """Whether stdout is a terminal (seam so tests can force either branch)."""
    return sys.stdout.isatty()


def main(*, argv: list[str] | None = None) -> int:
    """Mint a GitHub App installation token from env; print it to stdout.

    Takes no options. `--help` prints usage and exits 0 WITHOUT minting; any
    other argument is a usage error on stderr with exit 2, per this package's
    CLI output contract. Minting is refused with exit 2 when stdout is a
    terminal — see the module docstring for why there is no override.

    Every EXPECTED failure — missing/empty App env (including the no-fallback
    refusal when only the retired fleet PAT is present), a bad key, an App API
    rejection — surfaces the actionable `GithubAppAuthError` detail on stderr
    and exits 3. The (non-secret) source is logged to stderr; only the token is
    written to stdout for `GH_TOKEN="$(...)"` capture.
    """
    parser = argparse.ArgumentParser(
        prog="mint-app-token",
        description=(
            "Mint a GitHub App installation token from the credential env and "
            "write ONLY that token to stdout."
        ),
        epilog=(
            "Takes no options. Capture the token with "
            'GH_TOKEN="$(mint-app-token)". Minting is refused when stdout is a '
            "terminal, so asking this command what it does can never answer "
            "with a live credential."
        ),
    )
    # `--help` exits 0 from here, before the guard below: help at a terminal
    # must print help, not a refusal.
    _ = parser.parse_args(argv)

    if _stdout_isatty():
        _ = write_stderr(
            text=(
                "ERROR: refusing to mint — stdout is a terminal.\n"
                "This command writes a LIVE GitHub App installation token to "
                "stdout; at a terminal that puts a credential into scrollback "
                "and any session transcript.\n"
                'Capture it instead: GH_TOKEN="$(mint-app-token)"\n'
            )
        )
        return _EXIT_USAGE

    # `load_github_app_config` is on the Result railway since livespec-runtime
    # v0.21.2; the mint itself still raises, so the two failure shapes are
    # discharged separately onto the SAME operator-facing refusal.
    config = load_github_app_config(environ=os.environ)
    if not is_successful(config):
        _ = write_stderr(text=f"ERROR: {config.failure().detail}\n")
        return _EXIT_MINT_FAILED
    try:
        token = InstallationTokenProvider(config=config.unwrap()).token()
    except GithubAppAuthError as exc:
        _ = write_stderr(text=f"ERROR: {exc.detail}\n")
        return _EXIT_MINT_FAILED
    _ = write_stderr(text="github-token source: github-app-installation-token\n")
    _ = write_stdout(text=token)
    return 0
