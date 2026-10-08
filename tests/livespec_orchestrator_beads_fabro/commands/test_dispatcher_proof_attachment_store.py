"""Tests for the upload leg that swaps an over-allowance proof for a stored asset.

`bd-ib-555xcd`. The decisions this module owns are the ones a publisher cannot see
from its own success: which proofs need attaching, what each asset is called, and
what happens when the store will not take one. Each is exercised here against the
real `attached_assertions` with a stubbed runner, because the alternative — only
testing it through a posting primitive — cannot reach the bounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    NO_GOVERNING_SCENARIO,
    RecordAssertion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import (
    PROOF_ASSET_MAX_ORDINAL,
    PROOF_STAGE_CAPTURE,
    RENDERING_AUTHENTICATED_LINK,
    ReleaseAssetProofStore,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment_store import (
    AttachmentTarget,
    attached_assertions,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    INLINE_PROOF_ALLOWANCE_BYTES,
)

_TAG = "proof-assets"
_SURFACE = "post-host-record"
_OVER = "o" * (INLINE_PROOF_ALLOWANCE_BYTES + 1)
_UNDER = "u" * 32


@dataclass(kw_only=True)
class _Runner:
    """A runner recording uploads, with a settable exit code and stdout."""

    exit_code: int = 0
    stdout: str = ""
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(list(argv))
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


def _assertion(*, text: str, proof: str) -> RecordAssertion:
    return RecordAssertion(
        text=text,
        proof_mode="factory_captured",
        governing_scenario=NO_GOVERNING_SCENARIO,
        steps=("Run it.",),
        proof=proof,
        reproduced=None,
    )


def _target(*, scratch: Path) -> AttachmentTarget:
    return AttachmentTarget(
        work_item_id="bd-ib-555xcd",
        run_id="01M44SESSION",
        stage=PROOF_STAGE_CAPTURE,
        release_tag=_TAG,
        store=ReleaseAssetProofStore(release_tag=_TAG, rendering=RENDERING_AUTHENTICATED_LINK),
        scratch=scratch,
    )


def _attach(
    *, assertions: tuple[RecordAssertion, ...], scratch: Path, runner: _Runner
) -> tuple[tuple[RecordAssertion, ...] | None, str]:
    emitted: list[str] = []
    result = attached_assertions(
        assertions=assertions,
        target=_target(scratch=scratch),
        runner=runner,
        surface=_SURFACE,
        emit=emitted.append,
    )
    return result, "".join(emitted)


def test_an_all_inline_record_never_touches_the_store(tmp_path: Path) -> None:
    """The ordinary record: returned as-is, with no upload and no attachment set.

    The IDENTITY of the returned values is what matters, not just their equality:
    assertion 4 of this item requires an under-budget inline record to publish
    exactly as before, and the cheapest way to guarantee that is for this module to
    hand back the very objects it was given.
    """
    runner = _Runner()
    given = (_assertion(text="One.", proof=_UNDER), _assertion(text="Two.", proof=_UNDER))

    result, emitted = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result == given
    assert all(one.attachment is None for one in result or ())
    assert runner.calls == []
    assert emitted == ""


def test_only_the_over_allowance_proofs_are_attached_and_ordinals_count_attachments(
    tmp_path: Path,
) -> None:
    """Ordinals number the ATTACHMENTS, not the Definition of Done positions.

    The bulky proof here sits at position two of three, and its asset is `01`. The
    alternative would leave `01` and `03` unused, which reads as two assets that
    failed to upload rather than as one that never needed to.
    """
    runner = _Runner()
    given = (
        _assertion(text="First, inline.", proof=_UNDER),
        _assertion(text="Second, bulky.", proof=_OVER),
        _assertion(text="Third, inline.", proof=_UNDER),
    )

    result, _ = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is not None
    assert [one.attachment is None for one in result] == [True, False, True]
    attachment = result[1].attachment
    assert attachment is not None
    assert "__capture__01__" in attachment.name
    assert attachment.size_bytes == len(_OVER.encode("utf-8"))
    # The two inline assertions are handed back unchanged, proof and all.
    assert result[0] == given[0]
    assert result[2] == given[2]


def test_the_stored_bytes_are_the_proof_and_the_digest_describes_them(tmp_path: Path) -> None:
    """What the record states must be what a verifier downloading the asset measures."""
    runner = _Runner()
    given = (_assertion(text="Bulky.", proof=_OVER),)

    result, _ = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is not None
    attachment = result[0].attachment
    assert attachment is not None
    staged = tmp_path / attachment.name
    assert staged.read_text(encoding="utf-8") == _OVER
    assert staged.stat().st_size == attachment.size_bytes
    # The upload names the asset explicitly, so the stored name is the ratified one
    # rather than whatever the scratch file happened to be called.
    assert runner.calls[0][:3] == ["gh", "release", "upload"]
    assert runner.calls[0][-2].endswith(f"#{attachment.name}")


def test_a_url_the_store_reports_is_preferred_over_the_derived_form(tmp_path: Path) -> None:
    """A store that says where it put the bytes knows better than this module does."""
    reported = "https://example.test/releases/download/proof-assets/asset.txt"
    runner = _Runner(stdout=f"uploading...\n{reported}\n")
    given = (_assertion(text="Bulky.", proof=_OVER),)

    result, _ = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is not None
    attachment = result[0].attachment
    assert attachment is not None
    assert attachment.url == reported


def test_a_reported_url_is_found_behind_trailing_chatter(tmp_path: Path) -> None:
    """The scan reads from the END and must SKIP non-URL lines, not stop at them.

    `gh` writes progress and success lines around whatever it reports, so the URL is
    rarely the last line. A scan that gave up on the first non-matching line would
    silently fall through to the derived form — which is a plausible-looking URL,
    so nothing downstream would reveal that the store's own answer was discarded.
    """
    reported = "https://example.test/releases/download/proof-assets/asset.txt"
    runner = _Runner(stdout=f"uploading...\n{reported}\nSuccessfully uploaded 1 asset\ndone\n")
    given = (_assertion(text="Bulky.", proof=_OVER),)

    result, _ = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is not None
    attachment = result[0].attachment
    assert attachment is not None
    assert attachment.url == reported


def test_with_no_reported_url_the_reference_is_derived_from_the_tag_and_name(
    tmp_path: Path,
) -> None:
    """`gh release upload` prints no URL, so the derived form is the ordinary answer."""
    runner = _Runner(stdout="")
    given = (_assertion(text="Bulky.", proof=_OVER),)

    result, _ = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is not None
    attachment = result[0].attachment
    assert attachment is not None
    assert attachment.url == f"releases/download/{_TAG}/{attachment.name}"


def test_an_upload_failure_refuses_naming_the_assertion_the_size_and_the_store(
    tmp_path: Path,
) -> None:
    """The refusal has to be actionable: which proof, how big, and which release."""
    runner = _Runner(exit_code=1)
    given = (_assertion(text="The bulky assertion.", proof=_OVER),)

    result, emitted = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is None
    assert "The bulky assertion." in emitted
    assert str(len(_OVER.encode("utf-8"))) in emitted
    assert str(INLINE_PROOF_ALLOWANCE_BYTES) in emitted
    assert _TAG in emitted
    assert "Nothing was published" in emitted


def test_more_attachments_than_the_ordinal_can_name_refuses_before_any_upload(
    tmp_path: Path,
) -> None:
    """The ratified name carries two digits, so the hundredth asset cannot be named.

    Refused BEFORE any upload rather than on reaching the hundredth: uploading
    ninety-nine assets and then refusing would leave the store carrying most of a
    record that was never publishable.
    """
    runner = _Runner()
    given = tuple(
        _assertion(text=f"Bulky number {index}.", proof=_OVER)
        for index in range(PROOF_ASSET_MAX_ORDINAL + 1)
    )

    result, emitted = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is None
    assert runner.calls == []
    assert str(PROOF_ASSET_MAX_ORDINAL + 1) in emitted
    assert str(PROOF_ASSET_MAX_ORDINAL) in emitted
    assert "smaller proof recipe or a smaller item" in emitted


def test_exactly_the_ordinal_maximum_is_admitted(tmp_path: Path) -> None:
    """The control for the bound above: ninety-nine attachments is NOT refused.

    Without it, the refusal is equally consistent with a real bound and with this
    module refusing any sizeable record, and the two look identical from the output.
    """
    runner = _Runner()
    given = tuple(
        _assertion(text=f"Bulky number {index}.", proof=_OVER)
        for index in range(PROOF_ASSET_MAX_ORDINAL)
    )

    result, emitted = _attach(assertions=given, scratch=tmp_path, runner=runner)

    assert result is not None
    assert len(runner.calls) == PROOF_ASSET_MAX_ORDINAL
    assert emitted == ""
    assert result[-1].attachment is not None
    assert f"__capture__{PROOF_ASSET_MAX_ORDINAL}__" in result[-1].attachment.name
