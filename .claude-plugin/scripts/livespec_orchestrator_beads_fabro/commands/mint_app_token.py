"""`mint-app-token` — thin CLI over the GitHub App installation-token mint.

The mint logic (RS256 JWT signing, installation discovery, token exchange, error
railway) lives in `commands/_app_token.py`. `orchestrator-entrypoint.sh` is thin
glue that runs `GH_TOKEN="$(mint-app-token.py)"`.

SECRET HYGIENE: only the token is written to stdout (for capture); diagnostics go
to stderr; env carries the inputs so no secret ever lands in argv.
"""

from __future__ import annotations

import os
import sys

from livespec_orchestrator_beads_fabro.commands._app_token import (
    DEFAULT_API,
    resolve_github_token,
)
from livespec_orchestrator_beads_fabro.errors import AppTokenMintError

__all__: list[str] = ["main"]

_EXIT_MINT_FAILED = 3


def main(argv: list[str] | None = None) -> int:
    """Resolve the factory GitHub credential from env, print the token to stdout.

    Prefers a GitHub App installation token (minted from GITHUB_APP_ID +
    GITHUB_PRIVATE_KEY), falling back to the LIVESPEC_FAMILY_GITHUB_TOKEN PAT only
    when no App is configured. `argv` is accepted for parity with the other
    command mains (no flags today). The (non-secret) source is logged to stderr;
    only the token is written to stdout for `GH_TOKEN="$(...)"` capture.
    """
    _ = argv
    try:
        resolved = resolve_github_token(
            app_id=os.environ.get("GITHUB_APP_ID", "").strip(),
            private_key_pem=os.environ.get("GITHUB_PRIVATE_KEY", ""),
            pat=os.environ.get("LIVESPEC_FAMILY_GITHUB_TOKEN", ""),
            api_url=os.environ.get("GITHUB_API_URL", DEFAULT_API),
            installation_id=os.environ.get("GITHUB_APP_INSTALLATION_ID"),
        )
    except AppTokenMintError as exc:
        _ = sys.stderr.write(f"ERROR: {exc}\n")
        return _EXIT_MINT_FAILED
    _ = sys.stderr.write(f"github-token source: {resolved.source}\n")
    _ = sys.stdout.write(resolved.token)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
