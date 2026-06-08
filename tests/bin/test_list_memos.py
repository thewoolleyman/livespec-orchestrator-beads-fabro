"""Per-wrapper coverage test for bin/list_memos.py."""

from collections.abc import Callable


def test_list_memos_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner("list_memos.py", "livespec_impl_beads.commands.list_memos", 0)
