#!/usr/bin/env python3
"""Print the catalogue and the current state. Nothing else, ever.

This is not a command line interface and must not become one. It takes no
arguments, changes no state, and exists for exactly one caller: the
`/stylelatch` slash command, which needs live text to show a user who is
browsing the `/` menu and has not yet learned the `::` grammar.

Every other capability is a `::` directive, typed in the chat.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _diagnostics  # imported after the sys.path line above, on purpose
import _directives
import _style

# A style may contain any character, and a Windows console defaults to cp1252.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, OSError):  # pragma: no cover
        _stream.reconfigure(encoding="utf-8", errors="replace")


def render() -> str:
    # The slash command runs from the project, so the working directory is the
    # right project hint -- there is no hook payload to take one from.
    _style.set_project_hint(str(Path.cwd()))
    _style.sync()
    return _directives.catalog_text() + "\n\n" + _diagnostics.status()


def main() -> int:
    try:
        print(render())
    except Exception as exc:  # noqa: BLE001 - a renderer must not raise at a user
        print(f"StyleLatch could not render its catalogue: {exc}")
        print("Type ::test in the chat for a full diagnostic.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
