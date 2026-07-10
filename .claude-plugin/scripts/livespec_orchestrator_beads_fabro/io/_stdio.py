"""Small terminal stream write surface for CLI supervisors.

Command modules call these helpers instead of directly reaching into
``sys.stdout`` or ``sys.stderr``. Tests can inject a stream; production uses
the process streams.
"""

from __future__ import annotations

import sys
from typing import TextIO

__all__: list[str] = [
    "write_stderr",
    "write_stdout",
]


def write_stdout(*, text: str, stream: TextIO | None = None) -> None:
    target = sys.stdout if stream is None else stream
    _ = target.write(text)


def write_stderr(*, text: str, stream: TextIO | None = None) -> None:
    target = sys.stderr if stream is None else stream
    _ = target.write(text)
