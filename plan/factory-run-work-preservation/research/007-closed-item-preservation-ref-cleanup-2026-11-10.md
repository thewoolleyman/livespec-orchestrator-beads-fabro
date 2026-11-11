# 007 — Deleting the preservation refs of closed items (2026-11-10)

Session: factory-run-work-preservation plan seat, session 1283cb86, 2026-11-10 about 20:10Z.

## The ruling

The deletion of the old preservation refs was deferred to the maintainer on 2026-11-05, because deleting refs on origin cannot
be undone. Asked again on 2026-11-10, the maintainer ruled, verbatim: "On decision 2, delete only closed items." The ruling is
recorded on epic bd-ib-nckst7 as scope event `frwp-maintainer-ruling-delete-closed-item-refs-2026-11-10`.

## What was deleted

381 refs, removed from origin at 2026-11-10T20:09:39Z by one atomic `git push`, each with a lease on its recorded commit:

- 167 `refs/livespec/preserved-publish/<work-item-id>/<sha>` refs whose work item is closed in this ledger.
- 214 `refs/heads/needs-human/<run-id>` refs whose owning work item is closed, and which no ledger comment on an item that is
  not closed cites.

The full list, with each ref's commit id and owning work item, is
`data/deleted-closed-item-preservation-refs-2026-11-10.tsv`. A deleted commit can be re-pointed by
`git push origin <sha>:<ref>` while the forge still holds the object.

## How a ref's owner was established

- A preserved-publish ref names its work item in the ref path.
- A needs-human ref names a run, not an item. Its owner came from, in order: ledger comments the factory writes on the owning item
  (`livespec-needs-human-cause`, `livespec-preserved-tree`, `livespec-preserve-by-reference`); this host's dispatch journal
  records carrying both the ref and a `work_item_id`; and, for refs neither names, the `Fabro-Run` trailer on the ref's commit,
  mapped to a work item through the dispatch journal.
- A ref was deleted only when exactly one owner was found, that owner was closed, and every other item whose ledger comments cite
  the ref was closed too. Statuses and refs were re-read immediately before the push, and nothing had changed.

## What was kept, and why

Measured on origin after the deletion: 381 needs-human refs and 55 preserved-publish refs remain.

- Owner not closed (blocked, ready, acceptance or backlog): kept, because each may be the only copy a recovery re-dispatch seeds
  from.
- Owner closed, but cited by a ledger comment on an item that is not closed (52 refs; the heaviest citers were bd-ib-qy5wol,
  bd-ib-ynnykl, bd-ib-6tcjfx and bd-ib-acrr56): kept, because that comment cites the ref as evidence.
- Owner not established (130 refs whose commit carries no `Fabro-Run` trailer, 8 whose run maps to no item in this host's
  journal, and 1 with two recorded owners): kept, because the ruling covers closed items only and these cannot be shown to be
  one.
- 20 preserved-publish refs naming work-item ids this ledger does not hold: kept for the same reason.

From here on, bd-ib-efiasj (closed 2026-11-10) deletes an item's work-in-progress and preserved-publish refs when the Dispatcher
closes the item, and a run's needs-human ref when ended-run collection removes that run of a closed item. A kept ref whose run
was collected before bd-ib-efiasj shipped is not reached by that path; repeating this method later, under the same ruling,
clears those once their items close.
