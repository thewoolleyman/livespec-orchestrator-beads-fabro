# 006 — R1 row-to-disposition map over the 142 audit rows (2026-11-01)

Session: spec-implementation-lockstep resume, Claude Opus 5.5, 2026-11-01 (unattended
overseer resume). This note is the input that the 2026-11-01T02:33:43Z
`livespec-reconciliation-batch-correction` record on epic bd-ib-ax3rds named as missing
from the bd-ib-j6uvkj Host-captured proof: a one-to-one map from each audit row to the
ledger record that disposes it.

## Method

1. Take every row of `data/audit-2026-10-19-open.jsonl` whose `class` is `UNGOVERNED`
   (88) or `PARTIAL` (54): 142 rows, 142 distinct ids.
2. For each id, read the live ledger (`bd show`, `bd comments`) on 2026-11-01.
3. The row's disposition record is the LATEST comment on the item whose first line is one
   of `livespec-governance-reclassification`, `livespec-governance-citation`,
   `livespec-governance-proposal-link`, `livespec-governance-ratified`,
   `livespec-governance-disposition`, `livespec-governance-correction` or
   `livespec-reconciliation-disposition`.
4. A row with no such comment is checked for a closure whose reason names the item that
   absorbed, superseded or duplicated it, or records it as stale against a named ratified
   clause.

The per-row result is `data/r1-row-disposition-map-2026-11-01.jsonl`: id, audit class,
type, live status, the disposing record's kind and timestamp, and a 400-character excerpt.

## Result

Every one of the 142 rows maps to a disposition on the ledger. None is undisposed.

| Disposition record | Rows |
|---|---|
| `livespec-governance-reclassification` (bug, chore or non-functional) | 49 |
| `livespec-governance-citation` (governed by a named ratified clause) | 37 |
| `livespec-governance-ratified` (its linked proposal is now ratified) | 24 |
| closure naming its successor (absorbed, superseded, duplicate or stale) | 13 |
| `livespec-reconciliation-disposition` | 9 |
| `livespec-governance-proposal-link` (pending proposal) | 8 |
| `livespec-governance-disposition` | 2 |
| **Total** | **142** |

The 13 closure rows are bd-ib-5vtqaq, bd-ib-f728, bd-ib-fhjqbv, bd-ib-gajho2,
bd-ib-gapagf, bd-ib-h7iaai, bd-ib-opd3hq, bd-ib-q8ox, bd-ib-tk6e, bd-ib-wc35,
bd-ib-xvhecz, bd-ib-y1b7 and bd-ib-zp2axi. Each close reason names the item or ratified
clause that took its place.

Two linked proposals that the batch-15 records still called pending were checked against
the spec history: `declared-merge-gate-suite-runs-in-the-sandbox` (bd-ib-ckocwc) and
`server-enforced-dispatch-claim-generation` (bd-ib-jjws2) were both ratified with
decision `accept` in v254. Their disposition stands.

## What this does not establish

- It covers Definition-of-Done assertion 1 of bd-ib-j6uvkj (every row carries a
  disposition). It does not check assertion 2 (each unstated feature's proposal names its
  generalization target) or assertion 3 (each batch comment records BCP14 clause and word
  counts).
- The capture is not posted. `post-host-record` resolves its target as the pull request of
  the item's latest merged run, and bd-ib-j6uvkj is a host-routed ledger-triage item that
  has no merged run. How a host-captured proof is posted for an item with no pull request
  is still an open question for whoever closes bd-ib-j6uvkj.
