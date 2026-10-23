"""The wall's ordering table must not describe the spec-change-tier row as free.

`pre_dispatch_wall_exit`'s docstring IS the ordering table — its own text says
the order is "data a reader can see at a glance, and adding a refusal is adding
a row" — so a later editor places a new refusal by reading what this table says
each existing row costs. That makes a wrong cost model in it a defect of the
same kind as a wrong constant, and the one asserted here was wrong in both of
the ways that matter.

IT CLAIMED THE ROW SPENDS NOTHING. `spec_change_tier_refusal` ->
`classify_and_hold` -> `classify_item_spec_change_tier` reaches the provider on
every reuse miss — `spec_stated.classify`, whose own docstring states "The model
is reached exactly once, through `run_model`", and then `judge_within_ceiling`
for a non-exempt feature. So the table and
`_spec_change_tier_wall`'s module docstring, which records that "What the ROW
additionally spends is the CLASSIFICATION the clause puts on every dispatch path
— reuse-capped", contradicted each other, and the authoritative surface was the
wrong one.

IT ALSO MISSTATED THE BASIS OF A PROPERTY THAT IS REAL. The row IS fail-closed,
but not because it reaches no provider: `classify_and_hold` re-reads the hold
from the LEDGER after classifying, so a standing record keeps governing an item
whose classification could not run. That sibling's docstring records the
measured regression from reading the fresh outcome instead — "the wall's own
unratified-topic case stopped refusing the moment the row began classifying" —
so an inverted basis recorded here invites exactly that regression back.

BOTH DIRECTIONS ARE ASSERTED, and neither alone is worth anything. The
present-needles alone would pass on a paragraph that states the correction while
the two false claims still sit beside it, which is the self-contradicting state
the finding is about; the absent-needles alone would pass on a paragraph that
says nothing about the row's cost at all.

Asserted against the FUNCTION docstring rather than the file text, because that
is the surface `help()` and an editor hover render, and a needle satisfied by a
comment elsewhere in the module would not be read by the editor this table
exists for. Each needle sits within one physical line, since the prose is
hard-wrapped and a needle straddling a break can only fail while the text says
exactly the right thing.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)

# The row is not a free read: it spends the reuse-capped classification.
_NOT_FREE = "it is NOT a free read"
# The fail-closed property comes from the ledger re-read, not from reaching no
# provider.
_LEDGER_REREAD = "re-reads the hold from the LEDGER"

# The two retracted claims. Each is quoted from the paragraph as it stood, so
# neither can be satisfied by a paraphrase this test would not recognise.
_FREE_READS_CLAIM = "the last of the free reads"
_NO_PROVIDER_CLAIM = "spends no model call and reaches no provider"


def test_the_ordering_table_states_what_the_spec_change_tier_row_spends() -> None:
    """The table must say the row classifies rather than reads for free."""
    docstring = pre_dispatch_wall_exit.__doc__

    assert docstring is not None
    assert _NOT_FREE in docstring
    assert _FREE_READS_CLAIM not in docstring


def test_the_ordering_table_bases_the_row_fail_closed_on_the_ledger_reread() -> None:
    """The table must not rest that property on reaching no provider."""
    docstring = pre_dispatch_wall_exit.__doc__

    assert docstring is not None
    assert _LEDGER_REREAD in docstring
    assert _NO_PROVIDER_CLAIM not in docstring
