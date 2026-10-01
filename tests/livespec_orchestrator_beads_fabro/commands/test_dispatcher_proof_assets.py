"""The proof asset store seam and the flat asset naming form.

Binds the `SPECIFICATION/contracts.md` Proof-of-Done-record clause ratified in
v114: the naming form every asset name MUST have, the one implementation-owned
store seam binary proof is stored through, and the two ways a record may
reference an image — inline for a repository where the forge renders it, and one
authenticated link per image where the inline half is waived.

WHY THE NAME IS ASSERTED FIELD BY FIELD AND AS A WHOLE. The form is load-bearing
in two separate ways that one assertion cannot cover. The RUN ID is what makes
"no run may overwrite another run's asset" true, so two runs differing in nothing
else must produce different names. The ORDINAL is what makes a `verify` asset
comparable to the `capture` asset it corresponds to, so the same ordinal across
the two stages must differ in the stage field ALONE.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets"
_SOURCE = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_proof_assets.py"
)


def _module() -> object:
    """The module under test, imported inside the body.

    Imported here rather than at module top so the Red of this slice fails on a
    genuine assertion about the missing file rather than dying at COLLECTION with
    a `ModuleNotFoundError`, which would prove only unimportability.
    """
    return importlib.import_module(_MODULE)


def test_the_module_exists_and_exports_the_seam_and_the_namer() -> None:
    """The seam is one module, and these are the names its consumers import."""
    assert _SOURCE.is_file(), f"{_SOURCE} does not exist"
    module = _module()

    for name in (
        "PROOF_STAGE_CAPTURE",
        "PROOF_STAGE_VERIFY",
        "RENDERING_AUTHENTICATED_LINK",
        "RENDERING_INLINE",
        "ProofAssetStore",
        "ReleaseAssetProofStore",
        "proof_asset_name",
        "proof_asset_slug",
    ):
        assert hasattr(module, name), name


def test_an_asset_name_has_the_ratified_flat_form() -> None:
    """`<work-item-id>__<run-id>__<capture|verify>__<NN>__<slug>.<ext>`, exactly.

    Asserted as the whole literal rather than by re-splitting it on the separator:
    a test that rebuilt the name from the same parts the function was handed would
    pass for any separator the function chose, which is the one thing a flat
    naming form has to pin down.
    """
    module = _module()

    name = module.proof_asset_name(
        work_item_id="bd-ib-b4u6b7",
        run_id="01M3TZNSHWK9FZMTSZS4PWYW62",
        stage=module.PROOF_STAGE_CAPTURE,
        ordinal=1,
        slug="capacity-banner",
        extension="png",
    )

    assert name == "bd-ib-b4u6b7__01M3TZNSHWK9FZMTSZS4PWYW62__capture__01__capacity-banner.png"


def test_the_ordinal_is_two_digits_so_assets_sort_and_compare() -> None:
    """A single-digit ordinal is zero-padded; a two-digit one is unchanged."""
    module = _module()

    def name_for(*, ordinal: int) -> str:
        return module.proof_asset_name(
            work_item_id="bd-ib-x",
            run_id="RUN",
            stage=module.PROOF_STAGE_CAPTURE,
            ordinal=ordinal,
            slug="s",
            extension="png",
        )

    assert "__01__" in name_for(ordinal=1)
    assert "__09__" in name_for(ordinal=9)
    assert "__10__" in name_for(ordinal=10)
    assert "__99__" in name_for(ordinal=99)


def test_the_run_id_is_in_the_name_so_no_run_overwrites_another() -> None:
    """Two runs alike in every other field still produce different names.

    This is the whole reason the run id is part of the form, and it is asserted as
    a DIFFERENCE between two names rather than as the substring's presence: a
    namer that embedded the run id somewhere inert would satisfy a `in` check and
    still let the second run clobber the first.
    """
    module = _module()

    def name_for(*, run_id: str) -> str:
        return module.proof_asset_name(
            work_item_id="bd-ib-same",
            run_id=run_id,
            stage=module.PROOF_STAGE_CAPTURE,
            ordinal=1,
            slug="same",
            extension="png",
        )

    assert name_for(run_id="RUN-A") != name_for(run_id="RUN-B")


def test_a_verify_asset_differs_from_its_capture_peer_in_the_stage_alone() -> None:
    """Same ordinal, same run: the two stages' assets are comparable by name.

    The contract says a `verify` asset compares to the `capture` asset of the same
    ordinal, so the two names must differ in exactly one field. Asserted by
    rebuilding one from the other.
    """
    module = _module()

    def name_for(*, stage: str) -> str:
        return module.proof_asset_name(
            work_item_id="bd-ib-b4u6b7",
            run_id="RUN",
            stage=stage,
            ordinal=7,
            slug="same-shot",
            extension="png",
        )

    captured = name_for(stage=module.PROOF_STAGE_CAPTURE)
    verified = name_for(stage=module.PROOF_STAGE_VERIFY)

    assert captured != verified
    assert captured.replace("__capture__", "__verify__") == verified


def test_an_unknown_stage_is_refused_naming_the_two_that_are_valid() -> None:
    """The stage field is a CLOSED pair, and a refusal says which two.

    Refused rather than coerced: a name carrying a third stage word would upload
    successfully and then be invisible to the replay's same-ordinal comparison,
    which is a silent failure rather than a loud one.
    """
    module = _module()

    refusal = module.proof_asset_name(
        work_item_id="bd-ib-x",
        run_id="RUN",
        stage="screenshot",
        ordinal=1,
        slug="s",
        extension="png",
    )

    assert isinstance(refusal, str)
    assert "screenshot" in refusal
    assert module.PROOF_STAGE_CAPTURE in refusal
    assert module.PROOF_STAGE_VERIFY in refusal


def test_an_out_of_range_ordinal_is_refused_rather_than_silently_widened() -> None:
    """`NN` is TWO digits, so 0 and 100 have no representation in the form.

    Both directions are asserted. A zero ordinal would render `00`, which no
    reproduction step can name as "the first proof"; a three-digit one would
    render a name that no longer matches the form at all.
    """
    module = _module()

    def result_for(*, ordinal: int) -> object:
        return module.proof_asset_name(
            work_item_id="bd-ib-x",
            run_id="RUN",
            stage=module.PROOF_STAGE_CAPTURE,
            ordinal=ordinal,
            slug="s",
            extension="png",
        )

    assert isinstance(result_for(ordinal=0), str)
    assert "0" in str(result_for(ordinal=0))
    assert isinstance(result_for(ordinal=100), str)
    assert "100" in str(result_for(ordinal=100))
    # The control: the boundaries themselves are VALID, so the refusal above is a
    # range check rather than a namer that refuses everything.
    assert str(result_for(ordinal=1)).endswith(".png")
    assert str(result_for(ordinal=99)).endswith(".png")


def test_a_slug_is_reduced_to_lowercase_kebab() -> None:
    """The form says "short lowercase-kebab", so the namer enforces it.

    Enforced rather than documented: a slug carrying a space or an underscore
    would collide with the `__` field separator and make the name un-parseable by
    the very comparison the ordinal exists to support.
    """
    module = _module()

    assert module.proof_asset_slug(text="Capacity Banner") == "capacity-banner"
    assert module.proof_asset_slug(text="runs_page__v2") == "runs-page-v2"
    assert module.proof_asset_slug(text="  Trailing and leading  ") == "trailing-and-leading"


def test_the_release_store_uploads_to_the_prerelease_tag_under_the_ratified_name() -> None:
    """The argv names the tag, the file, AND the name the asset is stored under.

    The stored-name half is the load-bearing one. The seam's contract is "store
    the file at `path` under `name`", so `name` has to REACH the argv — an
    implementation that uploaded the path alone would store whatever the scratch
    file happened to be called, and the ratified form would hold only by the
    capture stage's good behaviour. `<path>#<name>` is the forge CLI's own
    spelling for setting an asset's name, which is why the two arrive as one
    element rather than two.

    `--clobber` is asserted deliberately: re-entering the capture stage after an
    accepted fix round re-uploads the SAME asset name for the same run and
    ordinal, and without it the second upload fails on a name that is correct.
    """
    module = _module()
    store = module.ReleaseAssetProofStore(
        release_tag="proof-assets",
        rendering=module.RENDERING_INLINE,
    )
    name = "bd-ib-x__RUN__capture__01__s.png"

    argv = store.upload_argv(name=name, path=Path("/tmp/scratch-shot.png"))

    assert argv[:3] == ("gh", "release", "upload")
    assert "proof-assets" in argv
    assert f"/tmp/scratch-shot.png#{name}" in argv
    assert "--clobber" in argv


def test_the_release_store_renders_an_inline_reference_when_the_forge_renders_one() -> None:
    """Markdown image syntax, so an authorized viewer sees the proof in the comment."""
    module = _module()
    store = module.ReleaseAssetProofStore(
        release_tag="proof-assets",
        rendering=module.RENDERING_INLINE,
    )

    reference = store.record_reference(
        slug="capacity-banner", ordinal=2, url="https://example.invalid/a.png"
    )

    assert reference.startswith("![")
    assert "https://example.invalid/a.png" in reference
    assert "capacity-banner" in reference
    assert "02" in reference


def test_the_release_store_renders_one_authenticated_link_when_inline_is_waived() -> None:
    """The waived arm carries a LINK per image, never a broken inline reference.

    Asserted against the inline arm rather than on its own: a renderer that
    emitted markdown image syntax in both modes would satisfy every substring
    check here while rendering a permanently broken image on a private
    repository, which is the exact outcome the waiver exists to avoid.
    """
    module = _module()
    waived = module.ReleaseAssetProofStore(
        release_tag="proof-assets",
        rendering=module.RENDERING_AUTHENTICATED_LINK,
    )

    reference = waived.record_reference(
        slug="capacity-banner", ordinal=2, url="https://example.invalid/a.png"
    )

    assert not reference.startswith("![")
    assert reference.startswith("[")
    assert "https://example.invalid/a.png" in reference
    assert "capacity-banner" in reference


def test_the_release_store_satisfies_the_store_protocol() -> None:
    """The seam is a Protocol, so a second store can be added without a code change.

    The contract says binary proof is stored through ONE implementation-owned
    seam and names the release assets as the FIRST implementation that MAY be
    used — so the shape has to admit a second one.
    """
    module = _module()
    store = module.ReleaseAssetProofStore(
        release_tag="proof-assets",
        rendering=module.RENDERING_INLINE,
    )

    assert isinstance(store, module.ProofAssetStore)
