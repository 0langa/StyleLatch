#!/usr/bin/env python3
"""Layer 2: inject the full composed style at session start.

Fires on startup, resume, clear, compact and fork. Compact and fork are the
ones that matter most: that is where a style silently dies otherwise.

This is also where debug mode notices that the session changed, because a
session start is the only moment that is unambiguous about it.

When no style is set this prints {"continue": true} and costs nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _diagnostics  # imported after the sys.path line above, on purpose
import _style

EVENT = "SessionStart"


def read_payload() -> dict:
    """Always drain stdin, so the caller never blocks on an unread pipe."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001 - a hook must never fail on its own input
        return {}
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def build(payload: dict) -> list[str]:
    # Project-scoped styles live next to the code they apply to, so the
    # hook has to know which project this invocation belongs to.
    _style.set_project_hint(payload.get("cwd") or payload.get("workspace"))
    _style.set_session_hint(payload.get("session_id") or payload.get("sessionId"))
    _style.sync(force=True)
    pieces = []
    if _style.is_active():
        document = _style.read_active()
        if document:
            pieces.append(document)

    debug = _diagnostics.session_start_debug(payload)
    if debug:
        pieces.append(debug)
    return pieces


def main() -> None:
    payload = read_payload()
    try:
        pieces = build(payload)
        if not pieces:
            print(json.dumps(_style.quiet()))
            return
        print(json.dumps(_style.additional_context(EVENT, "\n\n".join(pieces))))
    except Exception:  # noqa: BLE001 - a broken style must never break a session
        print(json.dumps(_style.quiet()))


if __name__ == "__main__":
    main()
