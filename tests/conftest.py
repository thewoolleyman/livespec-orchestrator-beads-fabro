"""Top-level fixtures shared across every test tree.

These fixtures exist for one reason: the suite must answer the same way on
every machine it runs on. Each one replaces an AMBIENT host dependency the
dispatch path would otherwise read — the host Codex credential, the host
`fabro` engine binary, the host `gh`, the per-profile OAuth token slots
the credential wrapper injects, the dispatching operator's own invoker
identity and factory selection — with a hermetic stand-in, so the suite
never depends on whether the runner is logged in, has the engine
installed, ships `gh` on the step-subprocess PATH, is dispatching work,
or is running inside that wrapper.

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
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pytest
from hypothesis import settings
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._config_acp import resolve_acp_node_overlays

# Hypothesis's per-example WALL-CLOCK deadline, turned off suite-wide.
#
# The deadline is a PERFORMANCE assertion about the host, not a correctness
# assertion about the property under test — and it is the LAST ambient host
# dependency this module had left standing, which is why it is disarmed here
# beside the fixtures rather than per decorator. `just check` drives 7000+
# tests across four xdist workers with branch coverage tracing every statement,
# on a shared factory host that is routinely at load, so one example stalling
# past the 200ms default is a scheduler hiccup. Hypothesis reports it as
# `FlakyFailure: Unreliable test timings!`, whose remedy is to run the suite
# again — a red gate that says nothing about the code.
#
# Measured 2026-10-11 on `test_dispatcher_proof_attachment.py`'s round-trip
# property, which a janitor run failed while two standalone runs of the same
# commit passed: no input can falsify that assertion (its name and url are
# constants, every digest is `sha256:` + hex, and `str(int)` is always digits)
# and the example database held no counterexample, so the timing was the only
# reachable failure. Under oversubscribed load its per-example runtimes reached
# 185ms against the 200ms ceiling — 15ms of headroom, i.e. the gate turned on
# scheduler noise. Eight test modules draw on hypothesis and every one of them
# ran that exposure.
#
# Turning the deadline off removes a timing assertion and NOTHING else: every
# example still runs and every assert still holds. `tests/test_hypothesis_
# profile.py` binds both halves of that — the profile, and a property that
# genuinely outruns the old ceiling.
settings.register_profile("livespec", deadline=None)
settings.load_profile("livespec")


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
        "_dispatcher_credential_env.probe_claude_credential",
        successful_probe,
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_claude_credential_command.probe_claude_credential",
        successful_probe,
    )


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


_FACTORY_CREDENTIAL_SLOT_PREFIX = "CLAUDE_CODE_OAUTH_TOKEN__"

_PROJECTED_CREDENTIAL_USE_ENV = (
    "LIVESPEC_CREDENTIAL_EXPIRY_EPOCH",
    "LIVESPEC_CREDENTIAL_REQUIRED_REMAINING_SECONDS",
    "LIVESPEC_CREDENTIAL_USE_UNPROTECTED",
)


@pytest.fixture(autouse=True)
def _hermetic_projected_credential_use(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep worker-only credential-use projections out of the test process.

    The factory projects these values for a real dispatched worker. They are
    ambient runtime inputs, not repository test configuration. If they reach
    pytest, a deadline-only guard test silently becomes a credential-grade
    test and its synthetic one-hour deadline is judged against the factory
    run's longer required lifetime.

    THE UNPROTECTED DECLARATION IS THE THIRD MEMBER OF THAT SET, and it was
    missing here until 2026-10-16 because it was added to the projection after
    this fixture was written. The guard refuses when it is set ALONGSIDE a
    deadline -- "the declaration must be '1' and must stand alone" -- and it
    fails CLOSED, so an unprotected sandbox leaked the declaration into every
    child these cases spawn and 27 of them refused at startup instead of
    exercising the deadline. Measured in a factory sandbox whose PID 1 carries
    `LIVESPEC_CREDENTIAL_USE_UNPROTECTED=1`: 27 failed with the var ambient, 91
    passed with it removed, on a tree whose eight credential-use modules are
    byte-identical to master. `test_dispatcher_credential_use_unprotected.py`
    was unaffected throughout -- it pops the name in its own `_hermetic_env`
    and sets it explicitly per case, which is the precedent this follows.

    Tests that exercise the grade or the unprotected route set the names they
    need explicitly after this fixture runs. Every other test starts from the
    same absent state on a developer host, in CI, and inside a factory sandbox.
    """
    for name in _PROJECTED_CREDENTIAL_USE_ENV:
        monkeypatch.delenv(name, raising=False)


_AMBIENT_OPERATOR_ENV = (
    "LIVESPEC_INVOKER",
    "LIVESPEC_FABRO_FACTORY",
)


@pytest.fixture(autouse=True)
def _hermetic_operator_attribution_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the DISPATCHING operator's attribution and routing out of pytest.

    These two are the operator's own inputs to a dispatch — who is asking
    (`LIVESPEC_INVOKER`, which `drive` forwards to the Dispatcher as an
    explicit `--invoker <id>`) and which factory to route it to
    (`LIVESPEC_FABRO_FACTORY`, which outranks the committed default). They are
    ambient per-invocation inputs, not repository test configuration, and they
    are exactly the shape of ambient host dependency this file exists to
    replace: a case that resolves either one answers differently depending on
    whether the session running the suite happens to export it.

    The asymmetry is what makes it expensive. Continuous integration exports
    NEITHER, so a case that reads one is permanently green there, while a
    session that DISPATCHES exports the identity because the driver's gate
    requires it — and `just check` runs inside that session on every pre-push
    and inside the post-merge janitor. Measured 2026-10-18 at master
    d36799fa: with `LIVESPEC_INVOKER` exported, two of the four Scenario 17
    drive cases failed because the forwarded `--invoker` pair shifts the
    dispatcher argv past the index they read, so a dispatching session got a
    red host-side pre-push on every branch while the same tree's
    default-branch continuous integration was green (work-item
    bd-ib-untu6x). `bd-ib-fd26sc` removed both names from the janitor's own
    child environment, which fixed the janitor and not the suite's own
    process; this is that half.

    Scrubbing them is the whole fixture. A case that needs either value sets
    it explicitly after this fixture runs — the precedent the seven cases
    already popping `LIVESPEC_INVOKER` per test established, and which
    `monkeypatch` restores at teardown either way.
    """
    for name in _AMBIENT_OPERATOR_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _hermetic_factory_credential_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrub the wrapper-injected per-profile credential slots for every test.

    `select_factory_credential` follows the caam rotation: it reads the
    published profile from `~/.local/state/caam-usage-rotate/selected-account.json`
    and, when the environment carries the matching
    `CLAUDE_CODE_OAUTH_TOKEN__<PROFILE>` pool slot, NAMES that slot — and both
    callers then read its value out of the real process environment. That is
    correct for a real dispatch and is exactly the ambient host dependency this
    file exists to replace for a test: a test supplying its own token under the
    unnumbered `CLAUDE_CODE_OAUTH_TOKEN` had it OVERRIDDEN by the host's real
    one, so the value reaching the credential gate and the run-config overlay
    depended on whose machine the suite ran on.

    Scrubbing the SLOTS is what makes the record inert, which is why this
    fixture does not touch `HOME`. The record can only win THROUGH a matching
    slot, so with no slot present the selector reaches its documented fallback
    — the unnumbered token — whatever profile the record names, and whether or
    not a record exists at all. Repointing `HOME` instead would reach a dozen
    unrelated `Path.home()` reads (the plugin-cache gate, the janitor worktree
    roots, the needs-attention core roots) and change answers this defect has
    nothing to do with.

    Measured on the dispatching host 2026-10-09 (work-item bd-ib-vvs645): the
    record named `anthropic-1`, the wrapper injected
    `CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_1`, and four dispatcher tests failed
    inside the credential wrapper while the same aggregate passed outside it —
    so every post-merge janitor, which runs `just check` under that wrapper,
    went red and merged items could not be closed. Continuous integration
    carries no slot variables, so the fallback hid the defect there
    permanently. The names are enumerated from a SNAPSHOT of `os.environ`
    because `delenv` mutates the mapping being read; `monkeypatch` restores
    every one of them at teardown, so a test asserting the rotation-following
    selection sets the slot it needs back explicitly.
    """
    for name in [name for name in os.environ if name.startswith(_FACTORY_CREDENTIAL_SLOT_PREFIX)]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _hermetic_session_headroom_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer every admission pass's session-headroom read without a provider.

    THE SECOND BOUNDED LIVE MESSAGES REQUEST, and the exact analogue of
    `_hermetic_claude_credential_probe` above: the admission valve builds a
    session-headroom policy per evaluation, and that policy's default read
    issues one `POST /v1/messages` to Anthropic for the five-hour utilization
    header. Left ambient, a hermetic dispatch test with any plausible
    `CLAUDE_CODE_OAUTH_TOKEN` in scope would reach the provider from pytest,
    and one with none would grade the reading UNOBSERVABLE -- which the clause
    skips exactly as a below-floor reading, so every covered candidate would
    leave the selectable set and every dispatch test would be refused before
    claim. Both outcomes depend on the runner rather than on the code, which is
    what this file exists to remove.

    IT WAS UNREACHABLE BEFORE AND IS NOT NOW, which is why it arrives with the
    no-fallback assessment rather than with the clause. Every repository
    fixture in this suite declares no ACP chain, so the preflight used to
    short-circuit before any policy was consulted; it no longer does, because
    the clause covers "built-in single-candidate nodes without fallback
    metadata" and those fixtures resolve exactly that through the bundled
    default workflow.

    THE STAND-IN READS AN UNTOUCHED WINDOW, so admission is graded exactly as
    it was before the path became reachable: a full allowance passes every
    floor, so no fixture changes answer and no case becomes vacuous. It is the
    same direction `_hermetic_claude_credential_probe` takes in returning a
    USABLE probe.

    ONLY THE PRODUCTION CALL SITE IS PATCHED. Every test that exercises the
    policy itself injects its own `read` and reaches no provider already, and
    patching the builder in its own module would also wrap it for those -- one
    of which binds the builder at import time and one of which asserts its
    signature.
    """
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission
    from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
        SessionHeadroomPolicy,
        SessionHeadroomReading,
        session_headroom_reading,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_gate import (
        session_headroom_policy,
    )

    def untouched_window(*, token: str | None, observed_at: str) -> SessionHeadroomReading:
        _ = token
        return session_headroom_reading(
            credential_identity="hermetic-session-headroom",
            observed_at=observed_at,
            utilization=0,
        )

    def hermetic_policy(**kwargs: Any) -> SessionHeadroomPolicy:
        _ = kwargs.setdefault("read", untouched_window)
        return session_headroom_policy(**kwargs)

    monkeypatch.setattr(_dispatcher_admission, "session_headroom_policy", hermetic_policy)


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
# The watchdog launcher fixtures' END-OF-RUN wait
# ---------------------------------------------------------------------------

# `WatchedFabroLauncher` runs `fabro run` on a thread it names after the work
# item it launched, and sets its OWN `run_returned` signal LAST — after
# `port.run` has returned AND the result has been published — because the
# watch loop reads that signal as the run being over.
#
# A fixture that releases a healthy fake run and then waits on the FAKE
# runner's own `run_returned` is therefore one step too early: the scripted
# runner sets that signal BEFORE it returns its `CommandResult`, so the watch
# loop can resume while the launcher's signal is still unset, find the run
# apparently still live, and take one more liveness sample. Under the injected
# clocks those fixtures use — which jump 600 seconds per reading — that extra
# sample pushes the quiet window past the bound the case declares, and the
# watchdog correctly cancels a run the case calls healthy. Measured
# 2026-10-18 in gate run 20261018T062039Z-3681040 at load15 16 to 20: one
# failure in 9335 tests, `stalled_run_id` reading `'01RUN'` where the case
# asserts None, while the same case passed 5 of 5 in isolation (bd-ib-spc6xr).
# Production is unaffected — with a real clock an extra sample costs seconds
# rather than 600 — so the defect is in the fixtures' wait and nowhere else.
#
# Joining the launcher's own thread is the wait that CANNOT be early: that
# thread exits only after the launcher has set its signal, so once the join
# returns the next check at the top of the watch loop ends the watch with no
# further sample.
_LAUNCHER_RUN_THREAD_PREFIX = "fabro-run-"

# Generous, because it bounds nothing a healthy fixture depends on: the fake
# runner returns as soon as it is released, so this only decides how long a
# genuinely wedged launcher thread is given before the wait reports it.
_LAUNCHER_RETURN_TIMEOUT_SECONDS = 10.0


def end_run_and_await_launcher_return(*, run_done: threading.Event, work_item_id: str) -> None:
    """Release a healthy fake `fabro run` and wait for the LAUNCHER to observe it.

    The wait every watchdog launcher fixture takes when it ends a healthy run
    from its injected sleep, so the watch loop cannot poll again between the
    run's return and the launcher's own return signal.

    The launcher thread is REQUIRED to be found rather than waited on if it
    happens to exist: a lookup that silently matched nothing would hand the
    caller back the early wait it is replacing, and report it as the
    launcher-side one.
    """
    run_done.set()
    name = f"{_LAUNCHER_RUN_THREAD_PREFIX}{work_item_id}"
    launcher_threads = [thread for thread in threading.enumerate() if thread.name == name]
    assert launcher_threads, f"no launcher run thread named {name} is alive"
    for thread in launcher_threads:
        thread.join(timeout=_LAUNCHER_RETURN_TIMEOUT_SECONDS)
        assert not thread.is_alive(), f"{name} did not return within its wait"


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

    IT DECLARES NO `pr_adapter`, and that absence is load-bearing rather than an
    omission. An IMPLEMENTATION workflow publishes through command stages
    (`SPECIFICATION/contracts.md`, the scripted-publication clause), so the
    committed workflow declares no publication adapter input and no dispatch
    renders one. A fixture that kept declaring one would hand every consumer a
    layer no dispatch builds — and because this fixture claims above to mirror
    the committed shape, that divergence would be invisible: the tests would
    keep passing against a `pr_adapter` production stopped rendering. A
    groom-kind variant's own `pr_adapter` is a property of THAT payload, so a
    test about it reads that payload rather than this literal.
    """

    def _resolve(*, repo: Path) -> Any:
        claude = "npx -y @agentclientprotocol/claude-agent-acp"
        implementer = f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {claude}"
        overlays = resolve_acp_node_overlays(cwd=repo)
        assert not isinstance(overlays, str), overlays
        resolution = resolve_acp_nodes(
            workflow_inputs={
                "implement_adapter": implementer,
                "fix_adapter": implementer,
                "review_fix_adapter": implementer,
                "review_adapter": claude,
                "disposition_adapter": claude,
                "dod_gate_adapter": claude,
            },
            repository=overlays,
            dispatch={},
        )
        assert not isinstance(resolution, str), resolution
        return resolution

    return _resolve
