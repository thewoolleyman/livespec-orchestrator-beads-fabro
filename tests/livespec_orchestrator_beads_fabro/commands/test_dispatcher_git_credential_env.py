"""Every sandbox git process authenticates a github.com fetch GitHub refuses anonymously.

Measured 2026-11-12 from about 13:20Z: GitHub intermittently answered 401 to
ANONYMOUS git fetches from the homelab NAT egress, and every orchestrator
dispatch then died at run_prepare_3 -- `uv sync` fetching the repository's
git-sourced dependencies -- with "could not read Username for
'https://github.com': terminal prompts disabled".

bd-ib-52zt3o already gives the sandbox a github.com credential helper, but as
clone-LOCAL config written by a Dispatcher setup node that runs AFTER the
committed run_prepare chain. uv fetches git dependencies from its own cache
directory, where no clone-local config applies, so the helper could never have
answered that fetch even had it existed yet. The cure is PROCESS-level config in
the run-scoped env table, which every git process in the sandbox inherits.

WHY `GIT_CONFIG_PARAMETERS` AND NOT `GIT_CONFIG_COUNT`. A Petri-era runner may
hand the sandbox its own `GIT_CONFIG_COUNT` set -- the sibling helper test
records one carrying an EMPTY github.com helper, which resets the accumulated
helper list. Writing `GIT_CONFIG_COUNT` pairs from the env table would clobber that set or
be clobbered by it; git reads `GIT_CONFIG_PARAMETERS` AFTER the COUNT set, so a
helper there survives the reset and leaves the runner's set alone. The
behavioural cases below therefore run under exactly that reset.

WHY `git credential fill` OUTSIDE ANY REPOSITORY. It is the credential
resolution a fetch performs after a 401, and running it from a directory that is
not a repository is what uv's cache-directory fetch looks like: no clone-local
config can contribute an answer, so a pass here is the process-level helper's.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_ENV_TABLE_HEADER = "[environments.livespec-ci.env]"
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
# The one value a dispatch ships, asserted verbatim: the subsection between the
# first and the last dot of the key is the URL git scopes the helper to, and the
# command is the same one bd-ib-52zt3o's clone-local helper runs.
_EXPECTED_PARAMETERS = "'credential.https://github.com.helper=!gh auth git-credential'"


def test_every_dispatch_projects_the_process_level_github_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both App-input arms, because "every dispatch" is the assertion."""
    for app_inputs_present in (True, False):
        for key in ("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY"):
            if app_inputs_present:
                monkeypatch.setenv(key, "42")
            else:
                monkeypatch.delenv(key, raising=False)
        rendered = _render(tmp_path=tmp_path)
        assert _env_table_values(rendered=rendered, name="GIT_CONFIG_PARAMETERS") == [
            _EXPECTED_PARAMETERS
        ]


def test_the_helper_configuration_carries_no_token_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The token rides only its own GITHUB_TOKEN line; the helper names a command."""
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    rendered = _render(tmp_path=tmp_path)
    values = _env_table_values(rendered=rendered, name="GIT_CONFIG_PARAMETERS")
    assert len(values) == 1
    parameters = values[0]
    assert _GITHUB_TOKEN not in parameters
    assert _OAUTH_TOKEN not in parameters
    assert "stub-pem" not in parameters
    assert "$" not in parameters
    assert rendered.count(_GITHUB_TOKEN) == 1
    assert _env_table_values(rendered=rendered, name="GITHUB_TOKEN") == [_GITHUB_TOKEN]


def test_a_refused_github_fetch_outside_any_clone_is_answered_with_the_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uv's cache-directory fetch, under a runner COUNT set that resets the helpers."""
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    sandbox = _sandbox(tmp_path=tmp_path, rendered=_render(tmp_path=tmp_path))

    completed = _credential_fill(sandbox=sandbox, url="https://github.com/owner/dependency.git")

    assert completed.returncode == 0, completed.stderr
    assert "username=x-access-token" in completed.stdout
    assert f"password={_GITHUB_TOKEN}" in completed.stdout
    assert _gh_calls(sandbox=sandbox) == ["auth git-credential get"]


def test_the_helper_answers_no_other_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scoped to https://github.com: another host never reaches gh at all."""
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    sandbox = _sandbox(tmp_path=tmp_path, rendered=_render(tmp_path=tmp_path))

    completed = _credential_fill(sandbox=sandbox, url="https://gitlab.com/owner/dependency.git")

    assert completed.returncode != 0
    assert _GITHUB_TOKEN not in completed.stdout
    assert _gh_calls(sandbox=sandbox) == []


def _render(*, tmp_path: Path) -> str:
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    return rendered


def _env_table_values(*, rendered: str, name: str) -> list[str]:
    """Every value one key carries in the run-scoped env table, decoded, in order.

    Bounded at the table's own header and the next table header, so a key of
    the same name anywhere else in the overlay cannot answer for it. A LIST, so
    "absent" and "rendered twice" are both visible to an equality assertion
    rather than collapsing into one sentinel, and so that no line here is
    reachable only while the key is missing: this module's Red runs against a
    tree without the key and its Green against one with it, and the coverage
    gate counts test lines too.
    """
    start = rendered.index(_ENV_TABLE_HEADER) + len(_ENV_TABLE_HEADER)
    table = re.split(r"^\[", rendered[start:], maxsplit=1, flags=re.MULTILINE)[0]
    found = re.findall(rf"^{re.escape(name)} = (\".*\")$", table, re.MULTILINE)
    return [str(json.loads(value)) for value in found]


def _sandbox(*, tmp_path: Path, rendered: str) -> dict[str, str]:
    """The env a sandbox git process inherits: the rendered helper plus a runner reset.

    The stand-in `gh` answers `auth git-credential` from GITHUB_TOKEN exactly as
    gh 2.96.0 does with an empty config directory (measured 2026-11-12), and
    logs each call so a case can assert gh was or was not reached.
    """
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    gh_log = tmp_path / "gh-calls.txt"
    gh_log.write_text("", encoding="utf-8")
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        'printf "%s\\n" "$*" >> "$GH_LOG"\n'
        "cat > /dev/null\n"
        'if [ "$1 $2 $3" = "auth git-credential get" ] && [ -n "${GITHUB_TOKEN:-}" ]; then\n'
        "  printf 'username=x-access-token\\npassword=%s\\n' \"$GITHUB_TOKEN\"\n"
        "fi\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    parameters = _env_table_values(rendered=rendered, name="GIT_CONFIG_PARAMETERS")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV") and not key.startswith("GIT_") and key != "GH_TOKEN"
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GH_LOG": str(gh_log),
            "GITHUB_TOKEN": _GITHUB_TOKEN,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            # The runner-style process set: an EMPTY github.com helper, which
            # resets every helper configured before it.
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "credential.https://github.com.helper",
            "GIT_CONFIG_VALUE_0": "",
            # Whatever the overlay rendered, verbatim; empty when it rendered
            # nothing, which git reads as no command-line configuration.
            "GIT_CONFIG_PARAMETERS": "".join(parameters),
        }
    )
    return env


def _credential_fill(*, sandbox: dict[str, str], url: str) -> subprocess.CompletedProcess[str]:
    """git's own credential resolution, from a directory that is no repository."""
    outside = Path(sandbox["GH_LOG"]).parent / "uv-cache"
    outside.mkdir(exist_ok=True)
    return subprocess.run(
        ["git", "credential", "fill"],
        cwd=outside,
        env={**sandbox, "GIT_CEILING_DIRECTORIES": str(outside.parent)},
        input=f"url={url}\n\n",
        capture_output=True,
        text=True,
        check=False,
    )


def _gh_calls(*, sandbox: dict[str, str]) -> list[str]:
    return Path(sandbox["GH_LOG"]).read_text(encoding="utf-8").splitlines()
