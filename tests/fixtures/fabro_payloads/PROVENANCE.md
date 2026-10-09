# Captured Fabro payloads

## `validate-0.378.0-nightly.0.json` — CAPTURED

Real `fabro validate --json` output, captured 2026-10-09 from the
v0.378.0-nightly.0 binary, run against this repository's own
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`.

| Property | Value |
| --- | --- |
| Command | `fabro validate .claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro --json` |
| Client version | `fabro 0.378.0-nightly.0 (64b9d88 2026-10-06)` |
| Release asset | `fabro-x86_64-unknown-linux-gnu.tar.gz`, tag `v0.378.0-nightly.0` |
| Asset SHA-256 | `457828ee7648ee0b1b88c866efd26cf682479d1aab78cd330b67a7ee7ba34342` |
| Binary SHA-256 | `864df2d94c96d7625a867e21e289e36bd7d1bbd6108f0b8aeb58ce5d1572788e` |
| Exit code | 1 (`× Validation failed`) |

Both digests match the ones research note 006 of `plan/fabro-currency` recorded
for the `hp-candidate` instance, so this is the SAME BINARY the P3 measurements
were taken on, not merely the same version string.

The capture independently reproduces note 006's measurement of this graph:
`valid: false`, 18 nodes, 37 edges, 7 `Warning` diagnostics and 3 `Error`
diagnostics, every error `attractor.condition.syntax` at lines 784, 786 and
787. That is a SECOND INSTRUMENT agreeing with the note — the binary itself
rather than a re-reading of the note — which is the only kind of corroboration
worth recording.

`validate` needs no server and no sandbox, which is why it is capturable in a
factory sandbox at all.

## `inspect` / `events` / terminal `conclusion` — NOT CAPTURED HERE

These are NOT in this directory, and the typed fixtures carrying their shapes
(in `tests/livespec_orchestrator_beads_fabro/commands/
test_fabro_port_payload_fixtures.py`) are TRANSCRIBED from the field sets
research notes 006 and 007 measured on the `hp-candidate` instance, NOT captured
by any run in this repository.

Transcribed rather than captured because all three require a configured Fabro
server plus a COMPLETED SANDBOX RUN, and a factory sandbox has none of the
three things that needs: there is no Docker (so no sandbox provider), the
`hp-candidate` instance on `:32278` is unreachable (no Tailscale — DNS does not
resolve), and a locally started server comes up in `unconfigured — install
mode` demanding an interactive browser install token.

Two field VALUES the notes never measured, recorded here so no later reader
mistakes a placeholder for a measurement:

- `conclusion.failure.detail.category` — note 006 records the KEY and no value.
  The reader therefore passes the string through and classifies on the MESSAGE,
  so it needs no value table; the fixtures carry a representative string.
- the `token.emitted` body's field names — notes 006 and 007 name the EVENT and
  record nothing of its body. The reader accepts several spellings and reports
  `None` when it recognizes none, rather than reporting zero.

Capturing these three against the released build on an operator host is the
host leg described in `.ai/host-captured-proof-replay.md`.
