#!/usr/bin/env python3
"""Layer 4: measure whether the reply that just finished obeyed the style.

Every other layer pushes a style toward the model. This one reads back what
came out, so the claim "the style is holding" stops being an impression and
becomes a number.

It injects nothing. Its whole output is `{"continue": true}`; what it produces
is a record that `::status` reports and that the next turn's nudge turns into
a correction naming the specific rule that broke.

Costs nothing when the latched style declares no checks, which is the default:
one state file read and an early return.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _adherence  # imported after the sys.path line above, on purpose
import _style


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


def measure(payload: dict) -> None:
    _style.set_project_hint(payload.get("cwd") or payload.get("workspace"))
    _style.set_session_hint(payload.get("session_id") or payload.get("sessionId"))

    rules, _ = _adherence.active_rules()
    if not rules:
        return

    transcript = payload.get("transcript_path") or payload.get("transcriptPath") or ""
    reply = _adherence.last_reply(str(transcript))
    if not reply:
        # The transcript shape was not recognised. Recording a clean turn here
        # would be a lie, and recording a broken one would be worse.
        return

    label = str(_style.load_state().get("label", "?"))
    _adherence.record(_adherence.evaluate(reply, rules), label)


def main() -> None:
    payload = read_payload()
    # Measuring must never break a turn. If it cannot be done, it is not done.
    with contextlib.suppress(Exception):
        measure(payload)
    print(json.dumps(_style.quiet()))


if __name__ == "__main__":
    main()
