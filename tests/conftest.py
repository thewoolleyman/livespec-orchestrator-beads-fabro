"""Top-level fixtures shared across every test tree.

These fixtures exist for one reason: the suite must answer the same way on
every machine it runs on. Each one replaces an AMBIENT host dependency the
dispatch path would otherwise read — the host Codex credential, the host
`fabro` engine binary, the host `gh` — with a hermetic stand-in, so the
suite never depends on whether the runner is logged in, has the engine
installed, or ships `gh` on the step-subprocess PATH.

The Claude credential pre-flight similarly makes one bounded live Messages
API request before a dispatch. Tests receive a successful non-secret probe
result by default so no hermetic dispatch test reaches Anthropic; the probe
I/O module's own tests exercise the real request construction through a
mocked ``urlopen``.

The dispatch path projects a freshness-gated snapshot of the host Codex
credential into the sandbox (scenarios.md Scenario 18 / 19), reading the
host `auth.json` under `$CODEX_HOME` (default `~/.codex`). EVERY test tree
that exercises a dispatch — the unit command tests under
`tests/livespec_orchestrator_beads_fabro/` AND the integration scenario
tests under `tests/integration/` — must therefore see a fresh, fake
credential rather than the real host one, so the suite is hermetic and
never depends on whether the runner is `codex login`'d (an unguarded read
of a missing `~/.codex` refuses the dispatch and fails every dispatch
test, which is exactly what happens on CI). This autouse fixture lives at
the top level so it reaches every subtree; it points `CODEX_HOME` at a
per-test scratch dir carrying a far-future-`exp` fake credential. Tests
asserting the missing/stale paths override it explicitly (delenv / point
at an empty dir / monkeypatch the read).
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._config import resolve_acp_node_overlays


@pytest.fixture(autouse=True)
def _hermetic_claude_credential_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
        ClaudeCredentialStatus,
    )

    def successful_probe(*, token: str) -> ClaudeCredentialStatus:
        _ = token
        return ClaudeCredentialStatus(
            condition="usable",
            present=True,
            usable=True,
            http_status=200,
            error_type=None,
            input_tokens=8,
            output_tokens=1,
            message="CLAUDE_CODE_OAUTH_TOKEN is usable in the hermetic test probe.",
            remedy="No action required.",
        )

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_credentials.probe_claude_credential",
        successful_probe,
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_claude_credential_command.probe_claude_credential",
        successful_probe,
    )


HERMETIC_MANAGER_CREDENTIAL = "hermetic-manager-oauth-token"
HERMETIC_MANAGER_RECORD_ID = "5f1b7a0c-0000-4000-8000-00000000cafe"
HERMETIC_MANAGER_ACCOUNT_ID = "anthropic-hermetic"


@dataclass(kw_only=True)
class HermeticCredentialManager:
    """A stand-in `CredentialManagerClient` that provisions without a manager process.

    The Dispatcher now obtains every run's Anthropic credential from the
    `llm-provider-manager` executable, which is an AMBIENT HOST DEPENDENCY of exactly the
    kind this file exists to replace: it is absent on CI, it holds real credentials for
    real accounts where it IS installed, and a dispatch that reached it would neither be
    hermetic nor safe. So every dispatch test provisions through this fake by default.

    It records the reports it receives so a test can assert what the dispatch told the
    credential authority, and `refusal` lets a test drive the refusal arm without
    replacing the whole fixture.
    """

    refusal: Any = None
    reports: list[Any] = field(default_factory=list)

    def provision(self, *, consumer_run_id: str) -> Any:
        from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
            CredentialReceipt,
            ProvisionedCredential,
        )

        _ = consumer_run_id
        if self.refusal is not None:
            return self.refusal
        return ProvisionedCredential(
            receipt=CredentialReceipt(
                record_id=HERMETIC_MANAGER_RECORD_ID,
                account_id=HERMETIC_MANAGER_ACCOUNT_ID,
                validated_at="2026-09-12T00:00:00Z",
                purpose="factory",
                lease_expires_at="2026-09-12T06:00:00Z",
            ),
            value=HERMETIC_MANAGER_CREDENTIAL,
        )

    def report(self, *, report: Any) -> Any:
        self.reports.append(report)
        return None


@pytest.fixture(autouse=True)
def hermetic_credential_manager(monkeypatch: pytest.MonkeyPatch) -> HermeticCredentialManager:
    """Provision every dispatch from the fake manager, never the host executable.

    Patched at the two modules that CONSTRUCT the default client, matching how the
    Claude-probe fixture above patches the name in each consuming module. A test wanting
    a refusal sets `.refusal` on the object this fixture returns; a test wanting to
    assert a failure report reads `.reports`.
    """
    manager = HermeticCredentialManager()
    for module in ("_dispatcher_credentials", "_dispatcher_loop"):
        monkeypatch.setattr(
            f"livespec_orchestrator_beads_fabro.commands.{module}.LlmProviderManagerClient",
            lambda **_kwargs: manager,
        )
    return manager


def _fresh_codex_auth_json() -> str:
    """A host Codex `auth.json` whose access-token JWT `exp` is a century out.

    A far-future `exp` keeps every dispatch test past the freshness gate
    against the real clock the dispatch path reads. The refresh token is a
    placeholder — `project_codex_auth_snapshot` replaces it with the inert
    sentinel before the snapshot reaches the overlay.
    """
    exp = int(time.time()) + 100 * 365 * 24 * 3600
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    access_token = f"header.{payload}.sig"
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": access_token,
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


@pytest.fixture(autouse=True)
def _hermetic_codex_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    codex_home = tmp_path_factory.mktemp("codex-home")
    _ = (codex_home / "auth.json").write_text(_fresh_codex_auth_json(), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))


@pytest.fixture(autouse=True)
def _hermetic_state_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Point every host-local state read and write at a per-test scratch root.

    `state_root()` resolves `XDG_STATE_HOME`, else the REAL `~/.local/state`,
    and two surfaces write beneath it: the run-turn export marker, and the
    tenant-checkout registry that makes the WIP-cap counted-claim bound
    tenant-scoped. Left ambient, a test would both pollute the developer's home
    and READ another test's entries back — the registry is keyed by tenant
    NAME, and several fixtures here declare the same one — so the suite would
    answer differently depending on which tests ran before it. That is exactly
    the ambient-host dependency this file exists to replace. Tests asserting
    the `~/.local/state` fallback itself delete the variable explicitly.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path_factory.mktemp("state-home")))


@pytest.fixture(autouse=True)
def _hermetic_release_adoption_bases(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Point the release-adoption lane at empty registries, not the real HOME.

    The lane reads this machine's Claude plugin registries to answer which
    adopters resolved the current release. That is an AMBIENT host dependency
    of exactly the kind this file exists to replace: on a runner with no
    installs it composes nothing, and on the maintainer's own machine it would
    compose real adopter items into every `build_attention` assertion. The
    lane's own tests inject their fixtures explicitly.
    """
    from livespec_orchestrator_beads_fabro.commands import needs_attention
    from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
        ReleaseAdoptionBases,
    )

    empty = tmp_path_factory.mktemp("claude-plugins")
    monkeypatch.setattr(
        needs_attention,
        "default_release_adoption_bases",
        lambda: ReleaseAdoptionBases(
            install_record=empty / "installed_plugins.json",
            marketplace_record=empty / "known_marketplaces.json",
        ),
    )


@pytest.fixture(autouse=True)
def _hermetic_fabro_auth_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Point the Fabro bearer-credential read at an absent scratch file.

    `resolve_bearer_token` falls back to `~/.fabro/auth.json`, which is where
    `fabro auth login` leaves a real token — so on the maintainer's own host,
    and on the factory hosts themselves, every port built for a configured
    server url would silently acquire an Authorization header that a runner
    with no login never sees. That is the ambient-host dependency this file
    exists to replace, and it would flip assertions about the unauthenticated
    posture rather than merely adding noise. The credential-resolution tests
    point this seam at their own fixtures explicitly.
    """
    from livespec_orchestrator_beads_fabro.commands import _fabro_port_auth

    absent = tmp_path_factory.mktemp("fabro-home") / "auth.json"
    monkeypatch.setattr(_fabro_port_auth, "fabro_auth_file", lambda: absent)


@pytest.fixture(autouse=True)
def _clear_dispatch_surface_bytecode(request: pytest.FixtureRequest) -> None:
    if request.node.path.name != "test_fleet_pat_dispatch_surface.py":
        return
    scripts_root = Path(__file__).resolve().parents[1] / ".claude-plugin" / "scripts"
    for cache_dir in scripts_root.rglob("__pycache__"):
        shutil.rmtree(cache_dir)


@pytest.fixture(scope="session")
def _fabro_stub_bin(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A real, executable throwaway `fabro` binary shared across the suite.

    The Dispatcher preflight (`_fabro_preflight_error`) refuses BEFORE
    admission when the resolved `fabro` engine binary is not an existing
    executable. The real default is the host's `$HOME/.fabro/bin/fabro`, which
    is absent on CI — so without a hermetic override EVERY dispatch/loop test
    that omits an explicit `--fabro-bin` would refuse at preflight. This
    session-scoped stub is a genuine chmod-0o755 file so the preflight's
    is_file + X_OK check passes.
    """
    stub_dir = tmp_path_factory.mktemp("fabro-stub-bin")
    stub = stub_dir / "fabro"
    _ = stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    return str(stub)


GH_STUB_EXIT_ENV = "LIVESPEC_TEST_GH_EXIT"
GH_STUB_STDOUT_ENV = "LIVESPEC_TEST_GH_STDOUT"
GH_STUB_LOG_ENV = "LIVESPEC_TEST_GH_LOG"

# The default-convention pipeline the master-CI preflight resolves for a repo
# that declares no `dispatcher.master_ci` — which is every throwaway repo the
# dispatch tests build. The preflight is FAIL-CLOSED: it refuses a host it
# cannot prove green, so a hermetic dispatch test needs a provably-green answer
# for the same reason it needs a `fabro` binary and a Codex credential. Scripting
# a specific `gh` outcome still wins; these answers only fill the unscripted
# default, and the branch answer is deliberately NOT the repo's own primary
# branch name, so a test passes only if the lookup used the RESOLVED branch.
_GH_STUB_DEFAULT_BRANCH = "main"
_GH_STUB_RUN_LIST = '[{"status":"completed","conclusion":"success","databaseId":900001}]'
_GH_STUB_JOBS = '{"jobs":[{"name":"ci-green","conclusion":"success","status":"completed"}]}'

# A real, executable `gh` stand-in. It never touches the network: it records
# its argv when asked, replays a scripted stdout, and exits a scripted code
# (default 1 — the "no observable PR" answer the real `gh` gives in the
# throwaway repos the dispatch tests build).
_GH_STUB_SOURCE = f"""#!/bin/sh
if [ -n "${{{GH_STUB_LOG_ENV}:-}}" ]; then
  printf '%s\\n' "$*" >> "${GH_STUB_LOG_ENV}"
fi
if [ -z "${{{GH_STUB_STDOUT_ENV}:-}}" ] && [ -z "${{{GH_STUB_EXIT_ENV}:-}}" ]; then
  case "$*" in
    'auth token') printf 'hermetic-gh-token\\n'; exit 0 ;;
    *defaultBranchRef*) printf '{_GH_STUB_DEFAULT_BRANCH}\\n'; exit 0 ;;
    'run list --branch'*) printf '%s' '{_GH_STUB_RUN_LIST}'; exit 0 ;;
    'run view'*'--json jobs') printf '%s' '{_GH_STUB_JOBS}'; exit 0 ;;
  esac
fi
if [ -n "${{{GH_STUB_STDOUT_ENV}:-}}" ]; then
  printf '%s' "${GH_STUB_STDOUT_ENV}"
fi
exit "${{{GH_STUB_EXIT_ENV}:-1}}"
"""


@pytest.fixture(scope="session")
def _gh_stub_bin(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A real, executable throwaway `gh` shared across the suite.

    Several production paths shell out to `gh` through the REAL
    `ShellCommandRunner` rather than an injected one — the post-verdict
    self-update's `resolve_merged_paths` (`gh pr view <branch> --json
    files`), the janitor's `gh repo view`, the reflector's `gh pr create`,
    the fleet-manifest fetch. Letting those reach the host's `gh` makes the
    suite non-hermetic (an ambient login, a real network call, and an
    answer that differs per machine); letting them reach NO `gh` at all
    used to crash the dispatch outright. This stub removes both: it is a
    genuine chmod-0o755 file at the head of PATH, so `subprocess.run`
    resolves it and the runner's real spawn path is still exercised.
    """
    stub_dir = tmp_path_factory.mktemp("gh-stub-bin")
    stub = stub_dir / "gh"
    _ = stub.write_text(_GH_STUB_SOURCE, encoding="utf-8")
    stub.chmod(0o755)
    return str(stub_dir)


@pytest.fixture(autouse=True)
def _hermetic_gh_bin(monkeypatch: pytest.MonkeyPatch, _gh_stub_bin: str) -> None:
    """Shadow any host `gh` with the scriptable stub for EVERY test.

    Prepending the stub dir to PATH reaches every caller uniformly — the
    injected-runner unit tier and the production-runner dispatch tiers
    alike — so no test depends on whether the runner image ships `gh`.
    Tests drive a specific `gh` outcome by setting `LIVESPEC_TEST_GH_EXIT`
    / `LIVESPEC_TEST_GH_STDOUT`, or assert the argv by pointing
    `LIVESPEC_TEST_GH_LOG` at a scratch file; the absent-`gh` path is
    driven by putting a PATH with no `gh` on it back in place.
    """
    monkeypatch.setenv("PATH", f"{_gh_stub_bin}{os.pathsep}{os.environ['PATH']}")
    for name in (GH_STUB_EXIT_ENV, GH_STUB_STDOUT_ENV, GH_STUB_LOG_ENV):
        monkeypatch.delenv(name, raising=False)


@dataclass(frozen=True, kw_only=True)
class ScriptedGh:
    """Control surface for the hermetic `gh` stand-in, handed to a test.

    Keeps the stub's env contract in ONE place: a test scripts an outcome
    with `script(...)` and reads back the argvs the code under test
    actually spawned with `argv_lines()`, instead of restating the
    `LIVESPEC_TEST_GH_*` variable names and risking drift from the stub.
    """

    monkeypatch: pytest.MonkeyPatch
    log_path: Path

    def script(self, *, exit_code: int, stdout: str = "") -> None:
        """Make every later `gh` call exit `exit_code` and print `stdout`."""
        self.monkeypatch.setenv(GH_STUB_EXIT_ENV, str(exit_code))
        self.monkeypatch.setenv(GH_STUB_STDOUT_ENV, stdout)

    def argv_lines(self) -> list[str]:
        """Every `gh` argv spawned so far, one space-joined line each."""
        return self.log_path.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def scripted_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ScriptedGh:
    """Script the PATH `gh` stub and capture the argvs it is called with."""
    log_path = tmp_path / "gh-argv.log"
    log_path.touch()
    monkeypatch.setenv(GH_STUB_LOG_ENV, str(log_path))
    return ScriptedGh(monkeypatch=monkeypatch, log_path=log_path)


@pytest.fixture
def absent_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Put a PATH carrying NO `gh` at all in place (the baked-image shape).

    The fabro-sandbox image resolves `gh` through a mise shim that is not
    on the step-subprocess PATH, so production code there spawns an
    executable that does not exist. This fixture reproduces exactly that.
    """
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))


@pytest.fixture(autouse=True)
def _hermetic_fabro_bin(monkeypatch: pytest.MonkeyPatch, _fabro_stub_bin: str) -> None:
    """Point `LIVESPEC_FABRO_BIN` at a resolvable stub for every test.

    Keeps the dispatch/loop suite hermetic against the new engine-binary
    preflight: dispatch/loop tests that omit `--fabro-bin` resolve to this
    absolute stub and pass preflight rather than refusing on a machine without
    the real `$HOME/.fabro/bin/fabro`. Tests asserting the refusal / default
    paths override it explicitly (an explicit `--fabro-bin`, or `delenv`).
    """
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", _fabro_stub_bin)


@pytest.fixture(scope="session", autouse=True)
def _hermetic_source_checkout(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Make pytest's temp root a real, origin-reachable git worktree.

    The source-checkout preflight is FAIL-CLOSED on both arms: it refuses a
    checkout whose HEAD no `origin/*` ref contains, and it refuses a path that
    is not a git worktree at all, because neither can prove the base Fabro
    would stage is origin-reachable. Every dispatch test builds its throwaway
    `--repo` under this root, so without a hermetic answer they would all
    refuse — the same ambient-host problem the `gh` and `fabro` stubs above
    solve, one layer down.

    The honest fix is to make those throwaway targets what a dispatch target
    genuinely is: a git checkout. One `git init` at the temp ROOT covers every
    per-test directory beneath it, an empty commit gives it a HEAD, and
    pointing `refs/remotes/origin/master` at that same commit makes HEAD
    origin-reachable — so the preflight's real logic runs and PASSES rather
    than being stubbed out of the path. A test asserting a refusal arm injects
    its own runner, and a test that creates its own nested repo shadows this
    one exactly as git itself would.

    No already-initialised guard: every step of the sequence is idempotent, and
    a guard whose other arm a fresh session-scoped basetemp can never reach
    would be a branch no test could cover honestly.
    """
    _git_init_origin_reachable(root=tmp_path_factory.getbasetemp())


def _git_init_origin_reachable(*, root: Path) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    author = {
        "GIT_AUTHOR_NAME": "livespec tests",
        "GIT_AUTHOR_EMAIL": "tests@example.invalid",
        "GIT_COMMITTER_NAME": "livespec tests",
        "GIT_COMMITTER_EMAIL": "tests@example.invalid",
    }
    for argv in (
        ["git", "init", "-b", "master", "."],
        ["git", "commit", "--allow-empty", "-m", "hermetic temp-root base"],
        ["git", "update-ref", "refs/remotes/origin/master", "HEAD"],
    ):
        _ = subprocess.run(  # fixed argv, no shell, hermetic temp root
            argv,
            cwd=str(root),
            check=True,
            capture_output=True,
            env={**env, **author},
        )


# ---------------------------------------------------------------------------
# ACP node adapters — the workflow-defaults layer for plans built by hand
# ---------------------------------------------------------------------------


class ResolveAcpNodes(Protocol):
    def __call__(self, *, repo: Path) -> Any:
        """Resolve every ACP node's adapter for one repo."""
        ...


@pytest.fixture
def resolve_test_acp_nodes() -> ResolveAcpNodes:
    """Resolve a repo's per-node adapters against default workflow inputs.

    A `DispatchPlan` built directly by a test carries NO adapter resolution,
    so it renders no adapter `--input` at all — the honest un-resolved
    behaviour. A test asserting which adapter a node runs therefore has to
    resolve one the way the Dispatcher does, and this is that resolution
    against a workflow declaring one adapter input per node, the shape this
    repo's committed workflow has. The workflow layer is supplied literally
    rather than read from a file so a test can assert which layer won
    without also owning a `workflow.toml`.
    """

    def _resolve(*, repo: Path) -> Any:
        claude = "npx -y @agentclientprotocol/claude-agent-acp"
        implementer = f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {claude}"
        # The publish node's committed default is the Claude Haiku adapter
        # (workflow.toml pr_adapter, v107), mirrored here so a test asserting
        # the un-configured publish node grades against the real default.
        publish = f"ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high {claude}"
        overlays = resolve_acp_node_overlays(cwd=repo)
        assert not isinstance(overlays, str), overlays
        resolution = resolve_acp_nodes(
            workflow_inputs={
                "implement_adapter": implementer,
                "fix_adapter": implementer,
                "review_fix_adapter": implementer,
                "pr_adapter": publish,
                "review_adapter": claude,
                "disposition_adapter": claude,
            },
            repository=overlays,
            dispatch={},
        )
        assert not isinstance(resolution, str), resolution
        return resolution

    return _resolve
