# livespec_orchestrator_beads_fabro/effects/

Declared boundary for expected external failures and narrow side-effect
adapters that must not live in pure command policy code.

Rules:

- Keep catches narrow and typed. Return explicit failure objects or raise the
  package's named expected errors; do not catch broad `Exception`.
- Do not put command policy, routing decisions, or user-facing formatting here.
  Callers decide the fallback behavior.
- Keep helpers small enough that a reviewer can see the exact external operation
  being protected.
- Do not read or print secrets.

