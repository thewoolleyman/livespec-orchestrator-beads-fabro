# Proof-to-fix renderer probe

`proof_fix_preamble.rs` exercises Fabro's real `build_preamble`, not a
Python reimplementation. It reads the candidate workflow's `fix` fidelity
through Fabro's own graph parser. Both successful proof stages carry an
actionable defect after a green janitor. Their exact findings must survive;
the compact-mode negative control must lose them. A red-janitor control
must retain its failure output.

This is a host-side enemy-unit probe, separate from the hermetic Python
graph/prompt regressions in `tests/integration/test_proof_fix_handoff.py`.
It requires an existing Fabro source checkout matching the factory's reported
commit. Do not change or restart the factory to run it.

Create a temporary Cargo package with this manifest, replacing the absolute
paths with the matching checkout and this fixture's path:

```toml
[package]
name = "proof-fix-preamble-probe"
version = "0.1.0"
edition = "2021"

[dependencies]
fabro-workflow = { path = "/fabro-checkout/lib/crates/fabro-workflow" }
fabro-graphviz = { path = "/fabro-checkout/lib/crates/fabro-graphviz" }

[[bin]]
name = "proof-fix-preamble-probe"
path = "/orchestrator-checkout/tests/fixtures/proof_fix_preamble.rs"
```

From the orchestrator checkout, run:

```sh
cargo run --manifest-path /temporary-package/Cargo.toml -- \
  .claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro
```

The program must print three PASS lines. Point the same binary at the
pre-fix workflow as a second negative control: it must fail at the missing
proof-capture finding, not during parsing or compilation. Record the Fabro
commit and both outcomes in the repair's verification record. This probes
context transport, not whether an LLM actually follows the fix instructions.
