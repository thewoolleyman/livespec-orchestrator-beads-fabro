"""The sandbox git credential helper every dispatch configures (bd-ib-52zt3o).

On the pinned 0.254 engine an in-sandbox `git push` authenticated through the
token Fabro wrote into the origin URL and re-minted at each ACP node entry. The
Petri-era standalone runner does neither — it logs that `run.integrations` is
ignored because "platform integrations are supplied by an embedding host" and
that it "performs no Git operations of its own" — so every in-sandbox push
(`needs_human` preserve, `publish_draft`, `pr`) arrives with no credential.
Measured on hp-candidate run 01M4NWARSD8T70G09PRQ70ZR5B: 30 prepare steps and a
real `dod_gate` turn succeeded, then `needs_human` printed
LIVESPEC_NEEDS_HUMAN_PUSH_FAILED.

WHY `git credential fill` IS THE INSTRUMENT HERE, and not `git push`. A real
https push needs an https server, which no hermetic test stands one up for — so
a push-shaped test would prove the fixture, not the behaviour. `git credential
fill` is not a stand-in for the push path: it IS that path's credential
resolution step, the one `git push` itself runs, and it is the exact decision
the two execution cases below disagree about. The push itself is the
work-item's Host-captured assertion, taken against the live candidate server.

Each execution case runs the ACTUALLY RENDERED prepare steps through `bash`,
against the actually-rendered refreshing `gh` wrapper, so what is measured is
the bytes a dispatch ships rather than a paraphrase of them. The mint log is
the discriminator between the two: a token minted DURING the fill is one line
appended while the fill runs, which a pre-minted token cannot produce, and the
credential-carrying case asserts the log did NOT grow — without that control a
helper that answered every request would satisfy the first case alone.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    SANDBOX_GH_REFRESH_ROOT_ENV_VAR,
)
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
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
_MINTED_TOKEN = "minted-installation-token"
_URL_EMBEDDED_TOKEN = "url-embedded-credential"
_CREDENTIAL_URL = "https://github.com"
# The exact script a dispatch ships. Asserted verbatim rather than by
# containment: the subsection between the first and the last dot is the URL git
# scopes the helper to, so a key assembled one dot differently configures a
# helper for a host no push ever asks about — and reads identical at a glance.
_EXPECTED_STEP_SCRIPT = f"git config credential.{_CREDENTIAL_URL}.helper '!gh auth git-credential'"
_GH_REFRESH_MARKER = "# --- Dispatcher-materialized livespec-refreshing-gh-wrapper ---"


def test_every_dispatch_configures_the_github_credential_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both App-input arms, because "every dispatch" is the assertion.

    The refreshing wrapper itself renders only when the App inputs are present,
    so a helper rendered inside that condition would cover the arm that happens
    to hold on this factory and silently omit the other.
    """
    for app_inputs_present in (True, False):
        for key in ("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY"):
            if app_inputs_present:
                monkeypatch.setenv(key, "42")
            else:
                monkeypatch.delenv(key, raising=False)
        rendered = render_run_config_overlay(
            committed_text=_COMMITTED_WORKFLOW_TOML,
            workflow_dir=tmp_path,
            token=_OAUTH_TOKEN,
            github_token=_GITHUB_TOKEN,
            siblings=None,
        )
        assert rendered is not None
        assert _credential_helper_step(rendered=rendered) == _EXPECTED_STEP_SCRIPT


def test_credential_helper_configuration_carries_no_token_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configuration must name a COMMAND, never a secret.

    A token written into the step would be persisted in the rendered run config
    the server keeps, and then again into the sandbox's own git config file —
    two durable copies of a credential whose whole point is that it is minted
    per push and never stored.
    """
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None
    step = _credential_helper_step(rendered=rendered)
    assert _OAUTH_TOKEN not in step
    assert _GITHUB_TOKEN not in step
    assert "stub-pem" not in step

    clone = _git_clone(tmp_path=tmp_path)
    _run(argv=["/bin/bash", "-c", step], cwd=clone, env=_scrubbed_env())
    written = (clone / ".git" / "config").read_text(encoding="utf-8")
    assert _OAUTH_TOKEN not in written
    assert _GITHUB_TOKEN not in written
    assert "!gh auth git-credential" in written


def test_push_without_a_url_credential_mints_a_token_at_push_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Petri-era case: origin carries no credential, so git asks the helper."""
    sandbox = _provision_sandbox(tmp_path=tmp_path, monkeypatch=monkeypatch)
    before = _mint_call_count(sandbox=sandbox)

    filled = _credential_fill(sandbox=sandbox, url=f"{_CREDENTIAL_URL}/owner/repo.git")

    assert "username=x-access-token" in filled
    assert f"password={_MINTED_TOKEN}" in filled
    # Minted DURING the fill -- a token resolved any earlier could not have
    # appended this line while git was waiting on the helper's answer.
    assert _mint_call_count(sandbox=sandbox) == before + 1


def test_push_with_a_url_credential_keeps_that_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pinned-engine case: Fabro's URL-embedded token still wins.

    Control for the case above. git consults no helper once a URL carries both
    a username and a password, so configuring one must leave the pinned engine's
    path byte-for-byte as it was.
    """
    sandbox = _provision_sandbox(tmp_path=tmp_path, monkeypatch=monkeypatch)
    before = _mint_call_count(sandbox=sandbox)

    filled = _credential_fill(
        sandbox=sandbox,
        url=f"https://x-access-token:{_URL_EMBEDDED_TOKEN}@github.com/owner/repo.git",
    )

    assert f"password={_URL_EMBEDDED_TOKEN}" in filled
    assert _MINTED_TOKEN not in filled
    assert _mint_call_count(sandbox=sandbox) == before


@dataclass(frozen=True, kw_only=True)
class _Sandbox:
    """A provisioned fixture: the clone git runs in, plus its env and mint log."""

    clone: Path
    env: dict[str, str]
    mint_log: Path


def _provision_sandbox(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _Sandbox:
    """Render and EXECUTE the gh-refresh plus credential-helper prepare steps.

    The bundle root is redirected off the production `/workspace` path for the
    reason `_dispatcher_gh_refresh` records beside the lever: the rendered
    script `rm -rf`s and `mkdir`s that root for real, which at a runner's
    filesystem root is either refused or destructive.
    """
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    monkeypatch.setenv(SANDBOX_GH_REFRESH_ROOT_ENV_VAR, str(tmp_path / "sandbox-bundle"))
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
    )
    assert rendered is not None

    clone = _git_clone(tmp_path=tmp_path)
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    mint_log = tmp_path / "mint-calls.txt"
    mint_log.write_text("", encoding="utf-8")
    # Stands in for the REAL `gh` the wrapper displaces. `auth git-credential`
    # answers from GH_TOKEN exactly as gh 2.102.0 does -- measured against the
    # live binary, which returns `username=x-access-token` plus the token it
    # holds, and prints its "github-token source:" line to stderr.
    _write_executable(
        path=bin_dir / "gh",
        source="#!/usr/bin/env bash\n"
        "set -eu\n"
        'if [ "$1" = "auth" ] && [ "$2" = "git-credential" ]; then\n'
        "  cat > /dev/null\n"
        "  printf 'username=x-access-token\\npassword=%s\\n' \"${GH_TOKEN:-}\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 64\n",
    )
    env = {
        **_scrubbed_env(),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "MINT_LOG": str(mint_log),
    }

    for index, step in enumerate(_prepare_step_scripts(rendered=rendered)):
        script = tmp_path / f"prepare-{index}.sh"
        script.write_text(step, encoding="utf-8")
        _run(argv=["/bin/bash", str(script)], cwd=clone, env=env)
    assert (bin_dir / "gh.livespec-real").is_file()
    assert "!gh auth git-credential" in (clone / ".git" / "config").read_text(encoding="utf-8")

    # Installed only AFTER the prepare chain, which needs a real `python3` to
    # unpack the streamed bundle.
    _write_executable(
        path=bin_dir / "python3",
        source="#!/usr/bin/env bash\n"
        "set -eu\n"
        'printf "%s\\n" "$1" >> "$MINT_LOG"\n'
        f"printf {_MINTED_TOKEN}\n",
    )
    return _Sandbox(clone=clone, env=env, mint_log=mint_log)


def _credential_fill(*, sandbox: _Sandbox, url: str) -> str:
    """Run git's own credential resolution -- the step `git push` performs."""
    completed = subprocess.run(
        ["git", "credential", "fill"],
        cwd=sandbox.clone,
        env=sandbox.env,
        input=f"url={url}\n\n",
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _mint_call_count(*, sandbox: _Sandbox) -> int:
    return len(sandbox.mint_log.read_text(encoding="utf-8").splitlines())


def _git_clone(*, tmp_path: Path) -> Path:
    """An empty repository standing in for the sandbox's own clone."""
    clone = tmp_path / "clone"
    clone.mkdir()
    _run(argv=["git", "init", "--quiet", "."], cwd=clone, env=_scrubbed_env())
    return clone


def _scrubbed_env() -> dict[str, str]:
    """The child environment: no coverage self-instrumentation, no host git config.

    `COVERAGE_PROCESS_START` would make the bundle-unpacking `python3` write a
    `.coverage.*` that races the parallel check dispatcher. The git config
    redirects keep the runner's own global and system config -- which may well
    carry a credential helper of its own -- out of the measurement.

    Dropping every `GIT_CONFIG*` variable completes that same isolation at the
    PROCESS scope, which the two redirects above cannot reach. A Petri-era
    sandbox is handed `GIT_CONFIG_COUNT` plus the matching
    `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` pairs, and that scope outranks the
    clone's own config: measured in-sandbox, the inherited set carried
    `credential.https://github.com.helper` twice -- once EMPTY, which resets
    the accumulated helper list, then once naming the runner's own
    `credential-store`. The clone-scoped `!gh auth git-credential` this test
    configures was therefore discarded before git ever consulted it, and
    `git credential fill` died `could not read Username` with the fixture
    perfectly sound. Explicitly NOT a claim about the production push path:
    what a real in-sandbox push resolves is the work-item's Host-captured
    assertion, and this helper only keeps the host out of THIS measurement.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COV") and not key.startswith("GIT_CONFIG")
    }
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _write_executable(*, path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _run(*, argv: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _credential_helper_step(*, rendered: str) -> str:
    """The one credential-helper step script, decoded from its TOML string."""
    found = re.findall(r'^script = ("git config credential\..*")$', rendered, re.MULTILINE)
    assert len(found) == 1, f"expected exactly one credential-helper step, got {found}"
    decoded = json.loads(found[0])
    assert isinstance(decoded, str)
    return decoded


def _prepare_step_scripts(*, rendered: str) -> list[str]:
    """The gh-refresh steps plus the credential-helper step, in rendered order.

    Bounded at the gh-refresh marker and at the NEXT dispatcher-materialized
    block: the overlay appends further blocks after these, and this caller
    EXECUTES what it returns against the runner's own environment, so reading
    past the boundary hands a later block's steps to a `bash` holding the real
    `$HOME`.
    """
    start = rendered.index(_GH_REFRESH_MARKER)
    tail = rendered[start + len(_GH_REFRESH_MARKER) :]
    credential_step = _credential_helper_step(rendered=rendered)
    boundary = tail.index(json.dumps(credential_step))
    scripts = re.findall(r"script = '''\n(.*?)\n'''", tail[:boundary], re.DOTALL)
    assert scripts, "the gh-refresh block emitted no prepare steps"
    return [*scripts, credential_step]
