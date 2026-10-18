"""This repository's opt-in to the delegated pre-push gate, and the branch its gate takes.

The delegation CONTRACT is livespec-dev-tooling's — its
`SPECIFICATION/contracts.md` section "Delegated pre-push gate", implemented by
the shared client `livespec_dev_tooling.gate_remote_delegate` this repository
already pins. What lives HERE is the wiring that consumes it: the switch in this
repository's own `[tool.livespec_dev_tooling]` block, and the branch
`dev-tooling/just-check-pre-push.sh` takes on the answer. Those two files are
the whole opt-in, and nothing else in this suite exercises either, so this is
where a regression in them is caught.

WHY IT IS WORTH OPTING IN. A push from the VPS runs the full `just check`
aggregate on the VPS — measured at about 17 minutes on this repository. The
delegated gate runs that same aggregate as a Job in the self-hosted k3s
cluster's `gates` namespace and gates the push on its verdict instead. This
repository's default suite has already run green there (gate Job
`gate-livespec-orchestrator-beads-fabro-1c5e8de33c1f`, 92 targets), so no
`gate_check_suite` declaration is wanted: the client's own documented
fall-through is the sequence this repository's pre-push already runs.

DELEGATION IS SELECTED BY TWO FACTS, AND ONLY ONE OF THEM IS IN THIS TREE. The
switch travels with the code and names no host; whether the pushing user can
read the gates kubeconfig is a property of the HOST. An opted-in repository on
a host with no credential therefore gates LOCALLY and says so, rather than
failing closed on a cluster it cannot reach — which is exactly the shape every
Fabro sandbox and every laptop is in.

WHY THE HOST HALF IS DRIVEN THROUGH `GATES_KUBECONFIG` AND NOT READ OFF THIS
HOST. The credential's real path is `/etc/ci-runner/gates.kubeconfig`, which is
absent in a sandbox and PRESENT on the VPS. A test that asserted on whatever
this host happens to hold would therefore assert opposite things in the two
places this suite runs, and would pass in the sandbox for the very reason it
would fail on the VPS. `GATES_KUBECONFIG` is not a back door around that: it is
the single override `livespec_dev_tooling.gate_credential` and the shipped
`with-gates-kubeconfig` wrapper BOTH resolve the credential from, so a test that
sets it reads the same switch the real host reads, with the host's own answer
substituted for one the test can state. Both answers are asserted, so neither
arm is assumed.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_dev_tooling.config import load_delegated_gate, load_gate_check_suite
from livespec_dev_tooling.gate_remote_delegate import GATED_LOCALLY, main

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-check-pre-push.sh"

# The one override both halves of the shared client resolve the credential from.
_GATES_KUBECONFIG_ENV = "GATES_KUBECONFIG"

_ENABLED_PROBE = "gate_remote_delegate enabled"
_DELEGATED_RUN = "gate_remote_delegate run"
_GREEN_TOKEN_PROBE = "green_token check"
_AGGREGATE = "just check-skipping check-codex-skill-picker"

_LIVE_OID = "b3d4f1a90c7e25486fd1c0b8a7e6554321098765"
_ZERO_OID = "0" * 40

# One ordinary publish: a single ref CREATE, which is the only input shape that
# reaches past the deletion-only skip to the branch under test here. The field
# order is git's own — `<local ref> <local object id> <remote ref> <remote
# object id>`.
_PUBLISH_REFS = f"refs/heads/feature {_LIVE_OID} refs/heads/feature {_ZERO_OID}\n"

# The stub `uv`. The green-token probe always MISSES, which is what keeps the
# rest of the path observable: a match exits the script before the delegated
# branch is reachable at all. Each delegated subcommand then answers with the
# exit code its own case exported.
_UV_STUB = """#!/usr/bin/env bash
printf "uv %s\\n" "$*" >> "${STUB_LOG}"
case "$*" in
    *"gate_remote_delegate enabled") exit "${STUB_ENABLED_EXIT}" ;;
    *"gate_remote_delegate run") exit "${STUB_RUN_EXIT}" ;;
esac
exit 1
"""
_JUST_STUB = '#!/usr/bin/env bash\nprintf "just %s\\n" "$*" >> "${STUB_LOG}"\nexit 0\n'


def _run_delegate_probe(
    *, kubeconfig: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    """Run the SHARED client's `enabled` probe against this repository, for one host answer.

    Invoked IN PROCESS rather than spawned: a test-spawned Python child
    self-instruments under `pytest --cov` and races the parallel dispatcher's
    concurrent coverage runs, which is why this repository bans the spawn
    outright. `main` reads the repository from `Path.cwd()` and the subcommand
    from `sys.argv`, so both are set here and nothing else about the call
    differs from the one a pre-push hook makes.
    """
    monkeypatch.setenv(_GATES_KUBECONFIG_ENV, str(kubeconfig))
    monkeypatch.chdir(_REPO_ROOT)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])
    returncode = main()
    return returncode, capsys.readouterr().err


def _run_pre_push(*, tmp_path: Path, enabled_exit: int, run_exit: int) -> tuple[int, list[str]]:
    """Run the shipped gate script on an ordinary publish, for one delegated-client answer.

    The script is executed as the SHIPPED BYTES, with `uv` and `just` replaced
    by stubs on `PATH` that record their argv. What the script INVOKES is the
    only observable that can tell a delegated gate from a local one: both
    complete, and a completed push looks identical afterwards whichever gated
    it. The real client is exercised by the cases above, so nothing here rests
    on the stub being a faithful one.

    Returns the script's exit code and every command it invoked, in order.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "invocations.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(log),
            "STUB_ENABLED_EXIT": str(enabled_exit),
            "STUB_RUN_EXIT": str(run_exit),
        }
    )
    completed = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=str(tmp_path),
        env=env,
        input=_PUBLISH_REFS,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return completed.returncode, invoked


def _invocation_index(*, invoked: list[str], needle: str) -> int:
    """Position of the first invocation carrying `needle`, or -1 when there is none."""
    for position, line in enumerate(invoked):
        if needle in line:
            return position
    return -1


def test_this_repository_declares_the_delegated_gate_switch() -> None:
    """The opt-in is one key in this repository's own dev-tooling block, and nothing else."""
    declared = load_delegated_gate(repo_root=_REPO_ROOT)

    assert declared is True, (
        "`delegated_gate = true` must stand in the [tool.livespec_dev_tooling] block of "
        "pyproject.toml: the shared client answers yes only to a literal true, and every "
        "other shape — absent, false, wrong type — keeps the full local aggregate this "
        f"repository ran before opting in; declared={declared!r}"
    )


def test_this_repository_declares_no_gate_suite_and_takes_the_shared_fall_through() -> None:
    """No declaration is the deliberate choice, not an omission.

    A declaration here would gate the tree on recipes chosen in this file rather
    than on the ones the repository's own pre-push actually runs — which is how
    a consumer's gate goes red on a green tree. The client's fall-through is
    that sequence, and it has already passed on the cluster for this repository.
    """
    declared = load_gate_check_suite(repo_root=_REPO_ROOT)

    assert declared is None, (
        "this repository must declare NO gate suite, so the delegated gate runs the "
        "shared pre-push sequence its local fall-through runs; "
        f"declared={declared!r}"
    )


def test_a_host_without_the_gates_credential_gates_locally_and_narrates_it(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The Fabro-sandbox and laptop case: switched on, no credential, so gate HERE — out loud.

    The narration is the assertion, not a courtesy. A locally-gated push and a
    cluster-gated one are indistinguishable once either has completed, so an
    opted-in repository that quietly gated somewhere else is the one outcome an
    operator cannot reconstruct afterwards.
    """
    absent = tmp_path / "no-such-dir" / "gates.kubeconfig"

    returncode, narration = _run_delegate_probe(
        kubeconfig=absent, monkeypatch=monkeypatch, capsys=capsys
    )

    assert returncode != 0, (
        "a host that cannot read the gates kubeconfig must NOT delegate, because the "
        "cluster is unreachable there and a delegation that reaches no verdict refuses "
        f"the push; narration={narration!r}"
    )
    assert GATED_LOCALLY in narration, (
        "the probe must say that the delegated gate is switched on for this repository "
        "but this host cannot read the gates kubeconfig, so the push gates locally; "
        f"narration={narration!r}"
    )


def test_a_host_holding_the_gates_credential_selects_delegation(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The positive control, without which the case above proves only that nothing is on.

    A repository that never opted in ALSO fails the probe from a credential-less
    host, and fails it silently. Only this arm separates "switched on, host
    ineligible" from "switched off": it holds the host half constant at eligible
    and reads the switch alone.
    """
    present = tmp_path / "gates.kubeconfig"
    _ = present.write_text("apiVersion: v1\n", encoding="utf-8")

    returncode, narration = _run_delegate_probe(
        kubeconfig=present, monkeypatch=monkeypatch, capsys=capsys
    )

    assert returncode == 0, (
        "with a readable gates kubeconfig the only remaining question is this "
        "repository's own switch, so a non-zero answer here means the opt-in is not "
        f"being read; narration={narration!r}"
    )
    assert GATED_LOCALLY not in narration, (
        "an eligible host delegates, so the local-gating narration must be silent — it "
        f"speaks in exactly one case, and this is not it; narration={narration!r}"
    )


def test_the_gate_consults_the_client_between_the_token_and_the_local_aggregate(
    *, tmp_path: Path
) -> None:
    """ORDER is the assertion: after the green-token skip, before the local fall-through.

    Ahead of the token probe the delegated branch would re-gate a tree already
    proven green, and a delegated pass writes the SAME token through the SAME
    CLI a local aggregate does, so that skip is sound for either gate. Behind
    the aggregate the branch would be unreachable. The position is what makes
    the switch replace the FALL-THROUGH and nothing else.
    """
    code, invoked = _run_pre_push(tmp_path=tmp_path, enabled_exit=1, run_exit=0)

    assert code == 0, f"invoked={invoked}"
    token_at = _invocation_index(invoked=invoked, needle=_GREEN_TOKEN_PROBE)
    probe_at = _invocation_index(invoked=invoked, needle=_ENABLED_PROBE)
    aggregate_at = _invocation_index(invoked=invoked, needle=_AGGREGATE)
    assert token_at >= 0, f"the green-token probe must still come first; invoked={invoked}"
    assert (
        probe_at >= 0
    ), f"the gate must ask the shared client whether THIS push delegates; invoked={invoked}"
    assert aggregate_at >= 0, (
        f"an ineligible host — every Fabro sandbox, every laptop — must still reach the "
        f"full local aggregate, which is the whole reason the probe may answer no; "
        f"invoked={invoked}"
    )
    assert token_at < probe_at < aggregate_at, (
        f"the delegated probe belongs between the green-token skip and the local "
        f"aggregate; invoked={invoked}"
    )


def test_a_selected_delegation_gates_on_the_cluster_instead_of_the_local_aggregate(
    *, tmp_path: Path
) -> None:
    """When the probe answers yes, the delegated run REPLACES the fall-through."""
    code, invoked = _run_pre_push(tmp_path=tmp_path, enabled_exit=0, run_exit=0)

    assert code == 0, f"invoked={invoked}"
    assert (
        _invocation_index(invoked=invoked, needle=_DELEGATED_RUN) >= 0
    ), f"a selected delegation must gate HEAD on the cluster; invoked={invoked}"
    assert _invocation_index(invoked=invoked, needle=_AGGREGATE) < 0, (
        f"running the local aggregate as well would spend on the VPS exactly the time "
        f"delegating was meant to save, and would reduce the cluster's verdict to an "
        f"advisory one; invoked={invoked}"
    )


def test_a_delegated_run_that_reaches_no_verdict_refuses_the_push(*, tmp_path: Path) -> None:
    """FAIL-CLOSED, and the `exec` is what makes it so.

    "We could not gate this" must never quietly become "we gated it some other
    way". Once delegation is selected the delegated run is the LAST branch: its
    exit status is the gate's, and a lost cluster, a Job that never rendered and
    a red tree all refuse the push rather than falling through to the aggregate
    below — which would publish on a second opinion the contract does not grant.
    """
    code, invoked = _run_pre_push(tmp_path=tmp_path, enabled_exit=0, run_exit=1)

    assert code != 0, f"a delegated run that did not pass must refuse the push; invoked={invoked}"
    assert _invocation_index(invoked=invoked, needle=_AGGREGATE) < 0, f"invoked={invoked}"
