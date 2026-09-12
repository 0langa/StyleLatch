#!/usr/bin/env python3
"""Layer 3. Runs on every message, and does three jobs in order.

1. THE SWITCH. If the message opens with a `::` directive, run it now and
   inject the result into this very turn. That is what makes StyleLatch
   usable without a terminal: the switch is a regular expression and a file
   write inside a hook that was going to run anyway.

2. THE NUDGE. Otherwise, if a style is latched, inject a ~30-word reminder.
   An output style is a continuous constraint with nothing to re-trigger it,
   so it drifts. This layer is what stops that, and it is only affordable
   because it stays tiny.

3. DEBUG. If debug mode is on, append what this invocation actually received,
   and spend one turn of its budget.

When nothing is latched and no directive is typed, this prints
{"continue": true} and costs nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _diagnostics  # imported after the sys.path line above, on purpose
import _directives
import _style

EVENT = "UserPromptSubmit"


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
    _style.sync(force=False)
    directive = _directives.parse(_style.prompt_from_payload(payload))

    # A ::test turn speaks for itself. Ticking debug mode here as well would
    # print the same block twice, and would let "::test off" answer with a
    # debug block it is in the middle of switching off.
    asking_about_stylelatch = directive is not None and directive[0] in _directives.TEST_WORDS

    pieces = []
    if directive is not None:
        pieces.append(_directives.apply(directive[0], directive[1], payload))
    elif _style.is_active():
        pieces.append(_style.nudge_text())

    if not asking_about_stylelatch:
        debug = _diagnostics.tick_debug(payload)
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
    except Exception:  # noqa: BLE001 - a broken style must never break a turn
        print(json.dumps(_style.quiet()))


if __name__ == "__main__":
    main()
