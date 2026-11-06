"""The attention row for a non-closed item that names no claim token after cutover.

Once `dispatcher.claim_tokens` is committed `true`, a claim writer that finds no
current token on a non-closed item writes nothing and reports
`claim-token-missing` (contracts.md, "Stranded claim release" -> "Claim
tokens"). That refusal is correct and it is also silent everywhere else: the
item rests in whatever status it had, no dispatch claims it, no valve moves it,
and nothing about it is stranded, held or aging. This lane is the surface the
same clause requires, one row per such item, so the count of unwritable items
is never something an operator has to infer from writers standing down.

IT COMPOSES NOTHING WHILE THE KEY IS FALSE OR ABSENT, and reads nothing either.
Before the cutover no item names a token and none is refused for it, so a row
per item would report the whole tenant as broken for being unmigrated.

THE HANDOFF IS THE SURVEY FORM OF THE MIGRATION PASS, never the applying one.
The pass writes only while every claim writer of the tenant is stopped, and
only an operator can attest that. A row whose command applied it would let any
consumer that executes handoffs run a migration under live writers. The survey
writes nothing, lists the items, and prints the flag the attestation is.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._store_claim_token_migration import (
    read_work_item_ids_naming_no_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["claim_token_missing_items"]

_MIGRATION_WRAPPER = "migrate_claim_tokens.py"
# What an unreadable setting reads as HERE, and only here. This lane reports; it
# refuses nothing, and `build_attention` has already raised on an unreadable
# `.livespec.jsonc` before reaching it, so the fallback is the quiet one.
_NOT_CUT_OVER = False


def claim_token_missing_items(
    *,
    project_root: Path,
    repo: str,
    config: StoreConfig,
) -> list[AttentionItem]:
    """One row for every non-closed item naming no current token, after cutover."""
    if not unsafe_perform_io(resolve_claim_tokens(cwd=project_root).value_or(_NOT_CUT_OVER)):
        return []
    context = ConformanceContext(project_root=project_root, repo=repo)
    command = _survey_command(project_root=project_root)
    return [
        context.candidate(
            id=f"hygiene:claim-token-missing:{work_item_id}",
            kind="hygiene",
            urgency="high",
            summary=(
                f"Work-item {work_item_id} names no current claim token while "
                "dispatcher.claim_tokens is true, so every claim writer refuses it "
                "with claim-token-missing and writes nothing. Stop every claim writer "
                "of this tenant, then run the claim-token migration pass."
            ),
            source_ref=SourceRef(repo=repo, work_item=work_item_id),
            handoff=Handoff(kind="shell", command=command),
        )
        for work_item_id in read_work_item_ids_naming_no_claim_token(path=config)
    ]


def _survey_command(*, project_root: Path) -> str:
    wrapper = shlex.quote(str(Path(__file__).parents[2] / "bin" / _MIGRATION_WRAPPER))
    return f"python3 {wrapper} --project-root {shlex.quote(str(project_root))}"
