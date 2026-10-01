"""The standing proof-assets prerelease, and the per-repository rendering measurement.

`SPECIFICATION/contracts.md`'s Proof-of-Done-record clause (ratified v114) says
the release assets of one standing prerelease per governed repository MAY be the
first proof asset store; that the prerelease MUST be marked prerelease so it is
never the repository's latest release; that it MUST be created by the Dispatcher
BEFORE the first dispatch of a repository whose item carries a `factory_captured`
assertion; and that a dispatch whose target lacks it after that attempt MUST
refuse before any run exists, naming the tag. This module is all of that, plus
the measurement that decides how a record references an image.

WHY THE RENDERING IS MEASURED HERE AND NOT DECIDED ONCE AT IMPLEMENTATION TIME.
The clause requires the inline half to be measured on a private repository before
a store is selected, and WAIVED PER REPOSITORY where it cannot be met. A literal
baked into this module would answer for one repository and be silently wrong for
the next one the fleet governs, and nothing would ever re-ask -- the shape the
verification-discipline rule about instructions outliving their condition warns
about. So the determination is made per dispatch from the repository's own
visibility, and journaled.

THE MEASUREMENT THE POLICY RESTS ON. Measured 2026-10-01 against live GitHub,
read-only, with controls in both directions. A PRIVATE repository's own-origin
content returns 404 to an ANONYMOUS fetch -- probed on
`thewoolleyman/window-namer` through both `github.com/<owner>/<repo>/raw/...` and
`raw.githubusercontent.com`, with an authenticated read of the same repository as
the control that the instrument was aimed at a repository that exists and is
private. A PUBLIC repository returns 200 through the identical probe, which is
the control that the instrument could return the other answer at all. The forge
renders an inline image in a comment by fetching it through its own ANONYMOUS
image proxy, so an asset no anonymous fetch can reach cannot render inline. Hence
`private` takes the authenticated-link arm.

WHAT THAT MEASUREMENT DID NOT ESTABLISH, stated because a reader will otherwise
assume it did: no private repository reachable from the measuring sandbox carried
a release, so the probe was aimed at private own-origin content rather than at a
private release ASSET specifically. The inference from one to the other is that
both are served from the same authenticated origin. A later slice that provisions
a private-repository prerelease should re-probe the asset URL directly and, if it
renders inline after all, narrow this policy -- the authenticated-link arm costs
an inline rendering, never the proof.

WHY AN UNREADABLE VISIBILITY WAIVES RATHER THAN GUESSES. An unknown visibility
means the measurement did not happen. Of the two available answers, the waiver
costs an inline rendering the repository might have supported; the other publishes
an inline reference on a repository nobody established was public. The proof
itself is never waived either way, so the waiver is the cheap mistake.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import (
    RENDERING_AUTHENTICATED_LINK,
    RENDERING_INLINE,
    ReleaseAssetProofStore,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DEFAULT_PROOF_ASSETS_RELEASE_TAG",
    "PROOF_ASSETS_RELEASE_TAG_KEY",
    "RELEASE_ASSETS_STORE_NAME",
    "ProofAssetsStoreResolution",
    "ensure_proof_assets_release",
    "item_is_proof_bearing",
    "proof_assets_release_tag",
    "proof_assets_release_tag_refusal",
    "proof_rendering_for_visibility",
    "proof_store_journal_record",
    "release_create_argv",
    "release_view_argv",
    "repository_visibility_from_view",
]

PROOF_ASSETS_RELEASE_TAG_KEY = "proof_assets_release_tag"
DEFAULT_PROOF_ASSETS_RELEASE_TAG = "proof-assets"

# The store this module resolves, named on the journal record. The clause requires
# the waiver to name "the store measured", and a second store added later writes
# its own name here rather than inheriting this one.
RELEASE_ASSETS_STORE_NAME = "release_assets"

# The repository visibility that satisfies the forge's anonymous image proxy. Read
# case-insensitively because the forge reports `PUBLIC` through its API and
# `public` through some of its own surfaces, and a case-sensitive compare would
# waive the inline half for every public repository on the wrong surface.
_PUBLIC_VISIBILITY = "public"

_RELEASE_NOTES = (
    "Standing carrier for Proof of Done assets. Created and maintained by the "
    "livespec Dispatcher; marked prerelease so it is never this repository's "
    "latest release. Do NOT delete it while any Proof of Done record references "
    "an asset in it."
)
_RELEASE_TITLE = "Proof of Done assets"

# Both calls are single forge round-trips against an already-authenticated `gh`.
_FORGE_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class ProofAssetsStoreResolution:
    """The resolved proof asset store for one repository, plus how it got there.

    `store` is already bound to the measured rendering, which is the
    resolve-once-project-everywhere discipline this package applies to the
    integration contract and the ACP adapters: no seam downstream re-derives
    whether this repository waives the inline half.

    `created` records whether THIS resolution created the prerelease, so the
    journal can distinguish a first provisioning from a steady-state dispatch
    without diffing the forge.
    """

    store: ReleaseAssetProofStore
    rendering: str
    visibility: str
    created: bool


def proof_assets_release_tag(*, block: dict[str, Any]) -> str:
    """Resolve `dispatcher.proof_assets_release_tag`, or return a refusal.

    Committed-configuration-only by ratification -- it is deliberately NOT a
    console setting, because the tag names a release that MUST NOT be deleted
    while any record references it, and a dial that can be turned at runtime
    orphans the assets already stored under the old value.

    An ABSENT key resolves the ratified default, which is a complete answer. A
    key that is PRESENT but blank, null, or not a string is refused rather than
    defaulted: a target that wrote the key meant to override the default, so
    sliding back onto `proof-assets` would store that repository's proof under a
    tag nobody declared.

    Absence is tested by MEMBERSHIP, not by a `None` value, because those are
    different declarations and this package already distinguishes them everywhere
    else -- the integration resolver reads a present-but-null key as defective
    rather than as a slide onto the convention, for exactly this reason.

    NOTE THE RETURN TYPE, because it is unusual for this package: the tag and the
    refusal are BOTH `str`, so a caller cannot tell them apart by type. A caller
    that BRANCHES must use `proof_assets_release_tag_refusal` below instead of
    inspecting this message -- sniffing its prefix would be a discriminator a
    legitimately-named tag could defeat.
    """
    refusal = proof_assets_release_tag_refusal(block=block)
    if refusal is not None:
        return refusal
    if PROOF_ASSETS_RELEASE_TAG_KEY not in block:
        return DEFAULT_PROOF_ASSETS_RELEASE_TAG
    return str(block[PROOF_ASSETS_RELEASE_TAG_KEY]).strip()


def proof_assets_release_tag_refusal(*, block: dict[str, Any]) -> str | None:
    """The refusal for a malformed tag declaration, or None when it is usable.

    THE CONTROL-FLOW ACCESSOR of the pair. It exists because its sibling above
    cannot signal failure by type, and a gate that has to decide whether to refuse
    a dispatch must not make that decision by pattern-matching an error message.
    One validation, two accessors.
    """
    if PROOF_ASSETS_RELEASE_TAG_KEY not in block:
        return None
    raw = block[PROOF_ASSETS_RELEASE_TAG_KEY]
    if isinstance(raw, str) and raw.strip():
        return None
    return (
        f"dispatcher.{PROOF_ASSETS_RELEASE_TAG_KEY} must be a non-empty string "
        f"naming the standing proof-assets prerelease tag; got {raw!r}"
    )


def item_is_proof_bearing(*, item: WorkItem) -> bool:
    """Whether this item's Definition of Done carries a `factory_captured` assertion.

    The trigger for provisioning is the ASSERTION's proof mode, not the presence of
    the section and not the item's type. An item whose every assertion sits under a
    `Human-attested` sub-heading has a Definition of Done and has assertions, yet
    will never store an asset -- so a predicate keyed on the section would
    provision a prerelease for a repository that needs none, and the refusal that
    follows a failed creation would block a dispatch that had no proof to store.

    The section is parsed through the ONE ratified parse, never a second one: the
    effective-acceptance-criteria clause says outright that no surface may parse
    the section by another path.
    """
    parsed = definition_of_done(description=item.description or "")
    return any(one.proof_mode == PROOF_MODE_FACTORY_CAPTURED for one in parsed.assertions)


def proof_rendering_for_visibility(*, visibility: str) -> str:
    """How a record must reference an image in a repository of this visibility.

    `inline` only for a repository the forge's anonymous image proxy can fetch
    from, which the module docstring's measurement establishes is the public case.
    Everything else -- private, internal, and an unreadable answer alike -- takes
    the authenticated-link arm, which waives the inline half and nothing else.
    """
    if visibility.strip().casefold() == _PUBLIC_VISIBILITY:
        return RENDERING_INLINE
    return RENDERING_AUTHENTICATED_LINK


def release_view_argv(*, tag: str) -> list[str]:
    """The argv that asks whether the standing prerelease already exists."""
    return ["gh", "release", "view", tag, "--json", "tagName"]


def release_create_argv(*, tag: str) -> list[str]:
    """The argv that creates the standing prerelease.

    `--prerelease` is load-bearing rather than decorative: the clause requires the
    release to be marked prerelease precisely so a carrier of proof assets never
    becomes the repository's advertised latest release.
    """
    return [
        "gh",
        "release",
        "create",
        tag,
        "--prerelease",
        "--title",
        _RELEASE_TITLE,
        "--notes",
        _RELEASE_NOTES,
    ]


def ensure_proof_assets_release(
    *,
    runner: CommandRunner,
    repo: Path,
    tag: str,
    visibility: str,
) -> ProofAssetsStoreResolution | str:
    """Ensure the standing prerelease exists, or refuse naming the tag.

    Probe first, create only on absence. The probe is what makes this idempotent,
    and idempotence is required rather than tidy: the clause says the prerelease
    MUST NOT be deleted while any record references it, and an unconditional
    create would rewrite a release that live records point into.

    A creation that fails leaves the target still lacking the tag, which is the
    ratified refusal -- returned as a message rather than raised, on the house
    `X | str` rail, so the caller routes it as a pre-dispatch refusal BEFORE any
    Fabro run exists. The tag is IN the message because the remedy is to create
    that release, and a refusal naming only the repository leaves an operator
    guessing which tag the factory wanted.
    """
    probe = runner.run(
        argv=release_view_argv(tag=tag),
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if probe.exit_code == 0:
        return _resolution(tag=tag, visibility=visibility, created=False)
    creation = runner.run(
        argv=release_create_argv(tag=tag),
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if creation.exit_code != 0:
        return (
            f"Fabro dispatch refused: this item carries a {PROOF_MODE_FACTORY_CAPTURED} "
            f"assertion, so its proof images need the standing prerelease tagged "
            f"{tag!r}, which does not exist and could not be created. Create it "
            f"(a prerelease, so it is never the latest release) or set "
            f"dispatcher.{PROOF_ASSETS_RELEASE_TAG_KEY} to a tag that exists. "
            f"gh reported: {creation.stderr.strip()}"
        )
    return _resolution(tag=tag, visibility=visibility, created=True)


def proof_store_journal_record(
    *,
    repository: str,
    tag: str,
    visibility: str,
    rendering: str,
    created: bool,
) -> dict[str, object]:
    """The per-repository proof-store record for the dispatch journal.

    The clause requires the waiver to be journaled PER REPOSITORY naming the store
    measured, so all four facts ride together: which repository, which store, what
    the measurement found, and whether the inline half is waived for it. A record
    missing the store name could not answer "which store was measured" once a
    second store exists.

    `inline_waived` is DERIVED from the rendering rather than passed in, so the
    record cannot disagree with the store the same resolution built.
    """
    return {
        "repository": repository,
        "store": RELEASE_ASSETS_STORE_NAME,
        PROOF_ASSETS_RELEASE_TAG_KEY: tag,
        "visibility": visibility,
        "rendering": rendering,
        "inline_waived": rendering != RENDERING_INLINE,
        "prerelease_created": created,
    }


def repository_visibility_from_view(*, stdout: str) -> str:
    """Read the visibility out of a `gh repo view --json visibility` payload.

    An unparseable or keyless payload yields the empty string, which
    `proof_rendering_for_visibility` treats as unmeasured and therefore waives --
    rather than raising, because a forge that answered oddly is not a bug in this
    package and the fail-safe answer is already defined.
    """
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    value = cast("dict[str, object]", payload).get("visibility")
    return value if isinstance(value, str) else ""


def _resolution(*, tag: str, visibility: str, created: bool) -> ProofAssetsStoreResolution:
    rendering = proof_rendering_for_visibility(visibility=visibility)
    return ProofAssetsStoreResolution(
        store=ReleaseAssetProofStore(release_tag=tag, rendering=rendering),
        rendering=rendering,
        visibility=visibility,
        created=created,
    )
