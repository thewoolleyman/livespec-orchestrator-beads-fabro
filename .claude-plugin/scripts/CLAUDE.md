# scripts/

The plugin's shared Python surface. `bin/` carries the shebang
wrappers Claude Code invokes; `livespec_orchestrator_beads_fabro/` is the
package those wrappers import; `_vendor/` carries vendored
pure-Python libraries (read-only — no local edits, no PyPI runtime
dependencies per `SPECIFICATION/constraints.md` §"Inherited from
livespec").

Per-subdirectory rules live in the `CLAUDE.md` alongside each
subdirectory. Global, mechanically-checkable rules live in
`SPECIFICATION/constraints.md` (which inherits the full
`livespec/SPECIFICATION/non-functional-requirements.md` rule set
verbatim) — do not duplicate them here.

Cross-cutting rules an agent editing anything under this tree must
respect:

- Keyword-only arguments (`*` separator on every `def`); dataclasses
  are `kw_only=True`. Dunders and third-party-lib destructures are
  the only exemptions.
- Pyright strict mode plus the seven strict-plus diagnostics; Ruff
  rule set; 100% line + branch coverage (paired test required).
- Domain errors vs bugs split: EXPECTED errors flow as
  `livespec_orchestrator_beads_fabro.errors` exceptions caught at the
  supervisor boundary; bugs raise built-in exceptions and propagate
  to the outermost supervisor.
- No relative imports; no banned-API surface (`abc.ABC`, `pickle`,
  etc.); `typing.Protocol` over `abc`.
