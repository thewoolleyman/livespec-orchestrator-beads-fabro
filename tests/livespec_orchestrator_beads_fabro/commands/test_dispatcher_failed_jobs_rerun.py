"""Classifier coverage for merge-poll's bounded failed-jobs re-run."""

import importlib
from pathlib import Path


def test_classifies_teardown_only_job_from_failed_steps() -> None:
    module_path = Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
        "_dispatcher_failed_jobs_rerun.py"
    )
    assert module_path.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_failed_jobs_rerun"
    )
    classified = module.classify_failed_job(
        job={
            "id": 12,
            "name": "check-coverage (nonroot)",
            "conclusion": "failure",
            "steps": [
                {"name": "Run checks", "conclusion": "success"},
                {"name": "Post Checkout", "conclusion": "failure"},
                {"name": "Stop containers", "conclusion": "failure"},
            ],
        },
        log="Executing the custom container implementation failed",
    )

    assert classified.kind == "runner-teardown"
    assert classified.evidence == (
        "failed teardown steps: Post Checkout, Stop containers",
        "log: Executing the custom container implementation failed",
    )
