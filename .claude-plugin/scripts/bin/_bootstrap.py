"""Pre-livespec_orchestrator_beads_fabro-import bootstrap: sys.path setup + Python version check.

Imported by every bin/*.py wrapper before any livespec_orchestrator_beads_fabro import.
Lives under bin/ so the wrappers can `raise SystemExit(main())` per the
shebang-wrapper contract.

At the tail of `bootstrap()` — AFTER the sys.path inserts make the vendored
`livespec_runtime` importable — the credential self-heal chokepoint runs. It
delegates the decision to the pure `decide_credentials` brain in
`livespec_runtime.credentials` and performs the impure act it prescribes:
proceed normally, re-exec the process through the project's configured
`credential_wrapper` (so the wrapper injects the missing tenant secret), or
fail with an actionable diagnostic. This covers every bin/*.py CLI that calls
`bootstrap()` at once, so a bare invocation without `BEADS_DOLT_PASSWORD`
self-heals instead of failing deep in the beads backend with a raw auth error.

That re-exec runs through `sudo`, which rebuilds the environment from its own
policy, so it is also the point where a non-secret session marker can be
silently DESTROYED — see `_marker_forwarded_argv`, which carries the
unattended-plan-resume marker across it.
"""

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

__all__: list[str] = ["bootstrap"]

# The tenant secret every beads-backed orchestrator CLI needs at call time —
# the DEFAULT `required` set; wrappers with a different secret surface pass
# their own (see `bootstrap`).
_REQUIRED_CREDENTIALS = ("BEADS_DOLT_PASSWORD",)
# The family tenant password authenticates the SHARED dolt-server tenant DB.
# An EMBEDDED, self-contained Dolt ledger (initialized with no `--server`)
# needs none, so it is dropped from `required` for a non-server project.
# (This is the env-var NAME, not a secret value.)
_TENANT_ENV_NAME = "BEADS_DOLT_PASSWORD"
_BEADS_CONFIG_RELPATH = (".beads", "config.yaml")
_SERVER_MODE_MARKER = "dolt.mode:server"
_LIVESPEC_CONFIG_FILENAME = ".livespec.jsonc"
_CREDENTIAL_FAIL_EXIT = 3
# The unattended-plan-resume marker. NOT a secret and never a member of
# `required`: the credential self-heal neither needs it nor injects it — it
# only has to stop DESTROYING it (see `_marker_forwarded_argv`). The name is
# re-declared here rather than imported from
# `commands._plan_timeline.UNATTENDED_ENV_VAR` because this runs at the
# pre-package boundary, and a credential self-heal must not start depending on
# the store layer importing cleanly; `tests/bin/
# test_bootstrap_unattended_marker_forwarding.py` pins the two spellings equal.
_PLAN_UNATTENDED_ENV_NAME = "LIVESPEC_PLAN_UNATTENDED"
# `env` is the POSIX command that runs its own operand with NAME=value applied.
_ENV_COMMAND = "env"


def bootstrap(*, required: tuple[str, ...] = _REQUIRED_CREDENTIALS) -> None:
    """Set up sys.path, then run the credential self-heal chokepoint.

    `required` names the secret env vars THIS bin wrapper needs at call
    time; the default is the tenant-wide `BEADS_DOLT_PASSWORD` every
    beads-touching CLI consumes. The Dispatcher requires the tenant secret
    PLUS the GitHub App env (GITHUB_APP_ID + GITHUB_PRIVATE_KEY); the
    mint-app-token CLI requires the App env ALONE (a GitHub token mint has
    no business demanding the Dolt password). Either way the set resolves
    ONLY through the governed project's credential_wrapper
    (github-app-auth Pillar 2: missing secrets re-exec through the wrapper
    when one is configured, and FAIL CLOSED when none is — never a fleet
    fallback).
    """
    if sys.version_info < (3, 10):
        sys.stderr.write(
            "livespec-orchestrator-beads-fabro requires Python 3.10+; install via uv.\n"
        )
        raise SystemExit(127)
    bundle_scripts = Path(__file__).resolve().parent.parent
    bundle_vendor = bundle_scripts / "_vendor"
    for path in (bundle_scripts, bundle_vendor):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    _self_heal_credentials(required=_effective_required(required=required, cwd=Path.cwd()))


def _tenant_secret_required(*, cwd: Path) -> bool:
    """Whether this beads CLI invocation needs the family tenant secret.

    `BEADS_DOLT_PASSWORD` authenticates the SHARED dolt-server tenant DB. A
    dispatch against an EMBEDDED ledger — a self-contained Dolt store
    provisioned in embedded mode (no `--server`), e.g. the disposable
    livespec-e2e golden-master target — needs no such password. So require it
    only when the governed project's beads ledger is server-mode (its
    `.beads/config.yaml` declares `dolt.mode: server`), and fail CLOSED
    (require) when that config is absent or unreadable.
    """
    config_path = cwd.joinpath(*_BEADS_CONFIG_RELPATH)
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return True
    return any(line.strip().replace(" ", "") == _SERVER_MODE_MARKER for line in text.splitlines())


def _effective_required(*, required: tuple[str, ...], cwd: Path) -> tuple[str, ...]:
    """Drop the family tenant secret from `required` for an embedded ledger.

    Only the tenant-password env var is mode-conditional; every other member
    of `required` (the GitHub App env) stays unconditionally required.
    """
    if _tenant_secret_required(cwd=cwd):
        return required
    return tuple(name for name in required if name != _TENANT_ENV_NAME)


def _read_credential_wrapper() -> list[str]:
    """Return the top-level `credential_wrapper` argv-prefix from the governed
    project's `.livespec.jsonc`, tolerating any read/parse quirk as `[]`.

    Fail-open toward "no wrapper": a missing file, malformed JSONC, a
    non-object root, or a non-list value all yield `[]` — which, when the
    secret is also missing, produces the actionable `Fail` diagnostic rather
    than crashing bootstrap on a config quirk.
    """
    # Deferred import: the package is on sys.path only AFTER `bootstrap()`'s
    # inserts run, so this cannot be a module-level import.
    from livespec_orchestrator_beads_fabro.commands._jsonc import JsoncParseError, loads

    config_path = Path.cwd() / _LIVESPEC_CONFIG_FILENAME
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        parsed = loads(text=raw_text)
    except JsoncParseError:
        return []
    if not isinstance(parsed, dict):
        return []
    mapping = cast("dict[str, object]", parsed)
    raw_wrapper = mapping.get("credential_wrapper", [])
    if not isinstance(raw_wrapper, list):
        return []
    return [str(token) for token in cast("list[object]", raw_wrapper)]


def _marker_forwarded_argv(
    *,
    reexec_argv: Sequence[str],
    credential_wrapper: Sequence[str],
    environ: Mapping[str, str],
) -> list[str]:
    """Carry the unattended-resume marker across the credential re-exec.

    The wrapper is a `sudo -n` escalation, and sudo rebuilds the environment
    from its own policy: the reference `with-livespec-env.sh` forwards
    `WRAPPER_STAGE` and `OP_ENV_WRAPPER_CACHE_TTL` and nothing else. So a
    `LIVESPEC_PLAN_UNATTENDED` set by the overseer daemon on the session it
    restarts does NOT survive into the wrapped process, and the plan resume
    there reads an unattended session as attended — `ask=True`, no error, a
    hands-off restart parked on a picker nobody is present to answer.

    What sudo cannot strip is the COMMAND it was asked to run. `reexec_argv` is
    `[*credential_wrapper, executable, *argv]`, so splicing `env NAME=value`
    in at `len(credential_wrapper)` puts the assignment after the wrapper's
    own `--` separator — inside the command, where it is applied by `env` in
    the already-escalated process rather than inherited through it. That is the
    same remedy operators are given for the wrapper by hand; the alternatives
    were rejected on evidence. Editing `with-livespec-env.sh` would make a
    plugin behaviour depend on a host file no clone provisions, and
    `OPENV_PRESERVE_VARS` is applied AFTER the stage-0 escalation that already
    dropped the variable.

    Only a NON-EMPTY marker is forwarded: the empty string is not truthy to
    `is_unattended_session`, so forwarding it would add an operand that says
    nothing. This never AUTHORS the marker — an attended session's argv is
    returned unchanged, which is what keeps the overseer daemon its only
    setter.
    """
    marker_value = environ.get(_PLAN_UNATTENDED_ENV_NAME, "")
    if not marker_value:
        return list(reexec_argv)
    separator_index = len(credential_wrapper)
    return [
        *reexec_argv[:separator_index],
        _ENV_COMMAND,
        f"{_PLAN_UNATTENDED_ENV_NAME}={marker_value}",
        *reexec_argv[separator_index:],
    ]


def _self_heal_credentials(*, required: tuple[str, ...] = _REQUIRED_CREDENTIALS) -> None:
    """Decide-and-perform the credential self-heal at the bin chokepoint.

    The pure decision lives in the vendored `livespec_runtime.credentials`;
    this thin performer supplies the live inputs (parsed wrapper, environ,
    interpreter, argv) and carries out the prescribed impure act.
    `required` is the calling wrapper's own secret set (see `bootstrap`).
    """
    # Deferred imports: the vendored tree is on sys.path only AFTER
    # `bootstrap()`'s inserts run.
    from livespec_runtime.credentials import (
        CREDENTIAL_REEXEC_SENTINEL,
        Fail,
        Proceed,
        Reexec,
        decide_credentials,
        wrapper_launch_failure,
    )
    from typing_extensions import assert_never

    credential_wrapper = _read_credential_wrapper()
    decision = decide_credentials(
        required=required,
        credential_wrapper=credential_wrapper,
        environ=os.environ,
        executable=sys.executable,
        argv=sys.argv,
    )
    match decision:
        case Proceed():
            return
        case Fail(message=message):
            _ = sys.stderr.write(message + "\n")
            raise SystemExit(_CREDENTIAL_FAIL_EXIT)
        case Reexec(argv=reexec_argv):
            _ = sys.stderr.write(
                "livespec: required credential env absent; re-invoking under credential_wrapper\n"
            )
            os.environ[CREDENTIAL_REEXEC_SENTINEL] = "1"
            completed = subprocess.run(  # noqa: S603
                _marker_forwarded_argv(
                    reexec_argv=reexec_argv,
                    credential_wrapper=credential_wrapper,
                    environ=os.environ,
                ),
                capture_output=True,
                check=False,
            )
            stdout = completed.stdout or b""
            stderr = completed.stderr or b""
            if stdout:
                _ = sys.stdout.buffer.write(stdout)
                _ = sys.stdout.flush()
            if completed.returncode != 0 and not stdout:
                fail = wrapper_launch_failure(
                    required=required,
                    credential_wrapper=credential_wrapper,
                )
                _ = sys.stderr.write(fail.message + "\n")
            elif stderr:
                _ = sys.stderr.buffer.write(stderr)
                _ = sys.stderr.flush()
            raise SystemExit(completed.returncode)
        case _:
            assert_never(decision)
