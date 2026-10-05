"""The dispatch-path proof-credential gate over a whole selection.

The IMPURE, selection-level entry point of `SPECIFICATION/contracts.md`'s
proof-credential-projection clause (ratified v114), and the ONE surface both
dispatch paths — the single dispatch and the drain — call before any run exists.

WHY THIS IS NOT IN `_dispatcher_proof_credentials`. That module's own docstring
says every fault IT names is a fault in COMMITTED CONFIGURATION, and it is pure
over a block handed to it. This gate is a different concern on three counts: it
READS the target repository off disk, it grades the Dispatcher's LIVE
ENVIRONMENT — which no committed declaration can decide — and it WRITES the
dispatch journal. Keeping a journal-writing, filesystem-reading selection pass
inside the committed-configuration grader was the drift; the seam was always
there.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials import (
    PROOF_CREDENTIAL_JOURNAL_STAGE,
    environment_refusal,
    proof_credential_journal_record,
    resolved_proof_credentials,
)

__all__: list[str] = [
    "proof_credentials_refusal_for_items",
]


def proof_credentials_refusal_for_items(
    *,
    repo: Path,
    environ: Mapping[str, str],
    wrapper_text: str,
    work_item_ids: Sequence[str],
    journal: object = None,
) -> str | None:
    """The pre-dispatch gate over a whole selection, journaling what it admits.

    The declaration is a REPOSITORY-level fact, so the refusal is computed once
    and returned once: enumerating it per candidate would read as N distinct
    faults when there is one. The journal records, by contrast, ARE per item,
    because each dispatched item gets its own run-configuration overlay and
    therefore its own projection — a reader asking what one item's dispatch
    projected must not be answered with a sibling's.

    A refusal writes NO projection record. Nothing was projected, and a journal
    asserting otherwise would describe a credential reaching a sandbox that was
    never launched; the refusal itself is journaled by the caller that reports it.

    `journal` is optional and is reached through its own `append`, so the gate is
    callable from a hermetic test and from a caller holding none, without a second
    serializer.
    """
    resolved = resolved_proof_credentials(block=dispatcher_block(cwd=repo))
    if isinstance(resolved, str):
        return resolved
    refusal = environment_refusal(resolved=resolved, environ=environ, wrapper_text=wrapper_text)
    if refusal is not None:
        return refusal
    append = getattr(journal, "append", None)
    if append is None:
        return None
    for work_item_id in work_item_ids:
        for credential in resolved.declared:
            append(
                record={
                    "stage": PROOF_CREDENTIAL_JOURNAL_STAGE,
                    "work_item_id": work_item_id,
                    **proof_credential_journal_record(
                        credential=credential, management=resolved.management
                    ),
                }
            )
    return None
