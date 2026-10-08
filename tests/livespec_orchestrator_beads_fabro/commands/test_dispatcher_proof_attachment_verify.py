"""Tests for grading an assertion whose proof lives in an attached asset.

`bd-ib-555xcd`: the acceptance pass and the replay stage grade such an assertion by
FETCHING the asset and checking its digest against the one the record states, and a
missing or digest-mismatched asset is reported as ABSENT EVIDENCE rather than as a
pass.

WHY THIS CANNOT BE LEFT TO THE RECORD'S OWN PROSE. Once a bulky proof travels as an
asset, the record no longer CONTAINS its evidence — it contains a pointer to it. A
pass that read only the record would therefore grade the assertion on the
publisher's say-so, which is exactly the property the proof chain exists to remove.
The asset can also go bad after the record is written, in ways nothing in the
record reveals: a later fix round re-uploads the name, an upload truncates, a
release is pruned. Only the digest distinguishes "these are the bytes the capture
measured" from "something is at that name".

WHY ABSENT EVIDENCE AND NOT A FAILURE. The unevidenceable-assertion clause is
explicit that an assertion nothing evidences "is unevidenced, not failed": a FAIL
routes the item to rework and consumes an `acceptance_rework_cap` attempt the
clause forbids spending. An unfetchable asset says nothing about whether the
behaviour holds — it says the proof could not be read — so it parks the item on
NEEDS_ATTENTION instead of punishing it.

WHY THE DEFAULT READER ANSWERS `None` FOR EVERYTHING. A caller that forgot to
supply a reader must not thereby pass every attachment. The default is the
fail-CLOSED direction: every asset reads as unfetchable, so the assertion parks
rather than closing on a digest nobody compared.
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    NO_GOVERNING_SCENARIO,
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment import (
    ProofAttachment,
    proof_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import proof_leg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_VERIFIED,
    proof_records,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment_verify"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_proof_attachment_verify.py"
)

_RUN = "01M44MERGINGRUN"
_ASSERTION = "The listing projects every record's parent field."
_PROOF = "the bulky captured output\n" * 40
_ASSET = "bd-ib-555xcd__01M44MERGINGRUN__capture__01__proof-sha256-deadbeefdeadbeef.txt"
_URL = f"https://example.test/releases/download/proof-assets/{_ASSET}"


def _module() -> object:
    """The verify module, imported inside a test body rather than at module top."""
    return importlib.import_module(_MODULE)


def _criteria() -> EffectiveCriteria:
    return EffectiveCriteria(
        source="definition-of-done",
        text=f"- {_ASSERTION}",
        assertions=(_ASSERTION,),
        proof_modes=(PROOF_MODE_FACTORY_CAPTURED,),
    )


def _record_body(*, attachment: ProofAttachment | None, proof: str = _PROOF) -> str:
    """One `verified` record for the single assertion, attached or inline."""
    return render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=VERDICT_VERIFIED,
        identity=f"run {_RUN}",
        timestamp="2026-10-08T00:00:00Z",
        build=BuildIdentity(release_tag=None, installed_build=None, commit="abc123"),
        assertions=(
            RecordAssertion(
                text=_ASSERTION,
                proof_mode=PROOF_MODE_FACTORY_CAPTURED,
                governing_scenario=NO_GOVERNING_SCENARIO,
                steps=("Run the listing. Produces proof 01.",),
                proof=proof,
                reproduced=True,
                attachment=attachment,
            ),
        ),
    )


def _absent_asset(*, name: str) -> str | None:
    """A reader standing for an asset the store does not hold."""
    del name
    return None


def _fetches(*, digest: str) -> Callable[..., str | None]:
    """A reader standing for a store holding bytes that hash to `digest`."""

    def _read(*, name: str) -> str | None:
        del name
        return digest

    return _read


def _attachment(*, digest: str) -> ProofAttachment:
    return ProofAttachment(
        name=_ASSET, size_bytes=len(_PROOF.encode("utf-8")), digest=digest, url=_URL
    )


def _leg_for(
    *,
    attachment: ProofAttachment | None,
    reader: Callable[..., str | None] | None = None,
) -> object:
    """Grade the one assertion against a record carrying (or not) an attachment."""
    body = _record_body(attachment=attachment)
    records = proof_records(comments=[{"body": body, "url": "https://example.test/c/1"}])
    assert len(records) == 1
    extra: dict[str, object] = {} if reader is None else {"attachment_digest": reader}
    return proof_leg(
        criteria=_criteria(),
        records=records,
        run_ids=(_RUN,),
        reason="read",
        **extra,  # pyright: ignore[reportArgumentType]
    )


def test_a_mismatched_attachment_digest_is_absent_evidence_not_a_pass() -> None:
    """The headline assertion, and the Red this slice was authored against.

    The record states `Reproduced: yes.` and names an asset, so a pass that read
    only the record grades this assertion PASSED. The asset's real bytes hash to
    something else, which means they are not the bytes the capture measured — so
    there is no evidence here, and the assertion must come back unevidenced.

    Graded through the DEFAULT reader, which answers `None` for every asset: a
    caller that supplies none must not thereby pass every attachment.
    """
    leg = _leg_for(attachment=_attachment(digest=f"sha256:{'0' * 64}"))

    assert _ASSERTION in leg.unevidenced  # pyright: ignore[reportAttributeAccessIssue]
    assert leg.checks == ()  # pyright: ignore[reportAttributeAccessIssue]


def test_a_missing_asset_is_absent_evidence_not_a_pass() -> None:
    """An asset nothing can fetch evidences nothing, however the record reads."""
    leg = _leg_for(
        attachment=_attachment(digest=proof_digest(text=_PROOF)),
        reader=_absent_asset,
    )

    assert _ASSERTION in leg.unevidenced  # pyright: ignore[reportAttributeAccessIssue]


def test_a_matching_attachment_digest_grades_the_assertion_normally() -> None:
    """The control: a fetched asset whose bytes ARE the record's bytes still passes.

    Without this, every test above is equally consistent with "the digest check
    works" and with "an attached proof can never pass", and the two are
    indistinguishable from the refusals alone — the second would make the whole
    attachment path useless while every mismatch test stayed green.
    """
    digest = proof_digest(text=_PROOF)

    leg = _leg_for(attachment=_attachment(digest=digest), reader=_fetches(digest=digest))

    assert leg.unevidenced == ()  # pyright: ignore[reportAttributeAccessIssue]
    checks = leg.checks  # pyright: ignore[reportAttributeAccessIssue]
    assert len(checks) == 1
    assert checks[0].passed is True


def test_an_inline_record_is_graded_without_any_asset_fetch() -> None:
    """A record with no attachment is unaffected, and fetches nothing.

    The reader raises if called, so this is evidence the inline path does not reach
    the store at all — not merely that it happens to reach the same verdict.
    """

    def _never(*, name: str) -> str | None:
        raise AssertionError(f"no asset may be fetched for an inline record: {name}")

    # The guard is a REAL instrument before anything rests on it: it fires when
    # called, so "nothing was fetched" below is evidence rather than a property of a
    # stand-in that could never have complained.
    with pytest.raises(AssertionError):
        _ = _never(name=_ASSET)

    leg = _leg_for(attachment=None, reader=_never)

    assert leg.unevidenced == ()  # pyright: ignore[reportAttributeAccessIssue]
    assert leg.checks[0].passed is True  # pyright: ignore[reportAttributeAccessIssue]


def test_the_verify_module_exposes_the_reader_seam_and_its_fail_closed_default() -> None:
    """The seam is a callable so the decision can be exercised without a forge."""
    assert _MODULE_PATH.is_file()
    verify = _module()

    assert verify.unverified_attachment(name=_ASSET) is None  # pyright: ignore[reportAttributeAccessIssue]
    assert "attachment_digest_reader" in verify.__all__  # pyright: ignore[reportAttributeAccessIssue]
    assert "attachment_is_evidence" in verify.__all__  # pyright: ignore[reportAttributeAccessIssue]


def test_attachment_is_evidence_requires_an_exact_digest_match() -> None:
    """Equality, and nothing looser. A prefix match would admit a truncated digest."""
    verify = _module()
    digest = proof_digest(text=_PROOF)
    value = _attachment(digest=digest)

    assert verify.attachment_is_evidence(attachment=value, fetched=digest)  # pyright: ignore[reportAttributeAccessIssue]
    assert not verify.attachment_is_evidence(attachment=value, fetched=None)  # pyright: ignore[reportAttributeAccessIssue]
    assert not verify.attachment_is_evidence(attachment=value, fetched=digest[:-1])  # pyright: ignore[reportAttributeAccessIssue]
    assert not verify.attachment_is_evidence(  # pyright: ignore[reportAttributeAccessIssue]
        attachment=value, fetched=f"sha256:{'1' * 64}"
    )


def test_the_reader_downloads_by_name_and_digests_the_downloaded_bytes(
    tmp_path: Path,
) -> None:
    """The real reader fetches the named asset and hashes the FILE, not the record.

    Hashing the downloaded bytes is the whole point: a reader that re-hashed the
    record's own stated digest, or the proof text the record no longer carries,
    would compare a value with itself and pass every asset.
    """
    verify = _module()
    downloaded = "the bulky captured output\n" * 40

    class _Runner:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def run(
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
            env: dict[str, str] | None = None,
            stdin: int | None = None,
        ) -> object:
            del cwd, timeout_seconds, env, stdin
            self.calls.append(list(argv))
            # Stand in for `gh release download`, which writes the asset to --dir.
            target = Path(argv[argv.index("--dir") + 1]) / _ASSET
            target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_text(downloaded, encoding="utf-8")
            result = importlib.import_module(
                "livespec_orchestrator_beads_fabro.commands._dispatcher_engine"
            )
            return result.CommandResult(exit_code=0, stdout="", stderr="")

    runner = _Runner()
    reader = verify.attachment_digest_reader(  # pyright: ignore[reportAttributeAccessIssue]
        repo=tmp_path, release_tag="proof-assets", runner=runner
    )

    answered = reader(name=_ASSET)

    assert answered == f"sha256:{hashlib.sha256(downloaded.encode('utf-8')).hexdigest()}"
    assert runner.calls[0][:3] == ["gh", "release", "download"]
    assert _ASSET in runner.calls[0]


def test_the_reader_answers_none_when_the_download_fails(tmp_path: Path) -> None:
    """An unfetchable asset is `None` — the unobserved answer, not an empty digest.

    An empty-string digest would compare unequal to the record's and so happen to
    reach the right verdict today, but it would say the asset WAS read and found
    different, which is a different fact and the wrong one to journal.
    """
    verify = _module()

    class _Failing:
        def run(
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
            env: dict[str, str] | None = None,
            stdin: int | None = None,
        ) -> object:
            del argv, cwd, timeout_seconds, env, stdin
            engine = importlib.import_module(
                "livespec_orchestrator_beads_fabro.commands._dispatcher_engine"
            )
            return engine.CommandResult(exit_code=1, stdout="", stderr="not found")

    reader = verify.attachment_digest_reader(  # pyright: ignore[reportAttributeAccessIssue]
        repo=tmp_path, release_tag="proof-assets", runner=_Failing()
    )

    assert reader(name=_ASSET) is None
