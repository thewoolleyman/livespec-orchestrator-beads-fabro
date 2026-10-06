"""The retained payload must be the release as it stood when it was COPIED.

Work-item `bd-ib-mtuqxb`'s second assertion requires each concurrent
invocation to use "their own COMPLETE release for code and assets". The
provisioning path graded that with a post-copy walk of the SOURCE comparing
SIZES, and two concrete cases get through it.

WHAT THIS DOES NOT CLAIM, stated first because the obvious stronger rule is
wrong. A complete, coherent payload whose SOURCE later changes is a SUCCESS,
not a defect — that is the whole point of copying the release aside. This file
must never demand that retained bytes equal a source which legitimately moved
on afterwards, and the third case below is the control that holds it to that:
a coherent copy whose source is mutated after the copy must still provision,
carrying its ORIGINAL bytes.

The two real faults are at the PROVISIONING BOUNDARY — the copy itself is
wrong as produced — and both were measured against the unmodified launcher on
2026-10-06 through a seam on the product's own `copytree`:

- a member present in the source when the copy STARTED is omitted from the
  copy, and is gone from the source before the post-copy walk runs. The walk
  enumerates the source as it now stands, so the omitted member is invisible
  to it. Measured: provisioning SUCCEEDED and the retained payload was missing
  the member — the literal `bd-ib-3ftj` shape, a deferred module absent hours
  into a run;
- a file is copied with WRONG BYTES at the SAME LENGTH. Size equality cannot
  see it. Measured: provisioning SUCCEEDED with the retained file holding
  `WRONGXXX` while its source held `ORIGINAL`.

An earlier disposable probe for these cases was INVALID and is recorded here
so the mistake is not repeated: it mutated the source AFTER a clean copy and
then reported the surviving original as an undetected gap. That is the success
case, not a defect. A valid demonstration has to make the COPY defective.

The remedy is to take the inventory BEFORE the copy and verify the copy
against it: a pre-copy map of relative path to content digest. That is also
precisely what keeps the control passing — the copy is compared against the
source AS IT WAS, never as it now is. Digests rather than sizes because sizes
cannot answer the second case; measured cost on this tree is 0.015s for 731
files over 5MB, so the "size, not content" trade-off the module recorded was a
premature optimisation at this scale.

Scope is same-release coherence between a copy and the tree it was made from.
This is NOT an integrity, tamper-resistance or supply-chain claim: a digest
here detects a copy that did not land faithfully, and nothing about it
establishes that the SOURCE was trustworthy.
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
# A non-required, deferred module: the incident's own shape. No list of
# required paths names it, which is why completeness has to be established
# against the tree the copy was made from.
_DEFERRED = "scripts/livespec_orchestrator_beads_fabro/commands/_deferred.py"
_ORIGINAL_BYTES = "ORIGINAL"
_WRONG_SAME_LENGTH = "WRONGXXX"
_MUTATED_SAME_LENGTH = "MUTATED!"


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
        _ = (root / relative).write_text("", encoding="utf-8")
    _ = (root / _DEFERRED).write_text(_ORIGINAL_BYTES, encoding="utf-8")
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
    `test_payload_provisioning_interruption.py` gives for the same technique: a
    wall-clock race would pass or fail on machine load, so the interleaving is
    made deterministic instead.

    The DEPTH counter is load-bearing. `shutil.copytree` recurses through the
    patched name, and the inner calls RETURN FIRST, so a "first call wins"
    guard applies the mutation to a subdirectory and the fixture silently
    measures nothing. Entry depth 1 is the whole-tree provision.
    """
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    source_root = _install(root=tmp_path / "cache" / "0123abc")

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


def test_a_member_omitted_from_the_copy_is_refused_even_if_the_source_loses_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The post-copy walk cannot see it; the pre-copy inventory can."""
    payload = _import_payload()

    def omit(source: Path, copy: Path) -> None:
        (copy / _DEFERRED).unlink()
        (source / _DEFERRED).unlink()

    _source, provisioned = _provision_with_seam(
        payload=payload, monkeypatch=monkeypatch, tmp_path=tmp_path, mutate=omit
    )

    assert isinstance(provisioned, payload.PayloadRefusal), (
        "a payload missing a member the release carried when the copy started "
        "was published as complete, so a deferred import will fail at the far "
        f"end of a dispatch: {provisioned}"
    )
    assert (
        _DEFERRED in provisioned.message
    ), f"the refusal does not name the missing member: {provisioned.message}"


def test_a_file_copied_with_wrong_bytes_at_the_same_length_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Size equality cannot establish same-release bytes."""
    payload = _import_payload()

    def wrong_bytes(_source: Path, copy: Path) -> None:
        _ = (copy / _DEFERRED).write_text(_WRONG_SAME_LENGTH, encoding="utf-8")

    _source, provisioned = _provision_with_seam(
        payload=payload, monkeypatch=monkeypatch, tmp_path=tmp_path, mutate=wrong_bytes
    )

    assert isinstance(provisioned, payload.PayloadRefusal), (
        "a payload carrying WRONG CONTENT at the right length was published as "
        f"the same release: {provisioned}"
    )
    assert (
        _DEFERRED in provisioned.message
    ), f"the refusal does not name the divergent member: {provisioned.message}"


def test_a_coherent_payload_survives_its_source_changing_afterwards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE CONTROL, and the reason this file cannot demand source equality.

    Copying the release aside exists so an invocation keeps running when its
    source moves or disappears. A source that changes AFTER a complete copy is
    the success case, and the payload must still provision carrying its
    ORIGINAL bytes. A fix that compared the copy against the source as it NOW
    stands would refuse here — which is the invented stronger requirement this
    control exists to forbid.
    """
    payload = _import_payload()

    def mutate_source_after(source: Path, _copy: Path) -> None:
        _ = (source / _DEFERRED).write_text(_MUTATED_SAME_LENGTH, encoding="utf-8")

    _source, provisioned = _provision_with_seam(
        payload=payload, monkeypatch=monkeypatch, tmp_path=tmp_path, mutate=mutate_source_after
    )

    assert not isinstance(
        provisioned, payload.PayloadRefusal
    ), f"a coherent payload was refused because its source moved on: {provisioned}"
    retained = provisioned.root / _DEFERRED
    assert retained.is_file(), "the coherent payload lost the member"
    assert (
        retained.read_text(encoding="utf-8") == _ORIGINAL_BYTES
    ), "the retained payload does not carry the bytes it was copied from"
