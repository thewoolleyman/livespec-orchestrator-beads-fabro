# livespec_orchestrator_beads_fabro/io/

Package-local side-effect surface for terminal I/O used by command supervisors
and hooks that need to preserve stdout/stderr contracts without reaching
directly into process streams at every call site.

Rules:

- Keep helpers tiny and explicit: stdout/stderr text emission only.
- Preserve keyword-only function signatures.
- Do not add persistence, subprocess, network, or beads access here.
