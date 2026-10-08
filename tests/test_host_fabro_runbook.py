from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_INSTRUCTIONS = (_REPO_ROOT / "AGENTS.md").read_text()
_IMAGE_RUNBOOK = (_REPO_ROOT / "orchestrator-image" / "README.md").read_text()
_CODEX_REFRESH_COMMAND = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_codex_cred_refresh_command.py"
).read_text()


def test_host_fabro_runbooks_require_supervised_web_console() -> None:
    runbooks = _AGENT_INSTRUCTIONS + _IMAGE_RUNBOOK

    assert "--no-web" not in runbooks
    assert "sudo systemctl restart fabro-server" in _AGENT_INSTRUCTIONS
    assert "sudo systemctl restart fabro-server" in _IMAGE_RUNBOOK
    assert "cargo clean --release -p fabro-spa" in _AGENT_INSTRUCTIONS
    assert "cargo clean --release -p fabro-spa" in _IMAGE_RUNBOOK
    assert "cargo dev build --release -p fabro-cli" in _AGENT_INSTRUCTIONS
    assert "cargo dev build --release -p fabro-cli" in _IMAGE_RUNBOOK
    assert "ExecStartPost" in _IMAGE_RUNBOOK
    assert "Never invoke `fabro server start`" in _IMAGE_RUNBOOK


def test_host_fabro_runbook_documents_run_turn_absence_guard() -> None:
    assert "### Fabro `run_turn` absence guard" in _IMAGE_RUNBOOK
    assert "`run-turn-telemetry-absent`" in _IMAGE_RUNBOOK
    assert "critical\nreflection finding" in _IMAGE_RUNBOOK
    # The trigger was PROVISIONED 2026-08-20, so the runbook must no longer
    # claim it is pending. Assert the provisioned identity instead, and assert
    # the stale claims are GONE so the doc cannot silently regress to them.
    assert "Fabro run_turn dead-man" in _IMAGE_RUNBOOK
    assert "q33z6VbrjT6" in _IMAGE_RUNBOOK
    assert "not yet provisioned in the livespec" not in _IMAGE_RUNBOOK
    assert "only the per-dispatch guard layer exists" not in _IMAGE_RUNBOOK
    assert "Real Fabro `run_turn` spans do not" in _IMAGE_RUNBOOK
    assert "timestamp-bounded global Fabro `run_turn` marker" in _IMAGE_RUNBOOK
    assert "if a future span shape carries them" in _IMAGE_RUNBOOK
    assert "zero `run_turn` spans over the" in _IMAGE_RUNBOOK
    assert "orchestrator-image/provision-honeycomb-run-turn-trigger.sh" in _IMAGE_RUNBOOK
    assert "filtered to `name = run_turn`" in _IMAGE_RUNBOOK
    assert "threshold `<= 0`" in _IMAGE_RUNBOOK
    assert "HONEYCOMB_OPERATOR_ALERT_RECIPIENT" in _IMAGE_RUNBOOK
    assert "redacted email addresses" in _IMAGE_RUNBOOK
    # Deliberately NOT asserting a literal window ("10-minute", "3600", "8h"):
    # the window is tuning, it has already changed twice, and pinning the number
    # here makes an operational retune fail CI for no safety benefit.
    assert "DRY_RUN=1" in _IMAGE_RUNBOOK


def test_host_runbook_documents_the_codex_identity_observation_and_its_limits() -> None:
    assert "### Host Codex credential identity observation" in _IMAGE_RUNBOOK
    assert "--observe-identity-state" in _IMAGE_RUNBOOK
    # The invocation alone is not enough: an operator reading only the command
    # would take an unchanged session identifier as proof the tokens issued
    # under it are still accepted, which is the one inference it cannot carry.
    assert "identifier continuity is not a validity claim" in _IMAGE_RUNBOOK
    assert "invokes no provider and never" in _IMAGE_RUNBOOK
    assert "deliberately NOT reported as `unchanged`" in _IMAGE_RUNBOOK


def test_host_runbook_distinguishes_a_withheld_write_from_a_failed_one() -> None:
    # The two look alike in a log and want opposite responses: `withheld` is the
    # mechanism protecting the comparison series, `failed` is a broken path.
    assert "`withheld` is the mechanism protecting the series, not a fault" in _IMAGE_RUNBOOK
    assert "`failed` IS a fault" in _IMAGE_RUNBOOK


def test_host_runbook_documents_the_credential_destination_refusal() -> None:
    # The destructive case: an observation destination that IS the credential.
    assert "**The destination may not be the credential file.**" in _IMAGE_RUNBOOK
    assert "symlinked parent" in _IMAGE_RUNBOOK
    assert "hard link" in _IMAGE_RUNBOOK
    # Tokens chosen so no line wrap can straddle them — a literal
    # reconstructed from the prose rather than copied out of it is a
    # check that can only fail silently.
    assert "`<destination>.tmp`" in _IMAGE_RUNBOOK
    assert "unlinked before anything is opened" in _IMAGE_RUNBOOK
    # And the `unknown`-not-`first-observation` rule for an unseen identifier.
    assert "`unknown` even on a first reading" in _IMAGE_RUNBOOK
    assert "not UTF-8" in _IMAGE_RUNBOOK


def test_host_runbook_makes_preflight_the_normal_renewal_and_retires_the_timer() -> None:
    assert "### Host Codex credential preflight and timer retirement" in _IMAGE_RUNBOOK
    assert "pre-claim credential gate" in _IMAGE_RUNBOOK
    assert "effective workflow and review-fix cap" in _IMAGE_RUNBOOK
    assert "systemctl --user disable --now livespec-codex-cred-refresh.timer" in _IMAGE_RUNBOOK
    assert "UnitFileState" in _IMAGE_RUNBOOK
    assert "ActiveState" in _IMAGE_RUNBOOK
    assert "unit files are retained" in _IMAGE_RUNBOOK
    assert "bounded manual diagnostic" in _IMAGE_RUNBOOK
    assert "systemctl --user enable --now livespec-codex-cred-refresh.timer" not in _IMAGE_RUNBOOK
    assert "18000 seconds (5h)" not in _IMAGE_RUNBOOK
    assert "five-minute host\ntimer runs" not in _CODEX_REFRESH_COMMAND
