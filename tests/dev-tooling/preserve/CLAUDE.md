# tests/dev-tooling/preserve/

Tests for the preserve-before-cancel scripts under `<repo-root>/dev-tooling/preserve/`.

- `test_preserve_runs.py` — runs the real `preserve_runs.sh` under bash against stub `ssh`, `sudo` and
  `k3s` commands, a local stand-in for the sandbox's `/workspace` and a local bare origin reached
  through `url.<base>.insteadOf`. It proves a container worker node's run is preserved through
  `kubectl exec` with only read commands and never reached over ssh or crictl, and that any other node
  keeps the ssh and crictl route (livespec-dev-tooling-smzkpu, README rule 11).
