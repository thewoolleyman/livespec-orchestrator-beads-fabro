"""WHICH source supplies one dispatch's sandbox image, and what the launch says.

`SPECIFICATION/contracts.md` section "Sandbox image source" (Scenario 169): a
dispatch whose resolved factory declares a catalog environment MUST launch its
sandbox from the image that environment declares ON THE FACTORY SERVER, and the
launch overlay MUST NOT substitute `dispatcher.fabro_sandbox_image` for it. The
committed key supplies the image only for a dispatch whose factory names no
catalog environment.

WHY THE DECISION IS A MODULE RATHER THAN A CONDITIONAL AT THE REWRITE. It has
TWO consumers that must agree — the overlay, which rewrites the submitted run
config, and the dispatch-id journal record, which must name the source — and
they sit in different layers. A conditional at the rewrite site would leave the
journal re-deriving the same decision from the same inputs with nothing holding
the two readings together, which is the shape this repository's resolve-once
clause exists to prevent. The TEXT REWRITE lives here too, beside the decision
that chooses it, so "which source supplies the image" and "what the submitted
config therefore declares" cannot drift apart across two files.

WHY THE CATALOG ARM REMOVES THE DECLARATION RATHER THAN WITHHOLDING THE PIN.
`dispatcher.fabro_sandbox_image` is not the only host-side image source: the
committed `workflow.toml` carries its OWN `[environments.<id>.image] docker`
tag, rewritten independently of that key by the dev-tooling release fan-out, and
a SUBMITTED image table is what the server creates the container from. Measured
2026-10-11 on hp-candidate run 01M4PBFW4MP8: `inspect` reported
`sandbox.plan.image` at the catalog's `python-agent-v1.93.5` while the started
container (`sandbox.instance.image`) ran the `python-agent-v1.92.0` the overlay
had written into that table — the plan named one image and the container ran the
other. Withholding the pin alone therefore swaps one host-side source for
another, and the catalog entry is the ONE source only when the submitted config
declares no image whatsoever. The host still never reads the catalog's image, so
it never names it; it names nothing, which is the only honest way to leave the
server's own selection standing.

WHY THE REMOVAL IS TEXTUAL BUT THE VERIFICATION IS A PARSE. The overlay
preserves the committed file's comments and never round-trips it through a
serializer, so the removal has to be a text edit — and TOML spells one table
many ways (`_dispatcher_toml_read`'s docstring enumerates nine), so a line-based
edit only recognizes the spellings its author thought of. An edit that silently
missed one would leave an image declaration standing while reporting success,
which is the instrument-that-cannot-return-a-hit failure this subsection exists
to close. So the result is PARSED, and a declaration that survives the edit
REFUSES the launch rather than submitting a config whose image nobody chose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    toml_section_string,
    toml_section_string_declaration,
)

__all__: list[str] = [
    "CATALOG_ENVIRONMENT_IMAGE_SOURCE",
    "COMMITTED_KEY_IMAGE_SOURCE",
    "SandboxImageSource",
    "resolve_launch_image",
    "sandbox_image_source",
]

# The two source names `contracts.md` section "Sandbox image source" enumerates,
# verbatim. The committed one is spelled as the CONFIGURATION KEY rather than as
# a label, because that is the thing an operator edits when the journal row says
# a launch took its image from there.
CATALOG_ENVIRONMENT_IMAGE_SOURCE = "catalog_environment"
COMMITTED_KEY_IMAGE_SOURCE = "dispatcher.fabro_sandbox_image"


@dataclass(frozen=True, kw_only=True)
class SandboxImageSource:
    """WHERE one launch's sandbox image came from, as the journal records it.

    `environment_id` is populated only on the catalog arm, because only that
    arm has an id to name; the committed key is a single global setting with no
    per-launch identity. The field is still journaled on both arms — an
    explicit null rather than an omission — so "which source supplied this
    image?" is answerable for every launch and not only for the unusual ones.
    """

    source: str
    environment_id: str | None = None


def resolve_launch_image(
    *,
    committed_text: str,
    environment_id: str,
    factory_environment: str | None,
    configured_image: str | None,
) -> str | None:
    """The committed run config with this launch's image declaration resolved.

    Three arms of ONE decision. A dispatch naming a CATALOG environment has the
    declaration REMOVED, so the submitted config names no image and the catalog
    entry is the only thing left that can supply one. A dispatch naming none
    substitutes `dispatcher.fabro_sandbox_image` when that key is set, and
    leaves the committed declaration standing byte for byte when it is not —
    the pre-key posture, which is what an adopter running no pin still gets.

    `factory_environment` is the catalog environment id the resolved factory
    declares, as `factory_environment_id` projects it off the dispatch's
    already-resolved target — None when that factory names none, which is a
    complete answer rather than an unread one.

    None is the UNUSABLE verdict the launch path reports as a refusal, never a
    no-op: a committed declaration the substitution cannot find, or one that
    survives the removal, would launch the sandbox from an image this
    resolution did not choose.
    """
    section = f"environments.{environment_id}.image"
    if factory_environment is not None:
        return _without_image_declaration(text=committed_text, section=section)
    if configured_image is None:
        return committed_text
    return _substituted_image(text=committed_text, section=section, image=configured_image)


def sandbox_image_source(*, factory_environment: str | None) -> SandboxImageSource:
    """The source the launch takes its sandbox image from, named for the journal.

    The SAME `factory_environment` `resolve_launch_image` reads, so the row the
    record carries and the rewrite the overlay performs cannot disagree: one
    input, one pure resolution, two readings of it.

    The committed arm is reported whether or not `dispatcher.fabro_sandbox_image`
    is actually set, because an unset key is still the source this launch
    CONSULTED — the committed workflow's own image table is what it then falls
    through to, which is that key's documented no-op rather than a third source.
    """
    if factory_environment is None:
        return SandboxImageSource(source=COMMITTED_KEY_IMAGE_SOURCE)
    return SandboxImageSource(
        source=CATALOG_ENVIRONMENT_IMAGE_SOURCE, environment_id=factory_environment
    )


def _without_image_declaration(*, text: str, section: str) -> str | None:
    """The text with the environment's image table removed, or None if it stands.

    Nothing to remove is NOT a refusal: the catalog arm's whole requirement is
    that the submitted config declare no image, and a committed config that
    declares none already satisfies it. A declaration that is still there
    AFTERWARDS is the refusal, whatever spelling carried it — see the module
    docstring for why that verification is a parse and not a second matcher.
    """
    header = f"[{section}]"
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if line.strip() == header), None)
    stripped = (
        text
        if start is None
        else "".join(lines[:start] + lines[_next_table_index(lines=lines, after=start) :])
    )
    if toml_section_string_declaration(text=stripped, section=section, key="docker") is not None:
        return None
    return stripped


def _next_table_index(*, lines: list[str], after: int) -> int:
    """Where the table opened at `after` ends: the next header, or end of file.

    A table's body runs to the next header, so removing the header plus that
    body removes the table's comments with it — which is the point, since those
    comments document a pin this launch is deliberately not making.
    """
    return next(
        (index for index in range(after + 1, len(lines)) if lines[index].startswith("[")),
        len(lines),
    )


def _substituted_image(*, text: str, section: str, image: str) -> str | None:
    """The text with the committed `docker` value replaced by `image`.

    Scoped to the canonical bytes the committed workflow carries: a declaration
    the parser reads but this rewrite cannot address is None rather than an
    unrewritten pass, because an unrewritten pass launches the committed image
    under a configuration that asked for another.
    """
    committed_image = toml_section_string(text=text, section=section, key="docker")
    if committed_image is None:
        return None
    needle = f'docker = "{committed_image}"'
    if needle not in text:
        return None
    return text.replace(needle, f"docker = {json.dumps(image)}", 1)
