# tests/livespec_orchestrator_beads_fabro/effects/

Paired tests for declared effect-boundary modules.

Rules:

- Exercise the expected failure mapping at the effect boundary.
- Keep tests hermetic: no real subprocess, network, beads, or credential access.
- Prefer direct synthetic inputs over live command execution.

