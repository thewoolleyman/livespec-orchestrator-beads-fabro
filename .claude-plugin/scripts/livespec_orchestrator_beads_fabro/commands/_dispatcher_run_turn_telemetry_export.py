"""Whether one factory's `run_turn` telemetry reaches a receiver THIS host reads.

The post-dispatch `run_turn` assertion is only meaningful where the marker it
reads could have been written here at all. `run_turn_sink_path` resolves a
HOST-LOCAL state file, and the receiver that writes it runs wherever the
sandbox exports to — so a dispatch whose factory ships its spans to a receiver
on another host leaves this host's sink empty however healthy the pipeline is
(measured 2026-08-22,
`plan/archive/otel-receiver-attr-verification/research/hp-factory-telemetry-measurement-2026-08-22.md`,
section 4). That is why the guard reports UNOBSERVABLE rather than ABSENT for
such a dispatch.

THE QUESTION IS ABOUT THE FACTORY'S OWN TELEMETRY EXPORT, NOT ABOUT ITS NAME.
The guard read `factory != "hp"` until this module existed, which has the whole
answer backwards: every OTHER factory — a Petri-era candidate instance beside
the pinned one on the same host, a second host, a locally served engine — was
reported observable by default, and the one factory that was genuinely
unobservable was recognised only by its spelling. A name test cannot be
re-pointed at a new factory without an edit to the Dispatcher.

So a factory DECLARES where its `run_turn` telemetry goes, under the
per-factory `run_turn_telemetry_export` key. The two values are
self-describing, never numbered, so a reader of a journal record can tell which
one a factory declared without consulting a lookup table:

  "dispatcher_receiver" -- the factory's engine exports `run_turn` spans to the
                           Dispatcher's own OTLP receiver, so the host-local
                           marker is written HERE and the assertion can be made.
  "none"                -- the factory exports no `run_turn` telemetry this
                           host's receiver sees, so the assertion is
                           unobservable rather than unmet.

The key is neither declared API-configurable nor otherwise classified, so it is
committed-only by default per `SPECIFICATION/contracts.md` section "The
declared-API-configurable class" and triggers no console Settings lockstep —
the same disposition as the `secret_channel` key beside it.

AN ABSENT DECLARATION RESOLVES FROM WHETHER THE FACTORY NAMES A SERVER, rather
than defaulting to either literal, because that is what keeps this change from
moving any factory this fleet actually dispatches to. A factory naming a server
names another host, whose receiver and whose sink are its own, so it reads
UNOBSERVABLE — exactly as `hp` read under the name test. A factory naming no
server is the implicit single-factory target, which runs the sandbox on THIS
machine, so it reads OBSERVABLE — exactly as it read when the name test let
every non-`hp` factory through. A factory served on loopback is the one shape
this default calls remote while it is in fact local; it declares
`dispatcher_receiver` and is then read correctly, which is the whole point of
having the key decide.

A REGISTRY-BACKED ENTRY NAMES A SERVER, and the host-factory-registry clause
says so in as many words: every surface whose behaviour depends on whether a
factory is remote must treat one as naming a server. Such an entry carries no
`server` key at all — its address is host state the fleet's provisioning
renders — so a reading that asked for the literal key resolved it as the
implicit single-factory target and reported the factory's sandbox as running on
THIS machine. The guard then asserted that this host's own `run_turn` sink
should carry that factory's spans, and a genuinely healthy remote pipeline read
as an absence.

The test is a DECLARATION question and deliberately not a filesystem one: no
registry is read here, and none needs to be. A registry-backed entry names
another machine whether or not this host can currently resolve which one, so an
unresolvable registry is still remote — and an unresolvable registry is exactly
the moment this gauge must not start claiming that the local sink should hold
that factory's spans.

AN UNRECOGNISED DECLARATION READS AS UNOBSERVABLE RATHER THAN REFUSING. The
guard is a non-blocking post-verdict assertion, so a refusal here would fail an
already-merged dispatch over a telemetry gauge; and the opposite fallback would
let a value this build cannot interpret stand as proof that the receiver saw
the factory's spans. `_dispatcher_secret_channel` refuses its own unrecognised
declaration for the mirror-image reason, and the asymmetry is deliberate: there
the wrong guess persists a credential in an immutable workflow version.

AN UNREADABLE CONFIGURATION READS AS UNOBSERVABLE for the same direction. A
gauge that reported observability when it could not read its own input would
turn "I could not tell" into an absence finding against a dispatch whose
telemetry may have been perfectly healthy.

BUT IT NAMES ITS OWN CAUSE, AND THAT IS WHY THIS RESOLVES TO AN OBSERVATION
RATHER THAN TO A BOOLEAN. Every unobservable arm reads as the same bare `False`
once it is one, so the journal row the sink then writes asserts whichever cause
that literal happens to name — and an unreadable `.livespec.jsonc` was recorded
as `unobservable-remote-factory`, a factory remoteness that was never involved.
That reading is not merely imprecise: a stray comma darkens this gauge for
EVERY factory in the repository, and the one record an operator would use to
find out why points at the factory instead of at the config. This is the defect
`dispatcher_block` raises to stop (its own docstring says so, and says it
REGREW), so the reason is carried through to the record rather than collapsed
here.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._factory_registry import REGISTRY_KEY
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

__all__: list[str] = [
    "RUN_TURN_TELEMETRY_EXPORTS",
    "RUN_TURN_TELEMETRY_EXPORT_DISPATCHER_RECEIVER",
    "RUN_TURN_TELEMETRY_EXPORT_KEY",
    "RUN_TURN_TELEMETRY_EXPORT_NONE",
    "RUN_TURN_UNOBSERVABLE_REMOTE_FACTORY",
    "RUN_TURN_UNOBSERVABLE_UNREADABLE_CONFIGURATION",
    "factory_run_turn_observation",
    "run_turn_telemetry_block",
]

# The per-factory declaration key under `dispatcher.factories.<name>`.
RUN_TURN_TELEMETRY_EXPORT_KEY = "run_turn_telemetry_export"
RUN_TURN_TELEMETRY_EXPORT_DISPATCHER_RECEIVER = "dispatcher_receiver"
RUN_TURN_TELEMETRY_EXPORT_NONE = "none"
RUN_TURN_TELEMETRY_EXPORTS: tuple[str, ...] = (
    RUN_TURN_TELEMETRY_EXPORT_DISPATCHER_RECEIVER,
    RUN_TURN_TELEMETRY_EXPORT_NONE,
)

# The unobservable CAUSES a resolution can report, as the journal records them.
# Self-describing and never numbered, for the same reason the two declaration
# values are: an operator reads the cause off the record without a lookup table.
RUN_TURN_UNOBSERVABLE_REMOTE_FACTORY = "unobservable-remote-factory"
RUN_TURN_UNOBSERVABLE_UNREADABLE_CONFIGURATION = "unobservable-unreadable-configuration"

_FACTORIES_KEY = "factories"
_SERVER_KEY = "server"
_DECLARATION_ABSENT = object()


def run_turn_telemetry_block(*, repo: Path) -> Mapping[str, object] | None:
    """The dispatcher block the declaration is read from; `None` when unreadable.

    Resolved ONCE per post-verdict pass and handed to every record's resolution,
    for the reason the resolve-once discipline exists elsewhere in this tree: a
    second read of the same file cannot be proven to agree with the first, and
    the disagreement would be invisible because both reads produce a well-formed
    block.

    `dispatcher_block` RAISES on a `.livespec.jsonc` that will not parse, and
    this runs in the dispatch tail AFTER the verdict is already computed — so an
    unwrapped read would turn an operator's stray comma into a traceback out of
    a stage whose whole contract is to be fail-open.
    """
    block = attempt(
        action=lambda: dispatcher_block(cwd=repo),
        exceptions=(LivespecConfigUnreadableError,),
    )
    if isinstance(block, AttemptFailure):
        return None
    return block


def factory_run_turn_observation(*, block: Mapping[str, object] | None, factory: str) -> str | None:
    """Why one named factory's `run_turn` export is unobservable here, or `None`.

    `None` is the OBSERVABLE answer, and every other return value is the cause
    the journal row reports — so a caller cannot record an unobservable reading
    without carrying the measurement that produced it, which is the collapse
    this module's docstring describes.
    """
    if block is None:
        return RUN_TURN_UNOBSERVABLE_UNREADABLE_CONFIGURATION
    declared = _declared_export(block=block, factory=factory)
    if declared is _DECLARATION_ABSENT:
        if _names_a_server(block=block, factory=factory):
            return RUN_TURN_UNOBSERVABLE_REMOTE_FACTORY
        return None
    if declared == RUN_TURN_TELEMETRY_EXPORT_DISPATCHER_RECEIVER:
        return None
    return RUN_TURN_UNOBSERVABLE_REMOTE_FACTORY


def _factory_entry(*, block: Mapping[str, object], factory: str) -> Mapping[str, object]:
    """One named `dispatcher.factories` entry, or `{}` when it is not declared.

    An undeclared name is not an error: the implicit single-factory target is
    exactly this case, and it must keep resolving to an entry that names no
    server so an unconfigured repository preserves today's reading.
    """
    factories = block.get(_FACTORIES_KEY)
    if not isinstance(factories, dict):
        return {}
    entry = cast("dict[str, Any]", factories).get(factory)
    if not isinstance(entry, dict):
        return {}
    return cast("dict[str, Any]", entry)


def _declared_export(*, block: Mapping[str, object], factory: str) -> object:
    """One factory's RAW telemetry-export declaration, or the absent sentinel.

    Absence and a malformed value are different answers: only absence falls
    through to the server test. Returning the raw value is what lets the
    resolver read empty, null and non-string declarations as unobservable
    rather than collapsing them into that fallback.
    """
    return _factory_entry(block=block, factory=factory).get(
        RUN_TURN_TELEMETRY_EXPORT_KEY, _DECLARATION_ABSENT
    )


def _names_a_server(*, block: Mapping[str, object], factory: str) -> bool:
    """Whether this entry names a machine other than the one this host runs on.

    A REGISTRY-BACKED entry does, and it is tested FIRST because it carries no
    `server` key for the second test to find — see the module docstring for what
    reading it as the implicit local target cost. `REGISTRY_KEY` is imported from
    the reading rather than respelled here, so a reader spelling the key its
    writer does not cannot silently resolve every registry-backed factory as
    local; and it is tested for `True` exactly as the reading tests it, because
    the clause ratifies one way of declaring the decision and any other spelling
    is an entry that is not registry-backed.
    """
    entry = _factory_entry(block=block, factory=factory)
    if entry.get(REGISTRY_KEY) is True:
        return True
    server = entry.get(_SERVER_KEY)
    return isinstance(server, str) and server.strip() != ""
