# Beads dependency rows and the list-work-items projection

Moved word for word from `AGENTS.md` §"Beads runtime prerequisites" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

**The `dependencies` array is ONE HETEROGENEOUS LIST whose target key DEPENDS ON
THE SURFACE THAT PRINTED IT, and the majority of its rows are not blockers.** On
`bd list --json` a row keys its target `depends_on_id`, with the edge in `type`;
it is not `target` or `to`, so a naive accessor yields `None` and a tenant of
perfectly sound edges reads as a tenant of dangling ones. Worse, six edge types
share the single array.

**Do NOT read that as "the target key is never `id`" — this entry asserted exactly
that until 2026-08-30, and the absolute form is what made it dangerous.** On
`bd show <id> --json` the rows are a DIFFERENT SHAPE: each inlines the whole target
record and keys it `id`, with the edge in `dependency_type`. So an accessor written
from this catalogue's own prescription reaches for `depends_on_id` on a `show` row,
gets `None`, and reports a live edge as dangling — the identical wrong conclusion
this entry exists to prevent, produced by obeying it. Measured 2026-08-30 on this
repo's tenant: all 500 dependency rows in `bd list --status all --json` carry
`depends_on_id`+`type` and none carries `id`+`dependency_type`, while `bd-ib-dbzp`
read through `bd show --json` carries `id`+`dependency_type` and neither
`depends_on_id` nor `type`. Each reading is correct for its own surface; neither
generalizes. The discriminator is the one this catalogue already prescribes for a
surprising empty result — `sorted(row.keys())` before indexing, which settles it in
one line. Measured 2026-08-21 over all 261 dependency
rows in the `livespec-dev-tooling` tenant: `parent-child` 116, `blocks` 93,
`relates-to` 26, `discovered-from` 23, `related` 2, `duplicates` 1 — so **168 of
261 rows (64%) are NOT blockers**, and any filter treating the array as a
blocker list is wrong for the majority of its own input, in the direction of
INVENTING blockers that do not exist. Do not hand-roll the discrimination:
`commands/_plan_child_edges.py` already does it correctly, and
`list-work-items --json`'s `depends_on` projection is **blocks-only** (verified
on `bd-ib-3kolea.2`, whose raw edge list is one `parent-child` plus four
`blocks` and whose projected `depends_on` is exactly those four).

**Prefer `list-work-items --json` to any raw per-item JSON read.** The
projection is DENSE — measured 2026-08-21 on this repo's tenant, 30 keys
present on all 638 records, no `omitempty` sparseness — so trap 2 does not
reach it, and it discards `parent-child` from `depends_on`, so trap 3 does not
either. Since `bd-ib-m36re3` it also carries `parent` and `labels`, which is
what makes the roll-up and acceptance-split questions answerable without
dropping to raw. **One caveat, so this does not become a new trap:** its
`parent` is populated from the native field and the `parent-child` EDGE, so it
inherits the dotted-id blind spot described in the child-enumeration entry
above. It is the right surface for reading an item's parent; it is still NOT a
complete child enumeration. Use `undisposed_plan_child_ids` /
`client.children()` for that.
