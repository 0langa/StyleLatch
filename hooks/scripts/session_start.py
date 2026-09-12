#!/usr/bin/env python3
"""Layer 2: inject the full composed style at session start.

Fires on startup, resume, clear, compact and fork. Compact and fork are the
ones that matter most: that is where a style silently dies otherwise.

When no style is set this prints {"continue": true} and costs nothing.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _style  # imported after the sys.path line above, on purpose


def main() -> None:
    # Drain stdin so the caller never blocks on an unread pipe.
    with contextlib.suppress(Exception):
        sys.stdin.read()

    try:
        if not _style.is_active():
            print(json.dumps(_style.quiet()))
            return
        document = _style.read_active()
        if not document:
            print(json.dumps(_style.quiet()))
            return
        print(json.dumps(_style.additional_context("SessionStart", document)))
    except Exception:  # noqa: BLE001 - a broken style must never break a session.
        print(json.dumps(_style.quiet()))


if __name__ == "__main__":
    main()
