"""Tests for the digest-named attachment a bulky proof travels as.

`bd-ib-555xcd`: a proof whose captured output exceeds the per-assertion inline
allowance is published as an attached asset, and the record carries the asset's
NAME, BYTE SIZE and DIGEST in place of the inline output — so the record stays
under budget without the evidence being truncated or dropped.

WHY ALL THREE FIELDS, AND WHY THE DIGEST IS THE LOAD-BEARING ONE. The name says
where the bytes are and the size says how many to expect, but only the digest says
WHICH BYTES. Without it, an asset that was overwritten, truncated mid-upload, or
re-uploaded by a later fix round would read as the capture's evidence while
carrying something else — and the replay leg would faithfully reproduce the wrong
thing. The acceptance pass and the replay stage therefore fetch the asset and
check its digest against the record, which only works if the record states one.

WHY THE ASSET NAME CARRIES THE DIGEST TOO. The name is what a reader sees first,
and a digest-bearing name makes two different captures of the same assertion
impossible to confuse: the bytes name themselves. It also means a re-upload of
IDENTICAL bytes lands on the identical name, which is what makes a fix round's
re-entry into the capture stage idempotent rather than a clobber of something
subtly different.

WHY THE RENDERED BLOCK IS PLAIN LINES AND NOT A FENCE. A fenced block is what the
INLINE proof uses, and the record reader's verdict scan deliberately ignores
everything inside a fence (it cannot tell a verdict a verifier AUTHORED from one a
proof PRINTED). An attachment reference is authored prose about the proof, not the
proof itself, so it belongs outside a fence where the reader can see it.
"""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    INLINE_PROOF_ALLOWANCE_BYTES,
    measured_bytes,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_proof_attachment.py"
)

_ASSET_NAME = "bd-ib-555xcd__01M44SESSION__host-capture__01__proof-sha256-9f86d081884c7d65.txt"
_ASSET_URL = "https://example.test/releases/download/proof-assets/" + _ASSET_NAME


def _module() -> object:
    """The attachment module, imported inside the test body.

    Imported here rather than at module top so the Red commit fails on the
    `is_file()` assertion below — a genuine assertion about the deliverable —
    rather than dying at collection with `ModuleNotFoundError`, which proves only
    unimportability.
    """
    return importlib.import_module(_MODULE)


def test_the_module_exists_and_exports_the_attachment_surface() -> None:
    assert _MODULE_PATH.is_file()
    attachment = _module()
    assert "ProofAttachment" in attachment.__all__  # pyright: ignore[reportAttributeAccessIssue]
    assert "proof_digest" in attachment.__all__  # pyright: ignore[reportAttributeAccessIssue]
    assert "attached_proof_in" in attachment.__all__  # pyright: ignore[reportAttributeAccessIssue]


def test_the_digest_is_sha256_over_utf8_bytes_and_names_its_algorithm() -> None:
    """A bare hex string would not say WHICH hash, so the algorithm is in the value.

    It is computed over UTF-8 BYTES for the same reason every size here is measured
    in them: the uploaded asset is bytes, and a digest over anything else could not
    be reproduced by `sha256sum` on the downloaded file — which is exactly what the
    replay stage and the acceptance pass do to check it.
    """
    attachment = _module()
    text = "proof output — with a multibyte dash\n"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()

    digest = attachment.proof_digest(text=text)  # pyright: ignore[reportAttributeAccessIssue]

    assert digest == f"sha256:{expected}"


def test_the_asset_slug_carries_the_digest_so_the_bytes_name_themselves() -> None:
    """The slug is derived from the digest, truncated to a readable prefix."""
    attachment = _module()
    digest = attachment.proof_digest(text="a")  # pyright: ignore[reportAttributeAccessIssue]

    slug = attachment.attached_proof_slug(digest=digest)  # pyright: ignore[reportAttributeAccessIssue]

    # Hex of sha256("a") begins ca978112ca1bbdca; the slug carries that prefix.
    assert slug == "proof-sha256-ca978112ca1bbdca"
    # Lowercase-kebab, as the ratified naming form requires of a slug.
    assert slug == slug.casefold()
    assert " " not in slug
    assert "_" not in slug


def test_the_rendered_block_carries_the_name_the_size_and_the_digest() -> None:
    """All three fields the Definition of Done names, each on its own plain line."""
    attachment = _module()
    value = attachment.ProofAttachment(  # pyright: ignore[reportAttributeAccessIssue]
        name=_ASSET_NAME, size_bytes=123456, digest="sha256:9f86d081884c7d65", url=_ASSET_URL
    )

    rendered = value.render()
    lines = rendered.splitlines()

    assert f"Attached proof: {_ASSET_NAME}" in lines
    assert "Attached proof bytes: 123456" in lines
    assert "Attached proof digest: sha256:9f86d081884c7d65" in lines
    assert f"Attached proof asset: {_ASSET_URL}" in lines
    # Plain lines, never bullets: the record reader ignores fenced content and a
    # bullet would not match the label scan either.
    assert not any(one.lstrip().startswith(("-", "*")) for one in lines if one.strip())
    assert "```" not in rendered


def test_the_rendered_block_is_far_smaller_than_the_inline_allowance() -> None:
    """The point of attaching: the record comes back under budget.

    Asserted as a RATIO rather than an absolute, because what matters is that the
    reference cost is negligible against the allowance it replaces — a block that
    cost most of an allowance would attach an enormous proof and still blow the
    budget on a record with several of them.
    """
    attachment = _module()
    value = attachment.ProofAttachment(  # pyright: ignore[reportAttributeAccessIssue]
        name=_ASSET_NAME,
        size_bytes=INLINE_PROOF_ALLOWANCE_BYTES * 40,
        digest=f"sha256:{'f' * 64}",
        url=_ASSET_URL,
    )

    assert measured_bytes(text=value.render()) < INLINE_PROOF_ALLOWANCE_BYTES // 20


def test_a_rendered_attachment_is_read_back_out_of_its_own_section() -> None:
    """The round trip, which is what the digest check downstream depends on.

    The reader is given the attachment's lines inside a realistic assertion section
    rather than alone, so a reader that only worked on an isolated block — and so
    would find nothing in a real record — fails here.
    """
    attachment = _module()
    value = attachment.ProofAttachment(  # pyright: ignore[reportAttributeAccessIssue]
        name=_ASSET_NAME, size_bytes=98765, digest=f"sha256:{'a' * 64}", url=_ASSET_URL
    )
    section = [
        "## Assertion 1 — The listing projects the parent field.",
        "",
        "Proof mode: factory_captured",
        "",
        "Proof:",
        "",
        *value.render().splitlines(),
        "",
        "Reproduced: yes.",
    ]

    read = attachment.attached_proof_in(section=section)  # pyright: ignore[reportAttributeAccessIssue]

    assert read == value


def test_an_inline_fenced_proof_carries_no_attachment() -> None:
    """The ordinary record reads as having no attachment, not as a broken one."""
    attachment = _module()
    section = [
        "## Assertion 1 — The command reports the version.",
        "",
        "Proof:",
        "",
        "```",
        "$ thing --version",
        "0.173.7",
        "```",
        "",
        "Reproduced: yes.",
    ]

    assert attachment.attached_proof_in(section=section) is None  # pyright: ignore[reportAttributeAccessIssue]


def test_an_attachment_reference_inside_a_fence_is_proof_output_not_a_reference() -> None:
    """A proof that PRINTS an earlier record must not be read as carrying its attachment.

    This is the same fail-open the record reader's verdict scan already guards: a
    replay that `cat`s the capture's record prints those very labels, and reading
    them as this assertion's own attachment would point the digest check at another
    assertion's asset — then grade THIS one on whether THAT one's bytes still hash
    correctly.
    """
    attachment = _module()
    section = [
        "## Assertion 1 — The record carries the attachment labels.",
        "",
        "Proof:",
        "",
        "```",
        f"Attached proof: {_ASSET_NAME}",
        "Attached proof bytes: 11",
        f"Attached proof digest: sha256:{'b' * 64}",
        f"Attached proof asset: {_ASSET_URL}",
        "```",
        "",
        "Reproduced: yes.",
    ]

    assert attachment.attached_proof_in(section=section) is None  # pyright: ignore[reportAttributeAccessIssue]


def test_a_partial_attachment_block_is_not_an_attachment() -> None:
    """Three of the four labels is an unusable reference, so it reads as absent.

    Fail-CLOSED on purpose. Returning a half-populated attachment would send the
    digest check after an asset with no digest to compare, and the natural coding
    of that is "no mismatch found" — a pass earned by missing data.
    """
    attachment = _module()
    section = [
        "Proof:",
        "",
        f"Attached proof: {_ASSET_NAME}",
        "Attached proof bytes: 11",
        f"Attached proof asset: {_ASSET_URL}",
    ]

    assert attachment.attached_proof_in(section=section) is None  # pyright: ignore[reportAttributeAccessIssue]


def test_a_non_numeric_byte_size_is_not_an_attachment() -> None:
    """A size that will not parse is a malformed reference, not a zero-byte asset."""
    attachment = _module()
    section = [
        f"Attached proof: {_ASSET_NAME}",
        "Attached proof bytes: not-a-number",
        f"Attached proof digest: sha256:{'c' * 64}",
        f"Attached proof asset: {_ASSET_URL}",
    ]

    assert attachment.attached_proof_in(section=section) is None  # pyright: ignore[reportAttributeAccessIssue]


@given(text=st.text(max_size=300))
def test_the_digest_matches_sha256sum_of_the_uploaded_bytes_for_any_text(*, text: str) -> None:
    """For every proof, not one: the digest is reproducible from the file alone."""
    attachment = _module()

    digest = attachment.proof_digest(text=text)  # pyright: ignore[reportAttributeAccessIssue]

    assert digest == f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


@given(size=st.integers(min_value=0, max_value=10**12), seed=st.text(max_size=60))
def test_render_and_read_round_trip_for_any_size_and_digest(*, size: int, seed: str) -> None:
    """Whatever the size and digest, what is rendered is what is read back."""
    attachment = _module()
    value = attachment.ProofAttachment(  # pyright: ignore[reportAttributeAccessIssue]
        name=_ASSET_NAME,
        size_bytes=size,
        digest=attachment.proof_digest(text=seed),  # pyright: ignore[reportAttributeAccessIssue]
        url=_ASSET_URL,
    )

    assert attachment.attached_proof_in(section=value.render().splitlines()) == value  # pyright: ignore[reportAttributeAccessIssue]


def test_a_nested_fence_does_not_reopen_the_section_to_the_reader() -> None:
    """An inner fence inside an outer one must not be read as CLOSING the outer.

    The renderer sizes a proof's fence one backtick longer than any run the proof
    contains, so a proof that prints Markdown legitimately nests three backticks
    inside four. A reader tracking a mere boolean inverts on the inner delimiter and
    stays inverted — after which the rest of the section reads as PROSE, and the
    attachment labels a later proof happens to print become this assertion's own
    reference.

    Here the labels sit inside the nested region, so a boolean-tracking reader would
    return an attachment and this one must return `None`.
    """
    attachment = _module()
    section = [
        "## Assertion 1 — The proof prints a record that itself carries labels.",
        "",
        "Proof:",
        "",
        "````",
        "$ cat earlier-record.md",
        "```",
        f"Attached proof: {_ASSET_NAME}",
        "Attached proof bytes: 11",
        f"Attached proof digest: sha256:{'d' * 64}",
        f"Attached proof asset: {_ASSET_URL}",
        "```",
        "````",
        "",
        "Reproduced: yes.",
    ]

    assert attachment.attached_proof_in(section=section) is None  # pyright: ignore[reportAttributeAccessIssue]
