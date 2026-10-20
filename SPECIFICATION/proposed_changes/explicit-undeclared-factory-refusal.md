---
topic: explicit-undeclared-factory-refusal
author: claude-opus-5-5
created_at: 2026-10-20T01:06:05Z
---

## Proposal: An explicit factory selection naming an undeclared factory refuses before claim

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Generalize the existing registry refusal (refuse before claim, never fall back to the ambient local Fabro target) from a declared registry-backed entry to any explicit factory selection, `--factory` or `LIVESPEC_FABRO_FACTORY`, that names no entry of a declared `dispatcher.factories`. The refusal names the offending value and the declared factory names. A repository that declares no factories keeps its implicit default. One Scenario Outline row set inside Scenario 182 makes the refusal gradeable.

### Motivation

Measured 2026-10-20: after orchestrator PR #3330 left dispatcher.factories with only `legacy` and `petri`, a dispatch of bd-ib-7f66ar with `LIVESPEC_FABRO_FACTORY=hp` was not refused. It ran as run 01M5BAYK2NNZ on the LOCAL vps Fabro server: `fabro run` was invoked with no `--server` and connected to 127.0.0.1:32276. The cause is that an undeclared name resolves to an empty entry with no server, the implicit-default behaviour meant for an unconfigured repository. The selection-order clause defines what an undeclared RECORDED pin does but is silent on an undeclared EXPLICIT selection, so this silent misrouting was not forbidden by any clause. The refusal the clause already requires for an unresolvable registry entry is the right behaviour here too. Generalizing it, rather than adding a standalone clause, follows the maintainer's no-overspecification direction, ruled by coordinator R264.

### Proposed Changes

Amend two existing paragraphs of `SPECIFICATION/contracts.md` §"Factory addresses resolved from a host registry", and add one Scenario Outline inside `SPECIFICATION/scenarios.md` §"Scenario 182 — A registry-backed factory resolves its address from the host registry, and an unresolvable one refuses before claim". No heading is added, removed or renamed.

```diff
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@
 The Dispatcher MUST refuse, before any claim, ledger write of any kind (status,
 metadata or comment) or Fabro run creation, a dispatch whose resolved factory
 is registry-backed when the registry file is absent or unreadable, does not
 parse as JSON, has a top-level value that is not an object, has no entry for
-that factory name, or gives that entry no valid `server` string. The refusal
-MUST name the factory and the registry path it read. The Dispatcher MUST NOT
-fall back to the ambient local Fabro target, to `dispatcher.default_factory`,
-or to any other factory in that case. An entry declaring `"registry": true`
+that factory name, or gives that entry no valid `server` string. It MUST
+refuse the same way a dispatch whose EXPLICIT factory selection — `--factory`,
+or a set and non-empty `LIVESPEC_FABRO_FACTORY` — names no entry of a
+declared `dispatcher.factories`. The refusal MUST name the factory and the
+registry path it read, or, for an undeclared explicit selection, the offending
+value and every factory name `dispatcher.factories` declares. The Dispatcher
+MUST NOT fall back to the ambient local Fabro target, to
+`dispatcher.default_factory`, or to any other factory in either case. A
+repository that declares no `dispatcher.factories` keeps its implicit
+single-factory default target. An entry declaring `"registry": true`
@@
-The registry refusal applies only to resolving a DECLARED, registry-backed
-entry. It does not change the factory selection order: an explicit
+The registry refusal applies only to resolving a DECLARED, registry-backed
+entry, and the undeclared-name refusal only to an EXPLICIT selection. Neither
+changes the factory selection order: an explicit
```

```diff
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@
+  Scenario Outline: An explicit selection naming an undeclared factory refuses before any ledger write and never falls back
+    Given dispatcher.factories declares no factory named "hp"
+    When an item is dispatched with <selection>
+    Then the dispatch is refused naming "hp" and every factory name dispatcher.factories declares
+    And the item's status, metadata and comments are unchanged
+    And no Fabro run is created on any server
+
+    Examples:
+      | selection                         |
+      | --factory hp                      |
+      | LIVESPEC_FABRO_FACTORY set to "hp" |
+
   Scenario: Only the selected entry is validated
```

The recorded-pin rule is unchanged: a recorded factory name that `dispatcher.factories` no longer declares is still ignored when no explicit selection is made (Scenario 182's "A recorded pin to an undeclared name still falls back to the default").
