"""Tests for host-side `inputs.*` substitution in the run-config overlay.

WHY THIS SURFACE EXISTS. The committed implement-work-item payload templates
its toolchain and conformance prepare steps as `{{ inputs.<name> }}`, on the
premise that the engine renders them from the `fabro run --input` pairs. The
pinned engine (fabro 0.254.0) does NOT: it renders `inputs.*` in graph node
attributes at run-create time and leaves `run.prepare` commands verbatim, so
every dispatch reached the shell as a literal `{{` and died at exit 127 before
any agent node ran.

Proven in isolation before this fix: one throwaway graph, one templated prepare
command and one templated node script reading the SAME input, created with
`fabro create --input probe_value=RENDERED_FROM_FLAG` and never started — the
node held the value, the prepare command still held the token.

The Dispatcher already materializes an uncommitted per-dispatch overlay of the
committed run config and rewrites it several ways. Substituting the resolved
contract values into that text is one more rewrite in the same place, against
the SAME already-resolved `ResolvedIntegrationContract` the `--input` pairs are
rendered from, so the two cannot drift apart. It needs no engine change.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    render_run_config_overlay,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
    "\n"
    "[[run.prepare.steps]]\n"
    'script = "set -- {{ inputs.prepare_toolchain_mise }}; test $# -eq 0 || \\"$@\\""\n'
    "\n"
    "[[run.prepare.steps]]\n"
    'script = "git config {{ inputs.sandbox_exempt_marker }} true"\n'
)


def _render(*, tmp_path: Path, prepare_inputs: dict[str, str] | None) -> str:
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        prepare_inputs=prepare_inputs,
    )
    assert rendered is not None
    return rendered


def test_prepare_input_tokens_are_substituted_host_side(tmp_path: Path) -> None:
    """Every declared `inputs.*` token is replaced by its resolved value.

    The load-bearing assertion is the absence of `{{`: a token that survives
    into the overlay reaches bash verbatim and kills the run in setup.
    """
    rendered = _render(
        tmp_path=tmp_path,
        prepare_inputs={
            "prepare_toolchain_mise": "sh -c 'mise trust && mise install --quiet'",
            "sandbox_exempt_marker": "livespec.sandboxExempt",
        },
    )
    assert "{{" not in rendered
    assert "sh -c 'mise trust && mise install --quiet'" in rendered
    assert "git config livespec.sandboxExempt true" in rendered


def test_the_empty_no_op_substitutes_as_the_empty_word_list(tmp_path: Path) -> None:
    """The ratified no-op renders as nothing, leaving a clean `set --` no-op.

    An adopter declaring no toolchain premise resolves to the empty argv. The
    payload's `set -- <value>; test $# -eq 0 || "$@"` idiom then takes the
    zero-argument branch, which is a clean exit rather than a syntax error.
    """
    rendered = _render(
        tmp_path=tmp_path,
        prepare_inputs={"prepare_toolchain_mise": "", "sandbox_exempt_marker": "x"},
    )
    assert "{{" not in rendered
    assert 'script = "set -- ; test $# -eq 0 || \\"$@\\""' in rendered


def test_an_unmapped_token_is_left_alone(tmp_path: Path) -> None:
    """A token with no resolved value survives, so the gap stays loud.

    Blanking an unknown token would silently turn an unresolved premise into a
    no-op — the same silent-gutting failure mode that made the sibling defect
    dangerous. Leaving it means the run still fails visibly at that step.
    """
    rendered = _render(tmp_path=tmp_path, prepare_inputs={"sandbox_exempt_marker": "marker"})
    assert "{{ inputs.prepare_toolchain_mise }}" in rendered
    assert "git config marker true" in rendered


def test_substituted_values_are_escaped_for_the_toml_string_they_sit_in(
    tmp_path: Path,
) -> None:
    """A value carrying a quote or a backslash must not break the overlay's TOML.

    The tokens sit inside TOML basic strings. Contract values arrive as one
    shell word-list from `shlex.join`, and `shlex.quote` emits the `\'"\'"\'`
    sandwich for an embedded apostrophe — which carries double quotes. Written
    raw, one of those would terminate the TOML string early and make the whole
    overlay unparseable, turning a per-repo command into a dispatch-wide
    failure.
    """
    quoted = 'sh -c "echo hi"'
    backslashed = "back\\slash"
    rendered = _render(
        tmp_path=tmp_path,
        prepare_inputs={
            "prepare_toolchain_mise": quoted,
            "sandbox_exempt_marker": backslashed,
        },
    )
    assert "{{" not in rendered
    marker_line = next(
        line for line in rendered.splitlines() if line.startswith('script = "git config')
    )
    assert marker_line == 'script = "git config back\\\\slash true"'
    mise_line = next(line for line in rendered.splitlines() if line.startswith('script = "set --'))
    assert 'sh -c \\"echo hi\\"' in mise_line
    # And the whole overlay still parses as TOML, which is the point of escaping.
    # `tomli`, not the stdlib `tomllib`: this suite runs on 3.10, where the
    # stdlib module does not exist yet.
    import tomli

    _ = tomli.loads(rendered)


def test_omitting_prepare_inputs_leaves_the_committed_text_untouched(tmp_path: Path) -> None:
    """No mapping means no substitution, so existing callers are unchanged."""
    rendered = _render(tmp_path=tmp_path, prepare_inputs=None)
    assert "{{ inputs.prepare_toolchain_mise }}" in rendered
    assert "{{ inputs.sandbox_exempt_marker }}" in rendered


def test_the_substitution_is_its_own_module_reached_through_the_overlay() -> None:
    """The chain lives in a module of its own, entry point only (bd-ib-kyeor4).

    The substituter and the TOML escaper only it reaches moved out of
    `_dispatcher_overlay` by cohesion when the factory-environment env-table
    keying needed room under that file's LLOC ceiling. Pinned here, where the
    behaviour is already covered, and pinned as GONE from the module they left:
    a new module re-exporting from the old one — or an old module that kept its
    copy — would satisfy every existence check while leaving that file exactly
    as large as it was, which is the whole reason for the move.

    The escaper stays PRIVATE inside the new module. Importing a `_`-prefixed
    name across modules is what pyright strict's `reportPrivateUsage` and this
    repository's `private_calls` check both reject, and that is the usual way a
    size-split fails.
    """
    moved = import_module(f"{_PACKAGE}._dispatcher_overlay_input_tokens")
    source = import_module(f"{_PACKAGE}._dispatcher_overlay")

    assert moved.__all__ == ["substitute_input_tokens"]
    assert callable(moved.substitute_input_tokens)
    assert "_escape_toml_basic_string" not in moved.__all__
    for name in ("_INPUT_TOKEN_RE", "_substitute_input_tokens", "_escape_toml_basic_string"):
        assert not hasattr(source, name), f"{name} is still defined on _dispatcher_overlay"
    # And the rendering is still REACHED through the overlay, which the cases
    # above exercise end to end.
    assert source.substitute_input_tokens is moved.substitute_input_tokens
