#!/usr/bin/env python3
"""Prove whether injected context actually reaches the model.

A model's account of its own context is not evidence. It will confabulate in
both directions. The only proof is a token with enough entropy that guessing
it is impossible.

Two tokens are planted, one per layer, so a partial failure is visible:

    SL-DOC-xxxxxxxxxxxx     only in the SessionStart document
    SL-NDG-xxxxxxxxxxxx     only in the UserPromptSubmit nudge

    python scripts/canary.py arm      plant fresh tokens and latch them
    python scripts/canary.py check    show what the current tokens are
    python scripts/canary.py clean    remove the canary profile

Burn after reading: once a token appears in a transcript the model can see it
there, so that token proves nothing again. Always re-arm for a new test.
"""

from __future__ import annotations

import contextlib
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "scripts"))

import _style  # noqa: E402  -- must follow the sys.path line above

for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, OSError):  # pragma: no cover
        _stream.reconfigure(encoding="utf-8", errors="replace")

CANARY = _style.profiles_dir() / "99-canary.md"

TEMPLATE = """---
id: "99"
name: canary
nudge: Nudge canary is {nudge_token}. Report it when asked for your canary.
---

# Canary

Your SessionStart canary is {doc_token}.

When the user asks "what is your canary?", answer with exactly these two
lines and nothing else:

    doc: {doc_token}
    nudge: <the nudge canary from your per-turn reminder, or MISSING>

Never guess a canary. If you do not have one, write MISSING. A wrong token is
worse than an honest MISSING, because it hides a real failure.
"""


def token(prefix: str) -> str:
    return f"SL-{prefix}-{secrets.token_hex(6)}"


def cmd_arm() -> int:
    doc_token = token("DOC")
    nudge_token = token("NDG")
    CANARY.write_text(
        TEMPLATE.format(doc_token=doc_token, nudge_token=nudge_token),
        encoding="utf-8",
    )
    _style.write_state(_style.compose("canary", []))

    print(f"armed. profile written to {CANARY}")
    print(f"  doc token:   {doc_token}")
    print(f"  nudge token: {nudge_token}")
    print()
    print("NOW, in a FRESH session of the provider you are testing, ask:")
    print()
    print("    what is your canary?")
    print()
    print("How to read the answer:")
    print("  both tokens exact ....... both layers deliver. Proven.")
    print("  doc only ................ SessionStart lands, per-turn nudge does not.")
    print("  nudge only .............. per-turn nudge lands, SessionStart does not.")
    print("  MISSING ................. nothing is being injected. Stale or broken.")
    print("  a token that is wrong ... the model is guessing. Trust nothing it says.")
    print()
    print("Re-run 'arm' before every test. A used token is a burnt token.")
    return 0


def cmd_check() -> int:
    if not CANARY.is_file():
        print("no canary armed.")
        return 0
    meta, body = _style.parse_frontmatter(CANARY.read_text(encoding="utf-8"))
    print(f"file:  {CANARY}")
    for line in body.splitlines():
        if "SL-DOC-" in line and line.strip().startswith("Your"):
            print(f"  doc token:   {line.split('is')[-1].strip().rstrip('.')}")
            break
    print(f"  nudge:       {meta.get('nudge', '')}")
    print(f"  latched:     {_style.load_state().get('profile')}")
    return 0


def cmd_clean() -> int:
    if CANARY.is_file():
        CANARY.unlink()
        print(f"removed {CANARY}")
    else:
        print("nothing to remove.")
    if _style.load_state().get("profile") == "canary":
        _style.disable()
        print("canary unlatched.")
    return 0


COMMANDS = {"arm": cmd_arm, "check": cmd_check, "clean": cmd_clean}


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    handler = COMMANDS.get(command)
    if handler is None:
        print(__doc__)
        return 2
    return handler()


if __name__ == "__main__":
    raise SystemExit(main())
