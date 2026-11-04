"""A clause the condensation withheld is still a clause a verdict may cite.

Assertion 2 of `bd-ib-a2bfp3`: "An item whose intent a ratified clause states is
still classified `stated`, naming that clause's H2 heading."

THE WORD THAT CARRIES THE ASSERTION IS "STILL" — still, despite the
condensation. `judge` derives the citable clause set from the TREE IT IS
HANDED, and refuses a `stated_by` naming a heading that tree does not carry, so
the condensation decides which verdicts are expressible at all. A clause it
drops is one no verdict may name: a model that correctly reads the ratified
text as stating the item's intent has its answer REFUSED, and every consumer
reports that as an item whose verdict could not be read — never as a clause the
condensation removed. The scan then exits its wire-shape code over a population
it judged correctly.

SO THE DISCRIMINATING CASE IS THE CLAUSE THE RETRIEVAL DID NOT SELECT. A clause
the retrieval DID select is carried whole whatever the condensation does with
the rest, so a test that only ever cites a selected clause passes against a
condensation that drops every unselected one entirely — which is the state this
assertion exists to rule out.

THE REAL-TREE CASE IS UNIVERSALLY QUANTIFIED, over every H2 heading this
repository's five spec files carry, because the assertion is about an item
whose intent SOME ratified clause states and nothing says which. Its own
control is the same citation taken against the UNREDUCED tree: without it the
heading set this module reads would be pinned to nothing, and a reading that
found headings the shared judgement does not recognise would report a
condensation failure for a disagreement about what a heading is.

AND AN INVENTED HEADING MUST STILL BE REFUSED. Carrying every real heading and
carrying everything are the same observation from the citing side; the negative
is what tells them apart, and it is the property `judge` has that makes a
verdict citing a clause nobody can open worse than no verdict at all.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    judge_within_ceiling,
)
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_runtime.spec_stated import judge
from returns.pipeline import is_successful

_SPEC_ROOT = Path(__file__).resolve().parents[3] / "SPECIFICATION"

# The shared judgement's own H2 pattern, restated so this module can read the
# heading inventory independently of the condensation it is checking. The
# unreduced-tree control below is what pins it to the pattern `judge` validates
# against: a heading this finds that the shared judgement does not recognise
# would fail there first.
_H2_HEADING = re.compile(r"^(##[ \t][^\n]*?)[ \t]*$", re.MULTILINE)

_SELECTED = "## The clause the statement is about"
_GOVERNING = "## The clause that states the intent"
_STATEMENT = (
    "Work item bd-ib-a2bfp3\n\nTitle: periwinkle quokka telemetry rehoming\n\n"
    "Description: the periwinkle quokka telemetry is rehomed onto the "
    "quokka transponder."
)

# One file whose GOVERNING clause shares no term with the statement and is far
# too large for the ceiling below, so no retrieval can select it, beside a
# small clause that is all the statement talks about.
_TREE = {
    "contracts.md": (
        "A preamble.\n\n"
        f"{_SELECTED}\n\nThe periwinkle quokka telemetry transponder.\n\n"
        f"{_GOVERNING}\n\n" + ("Filler prose about something else entirely. " * 2500) + "\n"
    )
}
_TIGHT_CEILING = 20_000


@dataclass(kw_only=True)
class _Citing:
    """A `ModelRunner` that answers `stated`, citing the headings it was given."""

    stated_by: tuple[str, ...]
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "kind": "stated",
                "stated_by": list(self.stated_by),
                "generalization_target": None,
                "rationale": "the ratified text states it",
            }
        )


def test_a_clause_the_retrieval_did_not_select_is_still_citable() -> None:
    """The withheld clause's heading is in the prompt and its verdict parses."""
    model = _Citing(stated_by=(_GOVERNING,))

    verdict = judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=model,
        ceiling=_TIGHT_CEILING,
    )

    prompt = model.prompts[0]
    assert len(prompt) < _TIGHT_CEILING
    assert "Filler prose about something else entirely." not in prompt, (
        "the governing clause's BODY is in the prompt, so this measurement is "
        "not about a clause the retrieval withheld"
    )
    assert _GOVERNING in prompt
    assert is_successful(verdict), (
        "the verdict naming the withheld clause was refused, so a model that "
        "read the ratified text correctly is reported as one that could not be read"
    )
    unwrapped = verdict.unwrap()
    assert unwrapped.kind == "stated"
    assert unwrapped.stated_by == (_GOVERNING,)


def test_every_heading_of_this_repositorys_spec_tree_stays_citable() -> None:
    """Whichever clause states an item's intent, naming it still parses."""
    spec_tree = read_current_specification(spec_root=_SPEC_ROOT).files
    headings = tuple(
        heading for path in sorted(spec_tree) for heading in _H2_HEADING.findall(spec_tree[path])
    )
    assert len(headings) > 200, "the heading inventory is too small to be this repository's"

    control = judge(
        spec_tree=spec_tree, statement=_STATEMENT, run_model=_Citing(stated_by=headings)
    )
    assert is_successful(control), (
        "the unreduced tree refuses these headings, so they are not the heading "
        "set the shared judgement recognises and this module is reading the wrong thing"
    )

    verdict = judge_within_ceiling(
        spec_tree=spec_tree, statement=_STATEMENT, run_model=_Citing(stated_by=headings)
    )

    assert is_successful(verdict)
    assert verdict.unwrap().stated_by == headings


def test_an_invented_heading_is_still_refused() -> None:
    """Carrying every real heading is not carrying every heading."""
    verdict = judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=_Citing(stated_by=("## A clause nobody ratified",)),
        ceiling=_TIGHT_CEILING,
    )

    assert not is_successful(verdict)
    assert verdict.failure().field == "stated_by"
