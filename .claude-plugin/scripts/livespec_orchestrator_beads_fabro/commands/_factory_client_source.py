"""How a client-key refusal NAMES the source that supplied the value it refuses.

`bin`, `secret_channel` and `environment` each reach their grade on one field
whichever source wrote them — that identity is the whole of how a registry-backed
factory gets the registry's client settings with no downstream surface changing —
so the refusal is the one place the two sources must be told apart again. The
clause requires it: every validation a committed value receives applies equally
to a registry-supplied one, "naming the registry path as its source".

WHY THE SOURCE CHANGES THE REMEDY AND NOT ONLY THE ATTRIBUTION. Each of the three
refusals ends by telling the operator what to edit, and the two sources are edited
by different people through different mechanisms: a committed value is a line in
the governed repository's own `.livespec.jsonc`, fixed by a commit, and a
registry-supplied one is host state the fleet's provisioning renders, fixed by a
change to the inventory. A refusal naming `dispatcher.factories.<factory>.<key>`
for a registry-supplied value therefore does worse than misattribute: it
prescribes removing a key the repository never wrote, which is an edit that cannot
be made and which, if the operator adds that key in order to remove it, is a
committed override they did not want.

WHY ONE RENDERER FOR ALL THREE. The three refusals are rendered in three modules
reached from two different surfaces, and they say the same thing about source in
three sentences of different shape. Spelled per module, two of them would keep the
committed wording the first time a key gained a registry source — which is exactly
how this defect arose — and nothing in any output would announce it.

WHY THREE FIELDS RATHER THAN ONE RENDERED SENTENCE. The three refusals place the
key, the value and the location differently: the `bin` grade quotes the value, the
`environment` grade quotes none, and the transport grade writes `<key> = <value>`.
A single sentence would have to be one of those shapes, so the other two would
read as the generic one rather than as their own refusal. The fields are the parts
that vary with the source; each refusal still writes its own sentence.

THE DISCRIMINATOR IS `registry_path`, AND `None` IS THE COMMITTED ANSWER rather
than an absent one. A key no source declared is never graded — every one of the
three refusals returns before it reaches here — so the only two states that arrive
are "the committed entry wrote it" and "the registry entry at this path did".
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "ClientKeySource",
    "client_key_source",
]

_COMMITTED_KEY_PREFIX = "dispatcher.factories"
_COMMITTED_REMEDY = "the key"
_REGISTRY_REMEDY = "the key from that registry entry"


@dataclass(frozen=True, kw_only=True)
class ClientKeySource:
    """The three source-dependent parts of one client key's refusal.

    `name` is how the key is named where the refusal states what was declared:
    the full committed path for a committed value, and the bare key for a
    registry-supplied one, whose file is named by `location` instead. Writing
    the committed path in both would send an operator to a key the repository
    never wrote, and writing the bare key in both would stop naming the file a
    committed value is actually in.

    `location` is the empty string for a committed value, so a refusal can
    append it unconditionally. That is what keeps the committed message
    BYTE-IDENTICAL to the one it rendered before any registry existed — the
    clause's "the same refusal, at the same point and with the same effects" is
    about the registry half, and a committed refusal that changed shape to make
    room for the registry half would be a surface this change had no licence to
    move.

    `remedy` is the thing the refusal tells the operator to remove, which is the
    half of the message the source changes most: a committed key is removed by a
    commit and a registry key by the provisioning, and the wording has to admit
    that the second is not in the file the first sentence named.
    """

    name: str
    location: str
    remedy: str


def client_key_source(*, factory: str, key: str, registry_path: str | None) -> ClientKeySource:
    """How to name and remedy one client key, given which source supplied it.

    `factory` is named inside `location` rather than left to the caller, because
    a registry holds an entry per factory and a refusal naming only the file
    would leave an operator reading a fleet-wide inventory for the entry that
    decided this dispatch.
    """
    if registry_path is None:
        return ClientKeySource(
            name=f"{_COMMITTED_KEY_PREFIX}.{factory}.{key}",
            location="",
            remedy=_COMMITTED_REMEDY,
        )
    return ClientKeySource(
        name=key,
        location=f" in factory {factory}'s entry in the factory registry at {registry_path}",
        remedy=_REGISTRY_REMEDY,
    )
