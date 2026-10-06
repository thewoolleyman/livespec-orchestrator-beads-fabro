"""What a non-built-in catalog entry owes before it may ship: a recorded run.

Binds the verification duty `SPECIFICATION/contracts.md` section "Built-in ACP
node defaults" puts on an entry this factory has not measured. An entry seeded
from the ACP registry is a transcription of someone else's document: it resolves,
renders, journals and prices correctly whether or not the program it names exists,
because a launch distribution is only a string until a sandbox execs it. So the
rule the shipped population answers to is an EXCLUSIVE OR -- an entry either names
the recorded run that verified its launch distribution, or it is withheld from the
catalog -- and nothing in between, because an unverified entry present in the
catalog is exactly the shape that passes every refusal and dies at exec.

THE RULE IS DATA-DRIVEN, WHICH IS WHY `registry_entries_naming_a_verification_run`
IS PUBLIC. A hardcoded admitted list would make "verified" a property of the
author's memory rather than of the entry, and its withholding arm would never run
against the shipped population at all -- so the one case that matters, the
unverified entry, would be untested forever. The function takes a population and
both arms are driven here.

THE TWO MEASURED BUILT-INS ARE EXEMPT, AND THE EXEMPTION IS ASSERTED RATHER THAN
ASSUMED. `claude-acp` and `codex-acp` carry the adapter strings section "Built-in
ACP node defaults" ratifies literally, and every dispatch this factory has ever run
exercised one of them; their verification is the ratification plus the live
golden-master gate, not a run id recorded here. The positive case therefore asserts
they are SHIPPED, because a withholding rule that quietly swallowed them would
satisfy every assertion about the other three.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

# A complete entry in the closed grammar, perturbed by exactly one field per case.
# Built through the real parser rather than the dataclass so the repository-facing
# grammar is exercised by the same cases that exercise the admission rule: an
# operator adding an agent writes this table, not an `AcpAgentEntry`.
_BASE_ENTRY: dict[str, Any] = {
    "display_name": "Probe Agent",
    "account_domain": "probe-allowance",
    "provider": "probe",
    "version": "9.9.9",
    "command": "npx -y probe-acp@9.9.9",
    "mechanism": {"kind": "protocol", "model": "model", "effort": "effort"},
}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _parsed(*, agent_id: str, verification_run: str | None) -> Any:
    """One entry through the real closed-grammar parser, or the refusal it gave.

    `verification_run=None` omits the key entirely, which is the shape of every
    entry written before the field existed and must stay admissible.
    """
    entry = dict(_BASE_ENTRY)
    if verification_run is not None:
        entry["verification_run"] = verification_run
    return _module(name="_acp_agent_entry").parse_agent_entry(
        agent_id=agent_id, entry=entry, key=f"dispatcher.agent_catalog.{agent_id}"
    )


def test_every_shipped_entry_outside_the_measured_built_ins_names_a_verification_run() -> None:
    """The exclusive or, read off the shipped population.

    The built-ins are asserted PRESENT in the same case, because a rule that
    withheld everything would otherwise pass this one unchanged.
    """
    catalog = _module(name="_acp_agent_catalog")
    shipped = catalog.builtin_agent_catalog()
    measured = getattr(catalog, "BUILTIN_AGENT_IDS", frozenset())

    assert measured == frozenset({"claude-acp", "codex-acp"}), measured
    assert measured <= set(shipped), sorted(shipped)
    for agent_id, entry in sorted(shipped.items()):
        if agent_id in measured:
            continue
        assert getattr(entry, "verification_run", "") != "", agent_id


def test_a_registry_entry_naming_no_verification_run_is_withheld_from_the_catalog() -> None:
    """The withholding arm, driven over a population carrying both shapes.

    One verified and one unverified entry go in together, so the result
    discriminates a rule that filters from one that passes everything AND from one
    that passes nothing -- neither of which a single-entry population could tell
    apart.
    """
    catalog = _module(name="_acp_agent_catalog")
    admit = getattr(catalog, "registry_entries_naming_a_verification_run", None)

    assert admit is not None, "the admission rule is not public; both arms are unreachable"
    verified = _parsed(agent_id="verified-acp", verification_run="01MRECORDEDRUN")
    withheld = _parsed(agent_id="withheld-acp", verification_run="")
    assert not isinstance(verified, str), verified
    assert not isinstance(withheld, str), withheld

    admitted = admit(entries=(verified, withheld))

    assert [entry.agent_id for entry in admitted] == ["verified-acp"]


def test_a_repository_entry_may_name_a_verification_run_and_may_omit_it() -> None:
    """The closed grammar carries the field, and an omission is not a refusal.

    An omitted field must stay admissible because the duty is on the SHIPPED
    population: a repository declaring an entry is asserting its own
    responsibility for an adapter this plugin has never seen, and refusing it for
    want of a run id this repository could not have recorded would close the one
    documented route to an agent the catalog does not carry.
    """
    named = _parsed(agent_id="named-acp", verification_run="01MRECORDEDRUN")
    omitted = _parsed(agent_id="omitted-acp", verification_run=None)

    assert not isinstance(named, str), named
    assert not isinstance(omitted, str), omitted
    assert named.verification_run == "01MRECORDEDRUN"
    assert omitted.verification_run == ""


def test_the_verification_run_moves_the_catalog_digest() -> None:
    """The field is part of the snapshot identity, not a comment.

    A digest blind to it would let a re-seed drop every verification record while
    two dispatches went on agreeing that they rendered the same catalog -- so the
    one field that says whether an entry was ever run would be the one field a
    reader could not tell had changed.
    """
    catalog = _module(name="_acp_agent_catalog")
    named = _parsed(agent_id="probe-acp", verification_run="01MRECORDEDRUN")
    bare = _parsed(agent_id="probe-acp", verification_run="")
    assert not isinstance(named, str), named
    assert not isinstance(bare, str), bare

    with_run = catalog.agent_catalog_digest(catalog={"probe-acp": named})
    without_run = catalog.agent_catalog_digest(catalog={"probe-acp": bare})

    assert with_run != without_run
