"""The seams a resolved integration contract PROJECTS into, and nothing else.

`SPECIFICATION/contracts.md`, the repository-integration-contract section's
resolve-once-project-everywhere clause, requires the Dispatcher to resolve the
contract exactly ONCE per dispatch, on the host, at plan-build time, and then to
make every seam -- the host janitor argv, the `fabro run` inputs, the prompt
variables, the prepare-step parameters -- a PROJECTION of that one resolved
object. This module is the projection side of that rule: it turns a
`ResolvedIntegrationContract` into what each seam consumes, and it is the only
place that knows what any seam's wire format looks like.

THE SANDBOX RECEIVES VALUES AND NEVER RESOLVES. `CONTRACT_INPUT_NAMES` is the
closed set of fields that cross the host/sandbox boundary; every other schema
field is answered on the host (the master-CI preflight, the host janitor's own
check-suite and bootstrap recipe, the livespec-core clone) and has no business
being restated inside a run. A field crossing that boundary does so as a NAMED
WORKFLOW INPUT, because the three sandbox-side consumers -- the `--input` pairs
themselves, the node prompts, and the `[[run.prepare.steps]]` scripts -- all read
`inputs.<name>` and therefore all read ONE value. That is what makes them
projections of the same object rather than three restatements of it.

AN INPUT THE WORKFLOW DOES NOT DECLARE IS NEVER SENT. fabro REJECTS an `--input`
name the run config does not declare, so the rendering is INTERSECTED with what
the dispatched workflow actually declares -- the same discipline
`_dispatcher_acp_nodes` already keeps for adapter inputs, and for the same
reason: the set of inputs that exist is a property of the DISPATCHED workflow,
not of this plugin's build, so a target still carrying an older payload is sent
what it can receive and nothing more.

COMMAND-SHAPED VALUES CROSS AS ONE SHELL WORD-LIST. The contract holds argv
tuples so nothing downstream re-tokenizes; a workflow input is a scalar, so the
tuple is rendered with `shlex.join` at this one seam and read back by a
`[[run.prepare.steps]]` script that is itself a shell command line. The join
happens HERE rather than at each consumer for the same reason the split happens
once in the resolver.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_conformance_premises import (
    conformance_field,
    conformance_mode,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    ResolvedIntegrationContract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_resolver import (
    Declared,
    Defective,
    FleetDefault,
    IntegrationResolution,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    CONFORMANCE_HOOK_INSTALL_FIELD,
    CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD,
    CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD,
    DEFAULT_BRANCH_FIELD,
    MERGE_MODE_FIELD,
    PREPARE_TOOLCHAIN_LEFTHOOK_FIELD,
    PREPARE_TOOLCHAIN_MISE_FIELD,
    SANDBOX_CHECK_SUITE_FIELD,
    SANDBOX_EXEMPT_MARKER_FIELD,
)

__all__: list[str] = [
    "CONTRACT_INPUT_NAMES",
    "MERGE_METHOD_FLAGS",
    "ContractPrepareParameters",
    "contract_prepare_parameters",
    "contract_prompt_variables",
    "contract_run_inputs",
    "contract_workflow_inputs",
    "integration_contract_journal_record",
    "merge_method_flag",
    "workflow_declared_inputs",
]

# The CLOSED set of fields that cross into the sandbox, and the workflow-input
# name each crosses as. Keyed by the schema field's own attribute so the mapping
# cannot name a point the schema does not carry; the input names match the
# attributes deliberately, because a rendered input and the `inputs.*` token a
# prompt or prepare step reads have to be the same word for the ratified
# seam-equivalence check to be able to compare the two sets at all.
CONTRACT_INPUT_NAMES: Mapping[str, str] = {
    SANDBOX_CHECK_SUITE_FIELD.attribute: "sandbox_check_suite",
    PREPARE_TOOLCHAIN_MISE_FIELD.attribute: "prepare_toolchain_mise",
    PREPARE_TOOLCHAIN_LEFTHOOK_FIELD.attribute: "prepare_toolchain_lefthook",
    CONFORMANCE_HOOK_INSTALL_FIELD.attribute: "conformance_hook_install",
    CONFORMANCE_VERIFY_COMMIT_REFUSE_HOOK_FIELD.attribute: (
        "conformance_verify_commit_refuse_hook"
    ),
    CONFORMANCE_VERIFY_PLUGIN_RESOLUTION_FIELD.attribute: ("conformance_verify_plugin_resolution"),
    SANDBOX_EXEMPT_MARKER_FIELD.attribute: "sandbox_exempt_marker",
    DEFAULT_BRANCH_FIELD.attribute: "default_branch",
    MERGE_MODE_FIELD.attribute: "merge_mode",
}

# How each admitted `dispatcher.merge_mode` value spells itself as the `gh pr
# merge` METHOD flag. The mapping is total over the schema's admitted set, so a
# value that resolved at all has a flag; an unresolvable merge mode carries the
# name sentinel instead and is refused rather than defaulted, on the same
# reasoning every other unresolved point records.
MERGE_METHOD_FLAGS: Mapping[str, str] = {
    "rebase": "--rebase",
    "squash": "--squash",
}

# `[run.inputs]` and its body, up to the next table header. A full TOML parser is
# unavailable on the pinned Python (tomllib is 3.11+; the family vendors no TOML
# library) and the run config is repo-owned with a stable shape, so a
# section-scoped regex is sufficient and dependency-free -- the same reasoning
# `_dispatcher_overlay._toml_section_string` records.
_RUN_INPUTS_RE = re.compile(r"(?ms)^\[run\.inputs\][ \t]*\r?$(?P<body>.*?)(?=^\[|\Z)")
# A declaration's default is a BASIC string, a LITERAL string, or a bare TOML
# scalar, and all three arms earn their place.
#
# The bare arm matters because two of the three per-item policy inputs are not
# strings -- the review-fix visit cap is an integer and the merge hold is a
# boolean -- and a string-only scan cannot see either. That is the "instrument
# incapable of returning a hit" failure: the seam-equivalence check's obligation
# to classify EVERY declared input would read clean over inputs it could never
# have found, and a variant that dropped one of them would pass vacuously.
#
# The LITERAL arm (`'...'`) matters for the same reason, one spelling later. A
# structured ACP adapter default is a JSON object, so it carries double quotes of
# its own and the basic arm -- which cannot hold one -- is unavailable to it. TOML
# literal strings take no escapes, so the JSON reads exactly as written. WITHOUT
# this arm such a value does not go unseen, which would at least be loud: it falls
# through to the BARE arm and is reported WITH ITS SURROUNDING QUOTES, a plausible
# string that no consumer can parse and that names no fault.
# Written VERBOSE and as ONE literal deliberately: the three arms need both
# quote characters, so neither a single-quoted nor a double-quoted one-line
# literal can hold them without escaping, and splitting it would be an implicit
# string concatenation (which pyright strict forbids) or an explicit one (which
# ruff's ISC003 forbids). VERBOSE ignores whitespace OUTSIDE character classes,
# so every `[ \t]` and `[^#\r\n]` below is preserved exactly as written.
_INPUT_ASSIGNMENT_RE = re.compile(
    r"""
    ^(?P<key>\w+)[ \t]*=[ \t]*
    (?:
        "(?P<quoted>[^"]*)"
      | '(?P<literal>[^']*)'
      | (?P<bare>[^\s"'#][^#\r\n]*?)
    )
    [ \t]*\r?$
    """,
    re.MULTILINE | re.VERBOSE,
)


@dataclass(frozen=True, kw_only=True)
class ContractPrepareParameters:
    """The integration values the sandbox's `[[run.prepare.steps]]` consume.

    Named as PARAMETERS rather than as rendered scripts because the scripts
    themselves live in the dispatched workflow payload, which templates
    `inputs.*`; this is the value side of that template, projected from the one
    resolved contract so the prepare chain and the node prompts cannot disagree
    about which check-suite or which exemption marker this repository uses.

    A toolchain premise an adopter does not carry resolves to the explicit
    no-op -- the empty argv -- which is a VALUE the ratified
    factory-sandbox-toolchain-disposition clause defines, never an absence to be
    inferred from silence. The three CONFORMANCE premises carry the same no-op
    for the same reason, one step further along: they are the prepare steps the
    ratified baseline conformance gate names, and an adopter that carries none of
    this fleet's tooling has to be able to say so as a value.
    """

    sandbox_exempt_marker: str
    toolchain_mise: tuple[str, ...]
    toolchain_lefthook: tuple[str, ...]
    conformance_hook_install: tuple[str, ...]
    conformance_verify_commit_refuse_hook: tuple[str, ...]
    conformance_verify_plugin_resolution: tuple[str, ...]


def contract_prompt_variables(*, resolved: ResolvedIntegrationContract) -> Mapping[str, str]:
    """Project the sandbox-facing fields as the variables a run renders from.

    ONE mapping, consumed three ways: `contract_run_inputs` renders it as the
    `fabro run --input` pairs, fabro binds those pairs to the `inputs.*` tokens
    the node prompts template, and the same tokens are what the prepare-step
    scripts read. Any seam that wants one of these values reads it from here
    rather than from configuration, which is the whole of the resolve-once rule
    expressed as a function.
    """
    contract = resolved.contract
    return {
        name: _scalar(value=getattr(contract, attribute))
        for attribute, name in CONTRACT_INPUT_NAMES.items()
    }


def contract_run_inputs(
    *, resolved: ResolvedIntegrationContract, declared: Collection[str]
) -> tuple[str, ...]:
    """Render the `--input name=value` pairs this dispatch's workflow can receive.

    INTERSECTED with `declared` -- the input names the dispatched run config
    actually declares -- because fabro rejects an `--input` naming an input the
    workflow does not declare. A workflow that declares none of these fields
    receives none of them and runs on its own committed literals exactly as
    before, so supplying the values is separable from the payload edit that
    templates them.
    """
    variables = contract_prompt_variables(resolved=resolved)
    return tuple(f"{name}={variables[name]}" for name in sorted(variables) if name in set(declared))


def contract_prepare_parameters(
    *, resolved: ResolvedIntegrationContract
) -> ContractPrepareParameters:
    """Project the prepare chain's parameters off the one resolved contract."""
    contract = resolved.contract
    return ContractPrepareParameters(
        sandbox_exempt_marker=contract.sandbox_exempt_marker,
        toolchain_mise=contract.prepare_toolchain_mise,
        toolchain_lefthook=contract.prepare_toolchain_lefthook,
        conformance_hook_install=contract.conformance_hook_install,
        conformance_verify_commit_refuse_hook=contract.conformance_verify_commit_refuse_hook,
        conformance_verify_plugin_resolution=contract.conformance_verify_plugin_resolution,
    )


def merge_method_flag(*, resolved: ResolvedIntegrationContract) -> str | None:
    """The `gh pr merge` METHOD flag the resolved merge mode projects to; None when unresolved.

    None is not "use the fleet default": it is the caller's cue that
    `dispatcher.merge_mode` resolved NOTHING, which the auto-merge argv reports
    rather than papering over with a strategy this repository never chose. A
    resolved mode always maps, because the schema admits only members of
    `MERGE_METHOD_FLAGS`.
    """
    return MERGE_METHOD_FLAGS.get(resolved.contract.merge_mode)


def contract_workflow_inputs(*, committed_text: str) -> frozenset[str]:
    """The CONTRACT input names a committed run config declares.

    Filtered to `CONTRACT_INPUT_NAMES` so the adapter inputs and the three
    per-item policy inputs sharing the `[run.inputs]` table are not mistaken for
    integration points; an absent table declares nothing.
    """
    names = frozenset(CONTRACT_INPUT_NAMES.values())
    return frozenset(workflow_declared_inputs(committed_text=committed_text)) & names


def workflow_declared_inputs(*, committed_text: str) -> Mapping[str, str]:
    """Every input a committed run config's `[run.inputs]` table declares, with its default.

    The generic scan behind both input-name questions the dispatch path asks --
    which adapter inputs exist, and which integration inputs exist. It lives in
    ONE place because two copies of a `[run.inputs]` regex is exactly how the
    two questions would come to disagree about what a payload declares.

    A bare scalar default -- an integer, a boolean -- is reported as the TEXT the
    payload wrote, because every consumer of this mapping asks about names or
    compares defaults as written; none of them types the value.
    """
    section = _RUN_INPUTS_RE.search(committed_text)
    if section is None:
        return {}
    return {
        match.group("key"): _declared_default(match=match)
        for match in _INPUT_ASSIGNMENT_RE.finditer(section.group("body"))
    }


def _declared_default(*, match: re.Match[str]) -> str:
    """One declaration's default, whichever of the three value arms matched.

    The two string arms are checked before the bare one because only one arm
    can match at a time: an unmatched arm is `None`, and a string default is
    legitimately the EMPTY string, so the arms are told apart by `is None`
    rather than by truthiness.
    """
    quoted = match.group("quoted")
    if quoted is not None:
        return quoted
    literal = match.group("literal")
    return match.group("bare") if literal is None else literal


def integration_contract_journal_record(
    *, resolved: ResolvedIntegrationContract
) -> dict[str, object]:
    """Project the resolved contract for the dispatch record.

    Every field reports the VALUE the run will use plus the ARM that produced it
    -- declared, fleet-default, or defective -- so a reader can tell an adopter's
    own declaration from the fleet convention without re-deriving the
    resolution. `defects` is restated as its own list because a reader asking
    "what was wrong with this repository at dispatch time" should not have to
    scan every field to find out.

    A CONFORMANCE premise additionally reports its MODE, because its value alone
    cannot answer the question a reader of this record actually has: the explicit
    no-op and the absent key resolve to the same empty argv, and only the mode
    beside the arm distinguishes a skip the adopter chose from one nobody wrote.
    """
    return {
        "integration_contract": {
            "schema_version": resolved.contract.schema_version,
            "fields": {
                attribute: _field_record(attribute=attribute, resolution=resolution)
                for attribute, resolution in sorted(resolved.resolutions.items())
            },
            "defects": [
                {"key": defect.key, "reason": defect.reason} for defect in resolved.defects
            ],
        }
    }


def _field_record(*, attribute: str, resolution: IntegrationResolution) -> dict[str, object]:
    """One field's dispatch-record entry; a conformance premise also reports its mode."""
    record: dict[str, object] = {
        "key": resolution.key,
        "arm": _arm(resolution=resolution),
        "value": _resolution_value(resolution=resolution),
    }
    field = conformance_field(attribute=attribute)
    if field is not None:
        record["mode"] = conformance_mode(field=field, resolution=resolution)
    return record


def _arm(*, resolution: IntegrationResolution) -> str:
    if isinstance(resolution, Declared):
        return "declared"
    if isinstance(resolution, FleetDefault):
        return "fleet-default"
    return "defective"


def _resolution_value(*, resolution: IntegrationResolution) -> str | None:
    """A resolution's value as one scalar; None where it resolved nothing."""
    if isinstance(resolution, Defective):
        return None
    return _scalar(value=resolution.value)


def _scalar(*, value: str | tuple[str, ...]) -> str:
    """One integration value as the single string a workflow input carries."""
    return value if isinstance(value, str) else shlex.join(value)
