"""The ONE seam binary proof is stored through, and the flat name it is stored under.

`SPECIFICATION/contracts.md`'s Proof-of-Done-record clause (ratified v114) says
binary proof "MUST be stored through one implementation-owned store seam" and
fixes the asset name's form exactly. This module is that seam and that namer.

WHY THE SEAM IS A PROTOCOL AND NOT A FUNCTION. The clause states ONE requirement
a store must satisfy -- an authorized viewer sees each image inline in the record
comment, and no unauthorized viewer can fetch it -- and then says the release
assets of a standing prerelease MAY be the FIRST implementation. "First" is the
word that decides the shape: a second store has to be addable without touching
the capture stage, so what the capture stage depends on is the Protocol below and
never `ReleaseAssetProofStore` by name.

WHY THE NAME IS BUILT HERE RATHER THAN IN THE PROMPT. Two stages produce assets
on two different adapters, and the whole point of the ordinal is that the
`verify` asset of ordinal 07 compares to the `capture` asset of ordinal 07. Two
agents independently formatting a name from prose would eventually disagree on
zero-padding or on the separator, and the failure would present as "the replay
found no counterpart" rather than as a formatting bug. One namer, with the
separator and padding pinned by test, removes that class entirely.

WHY REFUSALS RATHER THAN EXCEPTIONS, AND WHY THEY ARE LOUD. A stage value outside
the closed pair, or an ordinal with no two-digit representation, yields a name
that UPLOADS PERFECTLY WELL and is then invisible to the same-ordinal comparison
the replay performs. That is a silent failure, so it is refused at construction
with a message naming the offending value -- the house `X | str` rail every
sibling resolver here uses.

THE TWO RENDERINGS, AND WHY BOTH EXIST. The clause waives the INLINE half -- and
only that half -- for a repository where no API-drivable store satisfies it,
requiring "one authenticated link per image in place of the inline reference".
Which arm applies is NOT decided here: it is measured per repository and
projected in, because a store that guessed would waive the requirement on the
repositories that can meet it. `_dispatcher_proof_release` owns that measurement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__: list[str] = [
    "PROOF_ASSET_FIELD_SEPARATOR",
    "PROOF_RENDERINGS",
    "PROOF_STAGES",
    "PROOF_STAGE_CAPTURE",
    "PROOF_STAGE_VERIFY",
    "RENDERING_AUTHENTICATED_LINK",
    "RENDERING_INLINE",
    "ProofAssetStore",
    "ReleaseAssetProofStore",
    "proof_asset_name",
    "proof_asset_slug",
]

# The two stages that produce proof, and the field value each writes into a name.
# A CLOSED pair: the replay's same-ordinal comparison is defined between exactly
# these two, so a third value has no counterpart to compare against.
PROOF_STAGE_CAPTURE = "capture"
PROOF_STAGE_VERIFY = "verify"
PROOF_STAGES: tuple[str, ...] = (PROOF_STAGE_CAPTURE, PROOF_STAGE_VERIFY)

# How a record REFERENCES a stored image. Self-describing names rather than
# numbered modes, per the maintainer ruling that every enumeration value names
# what it IS.
RENDERING_INLINE = "inline"
RENDERING_AUTHENTICATED_LINK = "authenticated_link"
PROOF_RENDERINGS: tuple[str, ...] = (RENDERING_INLINE, RENDERING_AUTHENTICATED_LINK)

# The field separator the ratified form spells. A DOUBLE underscore on purpose:
# a work-item id and a slug both carry single hyphens, and a run id carries
# neither, so a single-character separator could not be told from content.
PROOF_ASSET_FIELD_SEPARATOR = "__"

# The two-digit ordinal's representable range, which is what makes `NN` literal.
_MIN_ORDINAL = 1
_MAX_ORDINAL = 99

_NON_SLUG = re.compile(r"[^a-z0-9]+")


@runtime_checkable
class ProofAssetStore(Protocol):
    """What the capture and replay stages need from a proof asset store.

    Two operations, because the stages do two things with an image: PUT it
    somewhere durable, and REFERENCE it from the record comment. Keeping the
    reference rendering on the store rather than in the prompt is what lets the
    inline-versus-authenticated-link decision be a property of the selected store
    for a repository instead of a branch in prose.
    """

    def upload_argv(self, *, name: str, path: Path) -> tuple[str, ...]:
        """The argv that stores the file at `path` under `name`."""
        ...

    def record_reference(self, *, slug: str, ordinal: int, url: str) -> str:
        """The markdown one record line uses to reference the stored image."""
        ...


@dataclass(frozen=True, kw_only=True)
class ReleaseAssetProofStore:
    """The first implementation: release assets of one standing prerelease.

    `release_tag` is the resolved `dispatcher.proof_assets_release_tag`, and the
    prerelease it names is created by the Dispatcher before the first
    proof-bearing dispatch -- this object never creates it, because a store that
    provisioned on demand would make "the prerelease exists" unobservable before
    a run is already burning.

    `rendering` is the MEASURED answer for this repository, passed in rather than
    decided here (see the module docstring).
    """

    release_tag: str
    rendering: str

    def upload_argv(self, *, name: str, path: Path) -> tuple[str, ...]:
        """The `gh release upload` argv for one asset.

        `--clobber` is required rather than convenient: every accepted review fix
        round re-earns a green janitor and re-enters the capture stage, which
        re-uploads the SAME name for the same run and ordinal. Without it the
        second upload fails on a name that is entirely correct, and the run parks
        for a reason no reader could act on.

        The asset is uploaded under `name` explicitly (`<path>#<name>` is gh's
        own spelling for that) so the stored name is the ratified one rather than
        whatever the scratch file happened to be called.
        """
        return (
            "gh",
            "release",
            "upload",
            self.release_tag,
            f"{path}#{name}",
            "--clobber",
        )

    def record_reference(self, *, slug: str, ordinal: int, url: str) -> str:
        """One record line referencing the stored image.

        Inline where the forge renders it for an authorized viewer; ONE
        authenticated link per image where that half is waived. The ordinal is
        carried in the visible text of BOTH arms, because a reader comparing a
        `verify` record against its `capture` peer matches them by ordinal and a
        reference whose ordinal lived only in the URL would make that a
        URL-parsing exercise.
        """
        label = f"{slug} (proof {_ordinal_text(ordinal=ordinal)})"
        if self.rendering == RENDERING_INLINE:
            return f"![{label}]({url})"
        return f"[{label} — authenticated link]({url})"


def proof_asset_name(
    *,
    work_item_id: str,
    run_id: str,
    stage: str,
    ordinal: int,
    slug: str,
    extension: str,
) -> str:
    """One asset name in the ratified flat form, or an actionable refusal.

    The form is
    `<work-item-id>__<run-id>__<capture|verify>__<NN>__<slug>.<ext>`.

    The run id is a FIELD rather than decoration: it is what makes "no run may
    overwrite another run's asset" true of the store, so two runs alike in every
    other field still write two distinct objects.
    """
    if stage not in PROOF_STAGES:
        return (
            f"proof asset stage must be one of {PROOF_STAGE_CAPTURE!r} or "
            f"{PROOF_STAGE_VERIFY!r}; got {stage!r}"
        )
    if ordinal < _MIN_ORDINAL or ordinal > _MAX_ORDINAL:
        return (
            f"proof asset ordinal must be between {_MIN_ORDINAL} and {_MAX_ORDINAL} "
            f"so it renders as the form's two digits; got {ordinal}"
        )
    fields = (
        work_item_id,
        run_id,
        stage,
        _ordinal_text(ordinal=ordinal),
        proof_asset_slug(text=slug),
    )
    return f"{PROOF_ASSET_FIELD_SEPARATOR.join(fields)}.{extension}"


def proof_asset_slug(*, text: str) -> str:
    """Reduce a free-text description to the form's short lowercase-kebab slug.

    Enforced rather than trusted. A slug carrying a space, an underscore or an
    uppercase letter would either collide with the `__` field separator or make
    two otherwise-identical names differ by case, and both failures surface as a
    replay that cannot find the counterpart asset rather than as a bad name.
    """
    return _NON_SLUG.sub("-", text.casefold()).strip("-")


def _ordinal_text(*, ordinal: int) -> str:
    """The ordinal as the form's two digits."""
    return f"{ordinal:02d}"
