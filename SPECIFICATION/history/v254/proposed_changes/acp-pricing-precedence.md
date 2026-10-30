---
topic: acp-pricing-precedence
author: claude-fable-5-1-plan-bd-ib-jxvgq5
created_at: 2026-10-06T00:29:45Z
---

## Proposal: Settle pricing precedence between the model catalog and a per-candidate pricing override

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The ratified text states two incompatible orders for pricing a structured ACP candidate. In section "Agent and model catalogs" one sentence says a per-candidate `pricing` override on a structured entry wins over the catalog value, while a later sentence in the same section and the cost sentence of "Factory-configurable ACP fallback priority" say the model catalog entry the candidate's identity names is consulted FIRST and the per-candidate explicit table SECOND. This proposal keeps the catalog-first order, which is what the merged implementation applies, and rewords the override sentence so the two agree.

### Motivation

Both readings were introduced by the v112 revise pass of plan bd-ib-jxvgq5. The implementing run of bd-ib-tmgt7v (PR 2562) had to choose; it implemented catalog-first because that order governs the cost path its acceptance graded, recorded the alternative reading in the docstring of `_acp_attempt_price.py`, and asked for a ruling. The independent completeness review of the plan (research/completeness-review-pass1-2026-10-04.md, finding B7) recorded the contradiction as uncarried. Work-item bd-ib-6lzk3o carries this filing. Catalog-first is proposed because it is the order the cost clause already requires for every attempt, it makes a committed catalog the single authority a reviewer can read, and an override that silently wins over the catalog is the one direction that lets a per-repository entry misprice a shipped model without any catalog change being visible. The override remains meaningful as the ONLY price for a manual-form candidate with no catalog match, which the cost clause already states.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Agent and model catalogs": replace the sentence that says a per-candidate `pricing` override on a structured entry wins over the catalog value with: "A structured entry MAY carry a per-candidate `pricing` table. The model catalog entry the candidate's identity names is consulted first; the per-candidate table applies only when that identity resolves to no catalog entry, which is the manual-form case and the case of a repository-added model the shipped catalog does not declare. A per-candidate table never overrides a catalog price for an identity the catalog declares." Leave the later sentence in the same section ("price a structured candidate through the model catalog first and a per-candidate override second") and the cost sentence of "Factory-configurable ACP fallback priority" unchanged; they already state the order this proposal adopts. Add one sentence after the catalog-first sentence: "When a repository wants a different price for a catalogued model it changes the catalog through `dispatcher.model_catalog`, never through a per-candidate table." No scenario changes; Scenario 129's rendering cases are unaffected because they do not assert pricing order.
