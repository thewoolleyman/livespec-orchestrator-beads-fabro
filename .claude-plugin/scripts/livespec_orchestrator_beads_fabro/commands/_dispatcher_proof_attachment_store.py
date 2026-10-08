"""The upload leg: swap every over-allowance proof for a stored, digest-named asset.

`bd-ib-555xcd`. The PURE half of attachment — the digest, the slug, the rendered
reference, the read-back — is `_dispatcher_proof_attachment`. This module is the
IMPURE half, and the split is the usual one here: the decision about what an
attachment IS can be exercised without a store, while the act of putting bytes
somewhere cannot.

WHAT THIS IS CALLED BETWEEN. It runs AFTER the payload has been read (so each
assertion's proof is in hand and its mode is the item's own) and BEFORE the record
is rendered — because the record must carry the reference rather than the proof,
and the budget is measured on the rendered bytes. Running it after the render would
measure a record it then changed.

WHY AN UNDER-ALLOWANCE PROOF IS LEFT ENTIRELY ALONE, which is the property
assertion 4 of this item rests on. An assertion whose proof fits inline is returned
UNTOUCHED — the same value, not a reconstruction — so a record that published
inline before this module existed renders byte-for-byte as it did. Uploading every
proof "for consistency" would spend a forge round trip per assertion and change
every existing record's shape, for no gain on the records that were never at risk.

WHY THE ORDINAL IS GUARDED HERE RATHER THAN LEFT TO THE NAMER. `proof_asset_name`
refuses an ordinal outside the two-digit range by returning its refusal IN PLACE OF
a name, which a caller that did not check would upload under a filename that is an
error message. This module generates the ordinals, so it owns the bound: it checks
against the namer's OWN published constants, which is what keeps the two from
drifting into disagreement, and refuses before any upload.

WHY AN UPLOAD FAILURE REFUSES RATHER THAN FALLING BACK TO INLINE. Falling back
would hand the budget check a record it is bound to refuse, and the refusal would
advise attaching the proof — the very thing that had just failed. The operator
would read a remedy they had already attempted. So the failure is reported where it
happened, naming the asset and the store.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import (
    PROOF_ASSET_MAX_ORDINAL,
    ProofAssetStore,
    proof_asset_name,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment import (
    ATTACHED_PROOF_EXTENSION,
    ProofAttachment,
    attached_proof_slug,
    proof_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    INLINE_PROOF_ALLOWANCE_BYTES,
    measured_bytes,
    proof_overflows_inline_allowance,
)

__all__: list[str] = [
    "AttachmentTarget",
    "attached_assertions",
]

_UPLOAD_TIMEOUT_SECONDS = 120.0

_TOO_MANY_REFUSAL = (
    "ERROR: {surface} refused: this record would need {needed} attached proofs, and"
    " the ratified asset name carries a two-digit ordinal, so at most"
    " {maximum} can be named. The record is too large to publish as one comment;"
    " the remedy is a smaller proof recipe or a smaller item.\n"
)
_UPLOAD_FAILED_REFUSAL = (
    "ERROR: {surface} refused: the proof of {text} measures {size} bytes, over the"
    " per-assertion inline allowance of {allowance}, and uploading it to the proof"
    " asset store as {name} failed. Nothing was published. The store is the"
    " release tagged {tag}; confirm it exists and that this invocation may write"
    " to it.\n"
)


@dataclass(frozen=True, kw_only=True)
class AttachmentTarget:
    """Where one record's bulky proofs are stored, and under whose identity.

    `run_id` is the record's own publishing identity — a Fabro run id on a factory
    record, a session identity on a host or plan one — because the ratified name
    carries it and that is what makes "no run or session may overwrite another's
    asset" true rather than hoped for.

    `stage` is the ratified stage word for the leg publishing this record, so a
    host-leg asset is named for the host leg rather than borrowing the factory's.
    """

    work_item_id: str
    run_id: str
    stage: str
    release_tag: str
    store: ProofAssetStore
    scratch: Path


def attached_assertions(
    *,
    assertions: Sequence[RecordAssertion],
    target: AttachmentTarget,
    runner: CommandRunner,
    surface: str,
    emit: Callable[[str], None],
) -> tuple[RecordAssertion, ...] | None:
    """Every assertion, with each over-allowance proof swapped for an attachment.

    `None` is a REFUSAL — the caller must publish nothing — and it is returned only
    where an attachment was genuinely needed and could not be made. An assertion
    whose proof fits inline never reaches the store at all.

    The ordinal is the position among the ATTACHED proofs rather than among the
    assertions, so a record with one bulky proof at Definition of Done position
    seven names it `01`. The alternative would leave gaps that read as missing
    assets, and the ordinal's job here is to distinguish this record's attachments
    from each other, not to index the Definition of Done.
    """
    needed = [one for one in assertions if proof_overflows_inline_allowance(proof=one.proof)]
    if not needed:
        return tuple(assertions)
    if len(needed) > PROOF_ASSET_MAX_ORDINAL:
        emit(
            _TOO_MANY_REFUSAL.format(
                surface=surface, needed=len(needed), maximum=PROOF_ASSET_MAX_ORDINAL
            )
        )
        return None
    attached: dict[str, ProofAttachment] = {}
    for ordinal, one in enumerate(needed, start=1):
        made = _uploaded(
            assertion=one, ordinal=ordinal, target=target, runner=runner, surface=surface, emit=emit
        )
        if made is None:
            return None
        attached[one.text] = made
    return tuple(
        one if one.text not in attached else replace(one, attachment=attached[one.text])
        for one in assertions
    )


def _uploaded(
    *,
    assertion: RecordAssertion,
    ordinal: int,
    target: AttachmentTarget,
    runner: CommandRunner,
    surface: str,
    emit: Callable[[str], None],
) -> ProofAttachment | None:
    """Write one proof to scratch, store it, and describe it, or refuse.

    The digest and the size are taken from the BYTES WRITTEN, not from the in-memory
    string, so what the record states is what a verifier downloading the asset will
    measure. They are the same bytes either way — the file is written from this
    string — but taking them from the file is what keeps that true if the write ever
    grows an encoding step.
    """
    digest = proof_digest(text=assertion.proof)
    name = proof_asset_name(
        work_item_id=target.work_item_id,
        run_id=target.run_id,
        stage=target.stage,
        ordinal=ordinal,
        slug=attached_proof_slug(digest=digest),
        extension=ATTACHED_PROOF_EXTENSION,
    )
    path = target.scratch / name
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(assertion.proof, encoding="utf-8")
    result = runner.run(
        argv=list(target.store.upload_argv(name=name, path=path)),
        cwd=target.scratch,
        timeout_seconds=_UPLOAD_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        emit(
            _UPLOAD_FAILED_REFUSAL.format(
                surface=surface,
                text=assertion.text,
                size=measured_bytes(text=assertion.proof),
                allowance=INLINE_PROOF_ALLOWANCE_BYTES,
                name=name,
                tag=target.release_tag,
            )
        )
        return None
    return ProofAttachment(
        name=name,
        size_bytes=path.stat().st_size,
        digest=digest,
        url=_asset_url(tag=target.release_tag, name=name, stdout=result.stdout),
    )


def _asset_url(*, tag: str, name: str, stdout: str) -> str:
    """The stored asset's URL: whatever the store reported, else the derived form.

    `gh release upload` prints no URL, so the derived form is the ordinary answer
    rather than a fallback. A store that DOES report one is preferred because it
    knows where it put the bytes, while this module only knows where it asked for
    them to go.

    The derived form is relative to the release tag rather than absolute, because
    the repository is not a thing this module is told. The surfaces that fetch the
    asset resolve it by NAME against the tag anyway — the URL is for a human reader
    — so an unresolvable origin here cannot break the digest check.
    """
    reported = stdout.strip().splitlines()
    for line in reversed(reported):
        if line.strip().startswith(("http://", "https://")):
            return line.strip()
    return f"releases/download/{tag}/{name}"
