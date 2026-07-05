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
"""

from __future__ import annotations

import os
import sys

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.provider import InstallationTokenProvider

__all__: list[str] = ["main"]

_EXIT_MINT_FAILED = 3


def main(argv: list[str] | None = None) -> int:
    """Mint a GitHub App installation token from env; print it to stdout.

    `argv` is accepted for parity with the other command mains (no flags
    today). Every EXPECTED failure — missing/empty App env (including the
    no-fallback refusal when only the retired fleet PAT is present), a bad
    key, an App API rejection — surfaces the actionable
    `GithubAppAuthError` detail on stderr and exits 3. The (non-secret)
    source is logged to stderr; only the token is written to stdout for
    `GH_TOKEN="$(...)"` capture.
    """
    _ = argv
    try:
        config = load_github_app_config(environ=os.environ)
        token = InstallationTokenProvider(config=config).token()
    except GithubAppAuthError as exc:
        _ = sys.stderr.write(f"ERROR: {exc.detail}\n")
        return _EXIT_MINT_FAILED
    _ = sys.stderr.write("github-token source: github-app-installation-token\n")
    _ = sys.stdout.write(token)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
