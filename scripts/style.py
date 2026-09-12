#!/usr/bin/env python3
"""Switch the active output style.

    python scripts/style.py list
    python scripts/style.py set 01 --with 02 --with 03
    python scripts/style.py set eli5 --with no-preamble
    python scripts/style.py show
    python scripts/style.py off

Composing happens here, at switch time. The agent only ever reads one flat
file with the real rules already merged in.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks" / "scripts"))

import _style  # imported after the sys.path line above, on purpose

# A style may contain any character, and Windows consoles default to cp1252.
# Printing a nudge must never crash the switcher.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, OSError):  # pragma: no cover
        _stream.reconfigure(encoding="utf-8", errors="replace")


def cmd_list(_args: argparse.Namespace) -> int:
    print("PROFILES  (pick exactly one)")
    for entry in _style.unique(_style.profiles()):
        print(f"  {entry['id']:>3}  {entry['name']}")
    print("\nMODIFIERS  (stack as many as you like)")
    for entry in _style.unique(_style.modifiers()):
        print(f"  {entry['id']:>3}  {entry['name']}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    try:
        result = _style.compose(args.profile, args.with_ or [])
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("run 'style.py list' to see valid ids and names.", file=sys.stderr)
        return 2
    _style.write_state(result)
    print(f"style {result['label']} active  ({result['profile']})")
    if result["modifiers"]:
        print(f"  modifiers: {', '.join(result['modifiers'])}")
    print(f"  written:   {_style.active_path()}")
    print(f"  nudge:     {result['nudge'] or '(none)'}")
    print("\nStart a new session or fork this one to pick it up.")
    return 0


def cmd_show(_args: argparse.Namespace) -> int:
    state = _style.load_state()
    if not state:
        print("no style has ever been set.")
        print(f"state dir: {_style.state_dir()}")
        return 0
    status = "ACTIVE" if _style.is_active() else "off"
    print(f"status:    {status}")
    print(f"label:     {state.get('label', '?')}")
    print(f"profile:   {state.get('profile', '?')}")
    print(f"modifiers: {', '.join(state.get('modifiers') or []) or '(none)'}")
    print(f"nudge:     {state.get('nudge') or '(none)'}")
    print(f"file:      {_style.active_path()}")
    return 0


def cmd_off(_args: argparse.Namespace) -> int:
    _style.disable()
    print("style off. Hooks now cost nothing until you set one again.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="style", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    lister = subparsers.add_parser("list", help="show available profiles and modifiers")
    lister.set_defaults(func=cmd_list)

    setter = subparsers.add_parser("set", help="compose and activate a style")
    setter.add_argument("profile", help="profile id or name")
    setter.add_argument(
        "--with",
        dest="with_",
        action="append",
        metavar="MODIFIER",
        help="modifier id or name; repeat to stack",
    )
    setter.set_defaults(func=cmd_set)

    subparsers.add_parser("show", help="show what is active").set_defaults(func=cmd_show)
    subparsers.add_parser("off", help="deactivate without deleting").set_defaults(func=cmd_off)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
