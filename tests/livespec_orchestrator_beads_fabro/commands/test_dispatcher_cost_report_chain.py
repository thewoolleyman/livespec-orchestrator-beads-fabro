"""An unpriceable attempt darkens the WHOLE run cost, and the report says so.

Binds two clauses of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -> "Cost follows every attempt in
a successful fallback run":

- "If any nonzero usage component cannot be priced, the whole run cost is
  unobservable, not a known partial subtotal. ... An unknown model MUST NOT be
  priced as an unrelated default or treated as free."
- and the report's own obligation, which this item's acceptance contract words
  as: the cost report names every priced identity in `model_basis` and reports
  `model_resolved` false when any attempt was unpriceable.

THE THREE WRONG ANSWERS ARE ASSERTED AGAINST INDIVIDUALLY, because each is a
plausible number a reader would accept. A partial subtotal, a default-priced
estimate and zero are all well-formed costs; only an explicit absence is
honest. So the fixtures below give the priceable attempt a KNOWN subtotal and
assert the total is neither that subtotal, nor the default model's price for
the same tokens, nor zero.

THE DEFAULT-MODEL ARM IS STILL ALIVE AND MUST STAY ALIVE, which is why its
control is here too. The legacy host-OTLP path prices a span with no `model`
attribute at the configured default -- that is the real Claude Code shape, and
"a single-candidate run is priced exactly as before this change" depends on it.
What the contract removes is that default for a run whose cost went through the
per-attempt chain path, so the two arms of `build_cost_report_item` are
asserted to disagree deliberately rather than by omission.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    CostObservation,
    chain_cost,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL,
    ModelPrice,
    TokenVector,
    derive_usd_micros,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_report import (
    build_cost_report_item,
    cost_report_summary_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostReport

_WORK_ITEM = "bd-ib-tmgt7v"
_PRICED_MODEL = "priced-model"
_UNPRICED_MODEL = "unpriced-model"
_SECOND_PRICED_MODEL = "second-priced-model"

# 1M input tokens at 7.00 USD per million is 7_000_000 micro-USD. Named so the
# "not a partial subtotal" assertions can name the subtotal they reject.
_PRICED_SUBTOTAL = 7_000_000
_PRICE = ModelPrice(input=7.0, output=0.0, cache_write=0.0, cache_read=0.0)
_SECOND_PRICE = ModelPrice(input=3.0, output=0.0, cache_write=0.0, cache_read=0.0)
_MILLION = 1_000_000


def _price(*, node: str | None, candidate_index: int | None, identity: str) -> ModelPrice | None:
    """A pricer that knows two models and has never heard of the third."""
    del node, candidate_index
    if identity == _PRICED_MODEL:
        return _PRICE
    if identity == _SECOND_PRICED_MODEL:
        return _SECOND_PRICE
    return None


def _observation(
    *, dedup_key: str, identity: str | None, input_tokens: int = _MILLION
) -> CostObservation:
    """One recorded call, with no instant so no window is needed to place it."""
    return CostObservation(
        dedup_key=dedup_key,
        started_at_ms=None,
        model_identity=identity,
        tokens=TokenVector(input=input_tokens, output=0, cache_write=0, cache_read=0),
        node_id=None,
    )


def _cost(*, observations: tuple[CostObservation, ...]) -> object:
    return chain_cost(observations=observations, windows=(), price_of=_price)


def _mixed_cost() -> object:
    """One priceable attempt and one whose emitted identity nothing prices."""
    return _cost(
        observations=(
            _observation(dedup_key="req-priced", identity=_PRICED_MODEL),
            _observation(dedup_key="req-unpriced", identity=_UNPRICED_MODEL),
        )
    )


def test_an_unpriceable_nonzero_component_darkens_the_whole_run_cost() -> None:
    """The total is absent, not the priceable attempt's subtotal."""
    cost = _mixed_cost()

    assert cost.usd_micros is None  # pyright: ignore[reportAttributeAccessIssue]


def test_the_darkened_total_is_not_the_priceable_attempt_s_subtotal() -> None:
    """Rejecting the "known partial subtotal" answer by name.

    The priceable attempt really is worth 7_000_000 micro-USD, which is what
    makes a partial subtotal so convincing: it is a true number about part of
    the run, presented as a number about the run.
    """
    priced_only = _cost(
        observations=(_observation(dedup_key="req-priced", identity=_PRICED_MODEL),)
    )
    assert priced_only.usd_micros == _PRICED_SUBTOTAL  # pyright: ignore[reportAttributeAccessIssue]

    assert _mixed_cost().usd_micros != _PRICED_SUBTOTAL  # pyright: ignore[reportAttributeAccessIssue]


def test_the_darkened_total_is_not_a_default_priced_estimate() -> None:
    """Rejecting the "unrelated default" answer by name.

    The default model would price these two million input tokens perfectly
    happily, and the resulting number would be an observation about a model
    neither attempt ran.
    """
    at_default = derive_usd_micros(
        tokens=TokenVector(input=2 * _MILLION, output=0, cache_write=0, cache_read=0),
        model_id=DEFAULT_DISPATCH_COST_MODEL,
    )
    assert at_default > 0

    assert _mixed_cost().usd_micros != at_default  # pyright: ignore[reportAttributeAccessIssue]


def test_the_darkened_total_is_not_zero() -> None:
    """Rejecting the "treated as free" answer by name."""
    assert _mixed_cost().usd_micros != 0  # pyright: ignore[reportAttributeAccessIssue]


def test_an_attempt_that_emitted_no_model_identity_darkens_the_total() -> None:
    """No identity is not the same as a known-cheap model.

    This is the shape the legacy default-model fallback was written for -- a
    span with no `model` attribute at all -- and it is exactly the shape the
    contract now refuses to price by default.
    """
    cost = _cost(observations=(_observation(dedup_key="req-nameless", identity=None),))

    assert cost.usd_micros is None  # pyright: ignore[reportAttributeAccessIssue]
    assert cost.model_resolved is False  # pyright: ignore[reportAttributeAccessIssue]


def test_an_unpriceable_attempt_that_spent_nothing_does_not_darken_the_total() -> None:
    """ "Any NONZERO usage component" -- an attempt with no usage has none.

    A zero-token attempt has nothing to price, so leaving it unpriced costs the
    run nothing. Darkening the total on it would make a complete, fully
    accounted cost unobservable for an attempt that cannot have changed it.
    """
    cost = _cost(
        observations=(
            _observation(dedup_key="req-priced", identity=_PRICED_MODEL),
            _observation(dedup_key="req-idle", identity=_UNPRICED_MODEL, input_tokens=0),
        )
    )

    assert cost.usd_micros == _PRICED_SUBTOTAL  # pyright: ignore[reportAttributeAccessIssue]
    assert cost.model_resolved is False  # pyright: ignore[reportAttributeAccessIssue]


def test_the_report_item_for_a_darkened_chain_is_unobservable() -> None:
    """The report carries the absence through rather than re-deriving a number."""
    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=None,
        chain=_mixed_cost(),  # pyright: ignore[reportArgumentType]
    )

    assert item.observable is False
    assert item.usd_micros is None


def test_the_report_item_for_a_darkened_chain_is_not_labelled_a_default_estimate() -> None:
    """A darkened chain must not borrow the legacy `default:<model>` basis.

    That label is the legacy path's honest description of a default-priced
    estimate. Reusing it here would say a number was estimated when no number
    exists at all.
    """
    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=None,
        chain=_mixed_cost(),  # pyright: ignore[reportArgumentType]
    )

    assert not item.model_basis.startswith("default:")
    assert DEFAULT_DISPATCH_COST_MODEL not in item.model_basis


def test_the_report_item_names_every_priced_identity_in_model_basis() -> None:
    """ "The cost report names every priced identity in model_basis."""
    cost = _cost(
        observations=(
            _observation(dedup_key="req-a", identity=_PRICED_MODEL),
            _observation(dedup_key="req-b", identity=_SECOND_PRICED_MODEL),
        )
    )

    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=None,
        chain=cost,  # pyright: ignore[reportArgumentType]
    )

    assert _PRICED_MODEL in item.model_basis
    assert _SECOND_PRICED_MODEL in item.model_basis
    assert item.model_resolved is True
    assert item.usd_micros == _PRICED_SUBTOTAL + 3_000_000


def test_the_report_item_reports_model_resolved_false_when_an_attempt_was_unpriceable() -> None:
    """ "...and reports model_resolved false when any attempt was unpriceable."

    Asserted on the arm where a number still exists -- the zero-usage
    unpriceable attempt -- because that is the only case where
    `model_resolved` carries information the `usd_micros` absence does not
    already carry.
    """
    cost = _cost(
        observations=(
            _observation(dedup_key="req-priced", identity=_PRICED_MODEL),
            _observation(dedup_key="req-idle", identity=_UNPRICED_MODEL, input_tokens=0),
        )
    )

    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=None,
        chain=cost,  # pyright: ignore[reportArgumentType]
    )

    assert item.observable is True
    assert item.model_resolved is False
    assert item.usd_micros == _PRICED_SUBTOTAL


def test_the_report_item_carries_the_chain_s_own_token_sums() -> None:
    """The item's token counts come from the attempts that were attributed."""
    cost = _cost(
        observations=(
            _observation(dedup_key="req-a", identity=_PRICED_MODEL, input_tokens=600_000),
            _observation(dedup_key="req-b", identity=_PRICED_MODEL, input_tokens=400_000),
        )
    )

    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=None,
        chain=cost,  # pyright: ignore[reportArgumentType]
    )

    assert item.input_tokens == _MILLION


def test_the_summary_line_for_a_darkened_chain_names_the_pricing_cause() -> None:
    """An unpriceable chain is not the same incident as silence, and reads differently.

    Both postures are "unobservable", but an operator fixing them does
    different things: one adds a catalog entry, the other investigates why no
    telemetry arrived. A single message for both sends every reader to the
    wrong half of that.
    """
    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=None,
        chain=_mixed_cost(),  # pyright: ignore[reportArgumentType]
    )

    line = cost_report_summary_lines(items=(item,))[0]

    assert "unobservable" in line
    assert "price" in line
    assert "no CC token telemetry arrived" not in line


def test_the_summary_line_for_a_silent_run_still_names_missing_telemetry() -> None:
    """The dark-run message is unchanged for a run that accrued nothing at all."""
    item = build_cost_report_item(work_item_id=_WORK_ITEM, report=None)

    line = cost_report_summary_lines(items=(item,))[0]

    assert "unobservable" in line
    assert "no CC token telemetry arrived" in line


def test_the_summary_line_flags_an_observable_chain_with_an_unpriceable_attempt() -> None:
    """A priced total with an unpriced attempt is tagged as such, not as a default.

    The legacy `(<family>-default estimate)` tag would be a false description:
    nothing here was priced at a default.
    """
    cost = _cost(
        observations=(
            _observation(dedup_key="req-priced", identity=_PRICED_MODEL),
            _observation(dedup_key="req-idle", identity=_UNPRICED_MODEL, input_tokens=0),
        )
    )
    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=None,
        chain=cost,  # pyright: ignore[reportArgumentType]
    )

    line = cost_report_summary_lines(items=(item,))[0]

    assert "unpriceable" in line
    assert "default estimate" not in line


def test_the_legacy_default_priced_arm_is_unchanged() -> None:
    """No chain, an unresolved model: still a `default:<model>` estimate.

    The control for "a single-candidate run is priced exactly as before this
    change". The default-model fallback is removed for the chain path only, and
    an arm that had silently lost it would make every ordinary dispatch's cost
    unobservable.
    """
    report = CostReport(
        usd_micros=1_234,
        input_tokens=10,
        output_tokens=5,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model_resolved=False,
        model_basis=DEFAULT_DISPATCH_COST_MODEL,
    )

    item = build_cost_report_item(work_item_id=_WORK_ITEM, report=report)

    assert item.observable is True
    assert item.usd_micros == 1_234
    assert item.model_basis == f"default:{DEFAULT_DISPATCH_COST_MODEL}"
    assert "default estimate" in cost_report_summary_lines(items=(item,))[0]


def test_a_chain_supersedes_a_default_priced_sink_report() -> None:
    """When both are present the CHAIN decides, because it alone has no default.

    The sink report for the same run carries a default-priced number -- it is
    the sum of the per-span prices the receiver derived -- so an implementation
    that preferred it would re-introduce exactly the default the contract
    removes, while still looking like it had consulted the attempts.
    """
    report = CostReport(
        usd_micros=99_999_999,
        input_tokens=2 * _MILLION,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model_resolved=False,
        model_basis=DEFAULT_DISPATCH_COST_MODEL,
    )

    item = build_cost_report_item(
        work_item_id=_WORK_ITEM,
        report=report,
        chain=_mixed_cost(),  # pyright: ignore[reportArgumentType]
    )

    assert item.observable is False
    assert item.usd_micros is None
