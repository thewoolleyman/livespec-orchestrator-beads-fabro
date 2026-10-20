"""A cache build's `.in_use` leases are session state, not release content.

Measured 2026-10-19 at about 15:56Z on cache build 29d454be7a46 (v0.222.0),
while ten seats on the host were restarting concurrently and each leasing that
same build. `context.py bd-ib-qieqc6 --json` exited 3 reporting that the copy
of the plugin installation "did not land complete" because `.in_use/661440`
"is missing or short, so this invocation would be running a DIFFERENT release
from the one installed". PID 661440 was not running moments later, and an
immediate retry of the identical command exited 0.

Nothing was wrong with that payload. `.in_use/` is the plugin cache's LEASE
directory: it holds one file per session bound to the build, named by the
holding process id and carrying that pid with the holder's start time
(`.ai/plugin-cache-lease-and-rebind.md` records it as the binding instrument).
Those files are per-session state owned by the harness and by OTHER sessions,
which create and remove them at any moment — so they are the one part of the
tree guaranteed NOT to be stable across a copy, and the pre-copy inventory
cycle 14 introduced (`test_payload_source_copy_coherence.py`) swept them in
alongside the release.

The race reaches the refusal from both directions and the refusal cannot tell
either from a defect. A lease REMOVED between the inventory and the copy reads
as a member the copy lost — the literal `bd-ib-3ftj` shape the fidelity grade
exists to catch — while being nothing but a sibling session exiting. A lease
CREATED while provisioning is under way reads as a member the copy omitted.
Either way an unrelated invocation refuses, claims nothing and starts no
factory run, over a file no code in this payload will ever read.

So leases are dropped from the inventory and from the copy, exactly as
`__pycache__` already is — through the one shared `IGNORED_NAMES` tuple,
because `_payload`'s `copytree` and the fidelity walk must agree on the drop
set or the copy omits something the comparison still demands.

SCOPE, stated because the weaker reading is the dangerous one: this drops the
LEASE DIRECTORY and nothing else. A release file anywhere outside it that is
missing from, or differs in, the copy must still refuse and must still name
itself. The third case below is that control, and without it this file would be
satisfied by a launcher that stopped grading copies at all.
"""

import importlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_RELEASE = "7.1.0"
# The lease directory as the Claude Code plugin cache names it, and one lease
# the installation already carries when provisioning starts — the incident's
# own shape, a file named for a holding pid.
_LEASE_DIRECTORY = ".in_use"
_HELD_LEASE = f"{_LEASE_DIRECTORY}/661440"
_ARRIVING_LEASE = f"{_LEASE_DIRECTORY}/661441"
_LEASE_BYTES = "661440 1760889360"
# A non-required, deferred module: a release member no list of required paths
# names, which is why it is the right subject for the control.
_DEFERRED = "scripts/livespec_orchestrator_beads_fabro/commands/_deferred.py"
_ORIGINAL_BYTES = "ORIGINAL"
_WRONG_SAME_LENGTH = "WRONGXXX"


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _install(*, root: Path) -> Path:
    """A complete harness-managed installation that already holds one lease."""
    for relative in (
        "scripts/bin",
        "scripts/livespec_orchestrator_beads_fabro/commands",
        "scripts/_vendor/livespec_runtime",
        ".fabro/workflows/implement-work-item",
        _LEASE_DIRECTORY,
    ):
        (root / relative).mkdir(parents=True)
    for relative in (
        "scripts/bin/_bootstrap.py",
        "scripts/bin/_payload.py",
        "scripts/livespec_orchestrator_beads_fabro/__init__.py",
        "scripts/livespec_orchestrator_beads_fabro/commands/__init__.py",
        "scripts/_vendor/livespec_runtime/__init__.py",
        ".fabro/workflows/implement-work-item/workflow.toml",
    ):
        _ = (root / relative).write_text("", encoding="utf-8")
    _ = (root / _DEFERRED).write_text(_ORIGINAL_BYTES, encoding="utf-8")
    _ = (root / _HELD_LEASE).write_text(_LEASE_BYTES, encoding="utf-8")
    _ = (root / "plugin.json").write_text(json.dumps({"version": _RELEASE}), encoding="utf-8")
    return root


def _provision_with_seam(
    *,
    payload: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutate,
):
    """Provision once, applying `mutate(source, copy)` the moment the copy lands.

    ONE narrow control on the product's own seam, for the reason
    `test_payload_source_copy_coherence.py` gives for the same technique: a
    wall-clock race between this invocation and a sibling session's lease churn
    would pass or fail on machine load, so the interleaving is made
    deterministic instead.

    The DEPTH counter is load-bearing, exactly as it is there. `copytree`
    recurses through the patched name and the inner calls RETURN FIRST, so a
    "first call wins" guard applies the mutation to a subdirectory and the
    fixture silently measures nothing. Entry depth 1 is the whole-tree
    provision.
    """
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    source_root = _install(root=tmp_path / "cache" / "29d454be7a46")

    real_copytree = shutil.copytree
    depth = {"n": 0}

    def seam(source, destination, *args: Any, **kwargs: Any):
        depth["n"] += 1
        outermost = depth["n"] == 1
        try:
            result = real_copytree(source, destination, *args, **kwargs)
        finally:
            depth["n"] -= 1
        if outermost:
            mutate(Path(source), Path(destination))
        return result

    monkeypatch.setattr(payload.shutil, "copytree", seam)
    return source_root, payload.retain_payload(source_root=source_root, environ={})


def test_a_lease_released_between_the_inventory_and_the_copy_still_provisions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The measured incident: a sibling session's lease vanishing mid-provision.

    The holder exits, so the lease is gone from the copy AND from the
    installation — which is precisely a member the inventory recorded and the
    copy cannot reproduce. Session state is not release content, so this
    invocation must run on the payload it provisioned.
    """
    payload = _import_payload()

    def release_lease(source: Path, copy: Path) -> None:
        # `missing_ok` on the COPY side, because whether the copy carries the
        # lease at all is exactly what this change decides: once leases are
        # dropped from the copy there is nothing there to remove, and a fixture
        # that insisted on removing it would raise inside `copytree` and be
        # reported as a failed copy — a refusal the fixture invented rather
        # than the one under test. The INSTALLATION side is unconditional: the
        # holder exiting is the premise of the case.
        (copy / _HELD_LEASE).unlink(missing_ok=True)
        (source / _HELD_LEASE).unlink()

    _source, provisioned = _provision_with_seam(
        payload=payload, monkeypatch=monkeypatch, tmp_path=tmp_path, mutate=release_lease
    )

    assert not isinstance(provisioned, payload.PayloadRefusal), (
        "another session releasing its lease mid-provision refused an unrelated "
        f"invocation, which claimed nothing and started no factory run: {provisioned}"
    )
    assert (provisioned.root / _DEFERRED).read_text(
        encoding="utf-8"
    ) == _ORIGINAL_BYTES, "the provisioned payload lost the release"


def test_a_lease_arriving_during_provisioning_is_neither_a_gap_nor_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The mirror direction: a sibling session binding the build mid-provision.

    `payload_fidelity_gaps` is the published source-versus-copy primitive, and
    it walks the installation as it NOW stands — so an arriving lease is a
    member the copy does not carry. It must not be reported, and the payload
    must not be required to hold it.
    """
    payload = _import_payload()

    def acquire_lease(source: Path, _copy: Path) -> None:
        _ = (source / _ARRIVING_LEASE).write_text("661441 1760889377", encoding="utf-8")

    source_root, provisioned = _provision_with_seam(
        payload=payload, monkeypatch=monkeypatch, tmp_path=tmp_path, mutate=acquire_lease
    )

    assert not isinstance(
        provisioned, payload.PayloadRefusal
    ), f"a lease arriving during provisioning refused the invocation: {provisioned}"
    gaps = payload.payload_fidelity_gaps(source_root=source_root, payload_root=provisioned.root)
    assert not [gap for gap in gaps if gap.startswith(f"{_LEASE_DIRECTORY}/")], (
        "a lease another session took while provisioning was under way is "
        f"reported as a fidelity gap in the release: {gaps}"
    )
    assert not (
        provisioned.root / _ARRIVING_LEASE
    ).exists(), "the payload is required to carry another session's lease"


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        pytest.param(
            "missing",
            lambda source, copy: ((copy / _DEFERRED).unlink(), (source / _DEFERRED).unlink()),
            id="missing-from-the-copy",
        ),
        pytest.param(
            "divergent",
            lambda _source, copy: (
                (copy / _DEFERRED).write_text(_WRONG_SAME_LENGTH, encoding="utf-8"),
            ),
            id="differs-in-the-copy",
        ),
    ],
)
def test_a_release_file_outside_the_lease_directory_still_refuses_and_names_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, label: str, mutate
) -> None:
    """THE CONTROL, and the reason this file cannot drop more than the leases.

    Both arms are the coherence cases cycle 14 was written for: a member the
    copy lost while the installation lost it too (invisible to a live-source
    walk), and a member copied with WRONG BYTES at the SAME LENGTH (invisible
    to size equality). Narrowing the drop set to the lease directory must leave
    both refusing, and must leave the refusal naming the file — otherwise this
    file is satisfied by a launcher that stopped grading copies at all.
    """
    payload = _import_payload()

    _source, provisioned = _provision_with_seam(
        payload=payload, monkeypatch=monkeypatch, tmp_path=tmp_path, mutate=mutate
    )

    assert isinstance(provisioned, payload.PayloadRefusal), (
        f"a payload whose release member is {label} was published as the same "
        f"release, so a deferred import will fail at the far end of a dispatch: "
        f"{provisioned}"
    )
    assert (
        _DEFERRED in provisioned.message
    ), f"the refusal does not name the {label} member: {provisioned.message}"
