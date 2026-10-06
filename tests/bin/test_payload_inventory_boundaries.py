"""The pre-copy inventory must not break refusal, cleanup or fail-closed.

Cycle 14 moved provisioning onto a pre-copy digest inventory. That fixed the
two coherence cases it was written for, and introduced two boundary faults of
its own in the NEW code. Both were measured against the cycle-14 build on
2026-10-06, and both are regressions against contracts this module had already
established rather than new policy.

ONE — the inventory step sat OUTSIDE the cleanup boundary. `_retained_root`
allocates the holder with `mkdtemp` and then runs the whole provision inside a
`try/finally` that removes the holder unless the payload was published; the
established contract, from the cycle that added it, is that a provision which
is INTERRUPTED leaves no adoptable tree, not merely one that errors. The new
`source_inventory` call landed between the `mkdtemp` and that `try`, so an
interrupt or any non-`OSError` fault inside it leaked the directory. Measured:
a `KeyboardInterrupt` raised during the inventory left
`livespec-orchestrator-beads-fabro-payload-7.1.0-oat7bhsm` standing in the
private temporary root. Once this process is gone nothing can tell that
half-built holder from a finished payload, which is the exact hazard the
`finally` exists for.

TWO — the unreadable sentinel compared EQUAL to itself. `_digest` returns the
same literal string for any file it cannot read, on BOTH sides of the
comparison, and `inventory_gaps` accepted a match. So a member unreadable when
the inventory was taken, whose copy is also unreadable, passed as faithful
while NEITHER set of bytes had ever been established. Measured with a seam
denying reads on one member in both trees: the inventory recorded
`unreadable`, the copied file existed and was unreadable, their ACTUAL bytes
differed, and `inventory_gaps` returned `()`. Two unknowns are not a match, and
a gauge that passes when it cannot observe its input is the fail-open shape
this repository treats as worse than an honest refusal.

A note on aiming, because the first probe for the second fault could not have
found it: pointing the comparison at a copy path that does not EXIST trips
`not copied.is_file()` and reports a gap before `_digest` is ever called, so it
returns the right answer for the wrong reason and hides the branch. The copy
has to exist and be unreadable.

Scope is the refusal/cleanup/fail-closed semantics of cycle 14's own new code.
Not an integrity or security addition: an unreadable member is REFUSED here
because its bytes are unknown, which is the same reason an unusable release
manifest already refuses.

The accepted cycle-14 regression at bytes `f219ca14…` is deliberately left
untouched; these cases live in their own file.
"""

import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_RELEASE = "7.1.0"
_DEFERRED_NAME = "_deferred.py"
_DEFERRED = f"scripts/livespec_orchestrator_beads_fabro/commands/{_DEFERRED_NAME}"


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _install(*, root: Path) -> Path:
    for relative in (
        "scripts/bin",
        "scripts/livespec_orchestrator_beads_fabro/commands",
        "scripts/_vendor/livespec_runtime",
        ".fabro/workflows/implement-work-item",
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
        _ = (root / relative).write_text("x", encoding="utf-8")
    _ = (root / _DEFERRED).write_text("ORIGINAL", encoding="utf-8")
    _ = (root / "plugin.json").write_text(json.dumps({"version": _RELEASE}), encoding="utf-8")
    return root


def _private_tempdir(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    return temp_root


@pytest.mark.parametrize(
    ("fault", "raised"),
    [
        pytest.param(KeyboardInterrupt, KeyboardInterrupt, id="interrupt"),
        pytest.param(MemoryError, MemoryError, id="bug-class-error"),
    ],
)
def test_a_fault_in_the_inventory_step_leaves_no_adoptable_holder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: type[BaseException],
    raised: type[BaseException],
) -> None:
    """The interruption-cleanup contract covers the inventory step too.

    An interrupt arrives as `KeyboardInterrupt` and a bug-class fault as a
    built-in error; neither is an `OSError`, so neither is caught by the
    provisioning handlers. Both must still leave nothing a later invocation
    could adopt.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "0123abc")

    def failing_inventory(**_kwargs: Any) -> dict[str, str]:
        raise fault

    monkeypatch.setattr(payload, "source_inventory", failing_inventory)

    with pytest.raises(raised):
        _ = payload.retain_payload(source_root=source_root, environ={})

    survivors = sorted(entry.name for entry in temp_root.iterdir())
    assert survivors == [], (
        "a provision faulting in the inventory step left a private directory "
        "behind; once this process is gone nothing can tell that half-built "
        f"holder from a finished payload: {survivors}"
    )


def test_a_member_unreadable_on_both_sides_is_refused_rather_than_matched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two unknowns are not a match.

    The member is denied in BOTH trees, so the inventory records the sentinel
    and the copy digests to the same sentinel. Its real bytes are never
    established, so the provision must refuse instead of publishing.
    """
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "0123abc")

    real_open = Path.open

    def denying_open(self: Path, *args: Any, **kwargs: Any):
        if self.name == _DEFERRED_NAME:
            raise OSError(5, "simulated I/O error")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denying_open)
    provisioned = payload.retain_payload(source_root=source_root, environ={})

    assert isinstance(provisioned, payload.PayloadRefusal), (
        "a member whose bytes were never established on either side was "
        f"published as a faithful copy: {provisioned}"
    )
    assert (
        _DEFERRED in provisioned.message
    ), f"the refusal does not name the unestablished member: {provisioned.message}"


def test_a_readable_complete_source_still_provisions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control: neither fix may turn an ordinary provision into a refusal.

    Without this, both cases above are satisfied by a launcher that refuses
    everything or cleans up unconditionally, and the suite could not tell.
    """
    payload = _import_payload()
    temp_root = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_root = _install(root=tmp_path / "cache" / "0123abc")

    provisioned = payload.retain_payload(source_root=source_root, environ={})

    assert not isinstance(
        provisioned, payload.PayloadRefusal
    ), f"an ordinary complete source was refused: {provisioned}"
    assert provisioned.holder is not None, "a retained payload must own its holder"
    assert (provisioned.root / _DEFERRED).read_text(encoding="utf-8") == "ORIGINAL"
    assert len(sorted(temp_root.iterdir())) == 1, "the provision left more than its own holder"

    payload.release_payload(payload=provisioned)
    assert sorted(temp_root.iterdir()) == [], "the creator's release left its holder behind"
