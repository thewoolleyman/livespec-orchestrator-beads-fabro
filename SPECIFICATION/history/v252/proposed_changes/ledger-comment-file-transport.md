---
topic: ledger-comment-file-transport
author: claude-opus-5-5
created_at: 2026-10-28T01:57:53Z
---

## Proposal: Every ledger comment reaches bd through a file, never as one argv element

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Under '## Beads connection model', a new bullet: every ledger comment the plugin writes through the live backend reaches bd through --file and its body is never a command-line argument; a comment reads back byte-identical whatever its length within the store's limit, and a plan record at the 196608-byte proof record budget is written to its plan epic as one comment that reads back byte-identical.

### Motivation

Spec-first for bd-ib-jiwoij, routed URGENT by petri-factory-on-gmktec: on build 0.246.0 the pre-dispatch Definition-of-Done judgement posts its verdict through add_comment as `bd comment <id> <body>`, and for long-history items the body exceeds Linux's 131072-byte MAX_ARG_STRLEN, so the dispatcher dies with 'Argument list too long: bd' before claiming (bd-ib-jp2qr2 and bd-ib-j5cwkj are held). The plan-record path admits 196608-byte records it cannot write. The item's screen refused it because no ratified H2 states ledger-comment transport.

### Proposed Changes

No `## ` heading changes, so `tests/heading-coverage.json` needs no co-edit. The diff below is the whole change.

```diff
diff --git a/SPECIFICATION/contracts.md b/SPECIFICATION/contracts.md
index 1a720e1e7..a11316c0a 100644
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -9312,6 +9312,15 @@ retired in livespec core's research consolidation):
   that would let that registration succeed. A `bd` call made through the
   plugin from the repository root MUST NOT print an `auto-backup failed`
   warning. Scenario 181 in `scenarios.md` exercises this bullet.
+- **Comment bodies travel by file.** Every ledger comment the plugin writes
+  through the live backend MUST reach `bd` through a file (`--file`), and its
+  body MUST NOT be passed as a command-line argument, because the
+  kernel caps one argument at a length (131072 bytes on Linux) far below what
+  the store holds. A comment's text MUST read back byte-identical through
+  `bd comments <id> --json` whatever its length within the store's own limit;
+  in particular a plan record at the 196608-byte proof record budget MUST be
+  written to its plan epic as one ledger comment that reads back
+  byte-identical.
 - **In-memory fake backend.** For hermetic CI and the
   no-live-connection runtime fallback, the plugin selects an in-memory
   fake backend (via `LIVESPEC_BEADS_FAKE=1` or the `connection.fake`
```

