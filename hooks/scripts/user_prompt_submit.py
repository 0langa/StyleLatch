#!/usr/bin/env python3
"""Runs on every message. Does two jobs.

1. THE SWITCH. If the message opens with "::something", latch that style now
   and inject it for this very turn. No terminal, no new session, no model in
   the loop -- a regex and a file write.

2. THE NUDGE. Otherwise, if a style is latched, inject a ~30-word reminder.
   An output style is a continuous constraint with nothing to re-trigger it,
   so it drifts. This is the layer that stops that, and it is only affordable
   because it stays tiny.

When no style is latched and no directive is typed, this prints
{"continue": true} and costs nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _style  # noqa: E402

EVENT = "UserPromptSubmit"


def read_payload() -> dict:
    """Always drain stdin, so the caller never blocks on an unread pipe."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return {}
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> None:
    payload = read_payload()
    try:
        # A directive is checked BEFORE the active gate: "::eli5" has to work
        # when nothing is latched yet, which is exactly the first time anyone
        # will type it.
        directive = _style.parse_directive(_style.prompt_from_payload(payload))
        if directive is not None:
            token, rest = directive
            text = _style.apply_directive(token, rest, payload)
            print(json.dumps(_style.additional_context(EVENT, text)))
            return

        if not _style.is_active():
            print(json.dumps(_style.quiet()))
            return
        print(json.dumps(_style.additional_context(EVENT, _style.nudge_text())))
    except Exception:  # noqa: BLE001 - a broken style must never break a turn.
        print(json.dumps(_style.quiet()))


if __name__ == "__main__":
    main()
