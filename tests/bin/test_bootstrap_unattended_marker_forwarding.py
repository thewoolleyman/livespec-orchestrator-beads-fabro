"""The unattended-plan-resume marker survives the credential re-exec.

The overseer daemon sets `LIVESPEC_PLAN_UNATTENDED` on the session it restarts
after a context threshold, and `resume_directive` refuses to raise the picker
only when `is_unattended_session` sees it. But every orchestrator CLI enters
through `bin/_bootstrap.bootstrap()`, whose credential self-heal re-execs the
process through the project's `credential_wrapper` — a `sudo -n` escalation
that forwards `WRAPPER_STAGE` and `OP_ENV_WRAPPER_CACHE_TTL` and nothing else.
A marker set in the OUTER session is therefore invisible to the wrapped
process, so a daemon-triggered resume computes `ask=True` — a plausible wrong
answer, with no error — and parks on a picker nobody is present to answer.

The fix carries the marker as an `env NAME=value` operand INSIDE the wrapper's
own argv, after its `--` separator: the wrapper cannot strip what it is asked
to execute. The two subprocess tests below prove that end to end against a
wrapper DOUBLE that reproduces the scrub — it `unset`s the marker before
exec'ing, exactly as the stage-0 sudo escalation does — so a forwarding that
only worked because the child inherited the parent's environment would fail
them.

Those two tests spawn a real interpreter, which `tests_no_subprocess_spawn`
otherwise steers away from. The spawn is performed by the PRODUCTION re-exec
path under test rather than by the test body, so that check's AST scan does not
see it — no in-process `main()` can stand in for "what does the re-executed
process see?". Both tests therefore scrub `COVERAGE_PROCESS_START` +
`COV_CORE_*` from the environment the child inherits, exactly as an allowlisted
spawn must, and this file is listed in `subprocess_spawn_allowlist` so the
exception is DECLARED rather than merely undetected by that scan.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from livespec_runtime.credentials import CREDENTIAL_REEXEC_SENTINEL, Reexec

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / ".claude-plugin" / "scripts"
_VENDOR_DIR = _SCRIPTS_DIR / "_vendor"
_BIN_DIR = _SCRIPTS_DIR / "bin"
_PACKAGE_DIR = _SCRIPTS_DIR / "livespec_orchestrator_beads_fabro"

_MARKER = "LIVESPEC_PLAN_UNATTENDED"
_WRAPPER_SEPARATOR = "--"
_ENV_COMMAND = "env"
_PLACEHOLDER_SECRET = "test-not-a-real-secret"

# The wrapper double. It reproduces the two behaviours of
# /usr/local/bin/with-livespec-env.sh this regression turns on: it injects the
# tenant secret the self-heal is re-execing to obtain, and it SCRUBS its
# caller's environment of everything the real wrapper's sudo stage does not
# forward. Anything the fix wants to survive must therefore arrive as argv.
_WRAPPER_DOUBLE = f"""#!/bin/sh
[ "$1" = "{_WRAPPER_SEPARATOR}" ] && shift
unset {_MARKER}
export BEADS_DOLT_PASSWORD={_PLACEHOLDER_SECRET}
exec "$@"
"""

# Runs inside the re-executed process. argv[1:3] are the scripts/ and
# scripts/_vendor/ paths (the child is reached through `env` + the wrapper, so
# it cannot rely on the parent's sys.path). It reports what the resume reads:
# whether this process carries the unattended marker, and what
# `resume_directive` decides for an epic whose typed next_action is kind
# `impl` with a non-empty ref.
_CHILD_PROBE = """
import json
import os
import sys

for entry in sys.argv[1:3]:
    if entry not in sys.path:
        sys.path.insert(0, entry)

from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import resume_directive
from livespec_orchestrator_beads_fabro.commands._plan_timeline import is_unattended_session
from livespec_orchestrator_beads_fabro.types import StoreConfig

config = StoreConfig(
    tenant="livespec-impl-beads",
    prefix="bd-ib",
    server_user="livespec-impl-beads",
    database="livespec-impl-beads",
    bd_path="bd",
    fake=True,
)
reset_fake_singleton()
_ = make_beads_client(config=config).create_issue(
    draft=IssueDraft(
        issue_id="bd-ib-epic",
        issue_type="epic",
        title="plan",
        description="plan",
        assignee=None,
        created_at="2026-09-07T00:00:00Z",
        metadata={
            "next_action": {
                "kind": "impl",
                "ref": "bd-ib-p02l",
                "text": "Forward the unattended marker through the credential re-exec.",
            }
        },
    )
)
unattended = is_unattended_session(env=os.environ)
directive = resume_directive(config=config, epic_id="bd-ib-epic", unattended=unattended)
_ = sys.stdout.write(
    json.dumps(
        {
            "unattended": unattended,
            "ask": directive.ask,
            "next_action": directive.next_action,
        }
    )
)
"""


def _import_bootstrap() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_bootstrap", None)
    return importlib.import_module("_bootstrap")


def _write_wrapper_double(*, cwd: Path) -> Path:
    wrapper = cwd / "with-livespec-env-double.sh"
    _ = wrapper.write_text(_WRAPPER_DOUBLE, encoding="utf-8")
    wrapper.chmod(0o755)
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"credential_wrapper": [str(wrapper), _WRAPPER_SEPARATOR]}),
        encoding="utf-8",
    )
    return wrapper


def _arrange_reexec(*, monkeypatch: pytest.MonkeyPatch, cwd: Path) -> None:
    """Put the process one `bootstrap()` call away from a real re-exec.

    The tenant secret is absent and no `.beads/config.yaml` exists (so the
    self-heal fails closed into requiring it), the re-exec sentinel is clear,
    and the coverage subprocess hooks are scrubbed so the spawned child does
    not self-instrument.
    """
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    monkeypatch.delenv("COVERAGE_PROCESS_START", raising=False)
    for name in [key for key in os.environ if key.startswith("COV_CORE_")]:
        monkeypatch.delenv(name, raising=False)
    child = cwd / "resume_probe.py"
    _ = child.write_text(_CHILD_PROBE, encoding="utf-8")
    _write_wrapper_double(cwd=cwd)
    monkeypatch.setattr(sys, "argv", [str(child), str(_SCRIPTS_DIR), str(_VENDOR_DIR)])


def test_reexecuted_process_sees_the_marker_and_resumes_without_asking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point: an unattended outer session stays unattended inside."""
    _arrange_reexec(monkeypatch=monkeypatch, cwd=tmp_path)
    monkeypatch.setenv(_MARKER, "1")
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module.bootstrap()
    captured = capsys.readouterr()
    assert excinfo.value.code == 0, captured.err
    report = json.loads(captured.out)
    assert report["unattended"] is True
    assert report["ask"] is False
    assert report["next_action"] == "impl:bd-ib-p02l"


def test_reexecuted_process_stays_attended_when_the_outer_session_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An operator-launched session forwards no marker and keeps its picker."""
    _arrange_reexec(monkeypatch=monkeypatch, cwd=tmp_path)
    monkeypatch.delenv(_MARKER, raising=False)
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module.bootstrap()
    captured = capsys.readouterr()
    assert excinfo.value.code == 0, captured.err
    report = json.loads(captured.out)
    assert report["unattended"] is False
    assert report["ask"] is True


def _record_reexec_argv(*, monkeypatch: pytest.MonkeyPatch, cwd: Path) -> list[str]:
    """Drive the Reexec arm with a stubbed spawn and return the argv it built."""
    monkeypatch.chdir(cwd)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    _ = (cwd / ".livespec.jsonc").write_text(
        json.dumps({"credential_wrapper": ["/usr/local/bin/with-livespec-env.sh", "--"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "livespec_runtime.credentials.decide_credentials",
        lambda **_kwargs: Reexec(
            argv=("/usr/local/bin/with-livespec-env.sh", "--", "/usr/bin/python3", "next.py")
        ),
    )
    recorded: list[str] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        recorded.extend(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit):
        bootstrap_module._self_heal_credentials()  # noqa: SLF001
    return recorded


def test_forwarded_argv_places_the_env_operand_after_the_wrapper_separator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The operand lands INSIDE the wrapper's own argv, never before it.

    Before the `--` it would be an argument TO the wrapper; after it, it is the
    command the wrapper execs, which is the only position the sudo stage cannot
    strip.
    """
    monkeypatch.setenv(_MARKER, "1")
    assert _record_reexec_argv(monkeypatch=monkeypatch, cwd=tmp_path) == [
        "/usr/local/bin/with-livespec-env.sh",
        _WRAPPER_SEPARATOR,
        _ENV_COMMAND,
        f"{_MARKER}=1",
        "/usr/bin/python3",
        "next.py",
    ]


def test_forwarded_argv_preserves_the_operator_written_marker_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`is_unattended_session` accepts four truthy spellings; forward the value."""
    monkeypatch.setenv(_MARKER, "true")
    assert f"{_MARKER}=true" in _record_reexec_argv(monkeypatch=monkeypatch, cwd=tmp_path)


def test_forwarded_argv_is_unchanged_for_an_attended_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(_MARKER, raising=False)
    assert _record_reexec_argv(monkeypatch=monkeypatch, cwd=tmp_path) == [
        "/usr/local/bin/with-livespec-env.sh",
        _WRAPPER_SEPARATOR,
        "/usr/bin/python3",
        "next.py",
    ]


def test_forwarded_argv_is_unchanged_when_the_marker_is_set_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty marker is not unattended, so forwarding it would say nothing."""
    monkeypatch.setenv(_MARKER, "")
    assert _ENV_COMMAND not in _record_reexec_argv(monkeypatch=monkeypatch, cwd=tmp_path)


def test_bootstrap_marker_name_matches_the_readers_constant() -> None:
    """One spelling of the marker, so the forwarder and the reader cannot drift.

    `_bootstrap` re-declares the name rather than importing it: the self-heal
    runs before the package has ever been imported, and pulling the store layer
    in at that point would make a credential failure depend on it. This guard
    is what keeps the re-declaration honest.
    """
    from livespec_orchestrator_beads_fabro.commands._plan_timeline import UNATTENDED_ENV_VAR

    bootstrap_module = _import_bootstrap()
    assert getattr(bootstrap_module, "_PLAN_UNATTENDED_ENV_NAME", None) == UNATTENDED_ENV_VAR
    assert UNATTENDED_ENV_VAR == _MARKER


_ENV_MUTATING_CALLS = frozenset({"putenv", "setenv", "setdefault", "update"})
_MARKER_TOKENS = (_MARKER, "UNATTENDED_ENV_VAR", "_PLAN_UNATTENDED_ENV_NAME")

# The positive control for the scan below, carrying one of each shape it
# claims to catch. An absence is evidence only when the instrument could have
# returned a hit, and a scan that quietly stops matching reports a clean tree.
_SETTER_CONTROL = """
import os

os.environ["LIVESPEC_PLAN_UNATTENDED"] = "1"
os.environ.update({UNATTENDED_ENV_VAR: "1"})
os.putenv(_PLAN_UNATTENDED_ENV_NAME, "1")
"""


def _env_mutating_nodes(*, tree: ast.AST) -> list[ast.AST]:
    """Statements that write into an environment mapping, of either shape."""
    nodes: list[ast.AST] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Subscript) for target in node.targets)
        ) or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _ENV_MUTATING_CALLS
        ):
            nodes.append(node)
    return nodes


def _marker_setters(*, source: str) -> list[str]:
    """Environment writes in `source` that name the unattended marker."""
    found: list[str] = []
    for node in _env_mutating_nodes(tree=ast.parse(source)):
        segment = ast.get_source_segment(source, node) or ""
        if any(token in segment for token in _MARKER_TOKENS):
            found.append(segment)
    return found


def test_the_package_adds_no_new_setter_of_the_unattended_marker() -> None:
    """`prose/plan.md` says "Nothing else sets it" — keep that sentence true.

    Forwarding an existing value as an argv operand is transport, not
    authorship. Writing the marker INTO an environment mapping anywhere in the
    plugin would make this package a second source of unattendedness beside the
    overseer daemon, and the prose a lie.
    """
    assert len(_marker_setters(source=_SETTER_CONTROL)) == 3
    offenders: list[str] = []
    for source_file in sorted([*_BIN_DIR.rglob("*.py"), *_PACKAGE_DIR.rglob("*.py")]):
        source = source_file.read_text(encoding="utf-8")
        offenders.extend(
            f"{source_file.relative_to(_REPO_ROOT)}: {segment}"
            for segment in _marker_setters(source=source)
        )
    assert offenders == []
