"""The materialized exact-object leased push used by scripted refresh."""

from __future__ import annotations

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_path_expansion,
    publication_push_program_prepare_steps_block,
    publication_push_program_source,
)


def test_the_prepare_step_materializes_the_single_safe_push_recipe() -> None:
    source = publication_push_program_source()
    path = publication_push_program_path_expansion()
    block = publication_push_program_prepare_steps_block()
    parsed = tomli.loads(block)
    [step] = parsed["run"]["prepare"]["steps"]
    script = step["script"]

    assert source.startswith("#!/bin/sh\nset -eu\n")
    assert source.count("git push") == 1
    assert '--force-with-lease="refs/heads/$branch:$expected"' in source
    assert 'origin "HEAD:refs/heads/$branch"' in source
    assert "--no-verify" not in source
    assert path.endswith(f"/{PUBLICATION_PUSH_PROGRAM_FILENAME}")
    assert f"cat > \"{path}\" <<'LIVESPEC_PUBLICATION_PUSH_PROGRAM'" in script
    assert source in script
    assert f'chmod 700 "{path}"' in script
