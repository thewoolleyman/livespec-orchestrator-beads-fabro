"""Stable-format ID generation for work-items.

Per SPECIFICATION/contracts.md §"Work-item beads-issue mapping" and the
beads connection model, every record minted by this plugin is stored as
an issue in the per-repo beads tenant. bd enforces that an issue id's
PREFIX equals the tenant database name (the load-bearing `prefix ==
database` identity rule — see `types.StoreConfig`); an id whose prefix
does not match the tenant is rejected at `bd create` time with a
`prefix mismatch` error.

So ids are minted as `<configured-prefix>-<suffix>`, where `<prefix>` is
the tenant prefix carried on the resolved `StoreConfig` (== the tenant DB
name) and `<suffix>` is the legacy six-char base32 random suffix.

The suffix is six lowercase base32 characters (a-z, 2-7). Randomness
comes from `secrets.token_bytes` so collision probability is negligible
under the append-only discipline; if two skills append records with
identical ids in the same git commit's pre-merge state, git merge will
surface the conflict and the user resolves it like any other race.

The suffix generator is the SHARED `random_id_suffix` lifted into
`livespec_runtime.work_items.reduce` at runtime v0.4.0; only the
backend-coupled PREFIX minting (the `prefix == tenant` identity rule)
stays local here.
"""

from livespec_runtime.work_items.reduce import random_id_suffix


def new_work_item_id(*, prefix: str) -> str:
    """Return a fresh `<prefix>-XXXXXX` work-item identifier.

    `prefix` is the tenant prefix from the resolved `StoreConfig`
    (== the tenant DB name); pass `config.prefix`. The six-char base32
    suffix comes from the shared `random_id_suffix`.
    """
    return f"{prefix}-{random_id_suffix()}"
