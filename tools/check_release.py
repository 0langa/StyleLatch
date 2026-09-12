#!/usr/bin/env python3
"""Refuse a release whose tag, manifests and changelog disagree.

A plugin is installed by version. A tag that says one thing while the manifest
says another produces an install that is silently the wrong code, which is
worse than a failed release.

    python tools/check_release.py v0.2.0
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (
    "plugin.json",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    tag = sys.argv[1]
    version = tag[1:] if tag.startswith("v") else tag

    problems = []
    for relative in MANIFESTS:
        found = json.loads((ROOT / relative).read_text(encoding="utf-8")).get("version")
        if found != version:
            problems.append(f"{relative} says {found}, tag says {version}")

    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    for entry in market["plugins"]:
        if entry.get("version") != version:
            problems.append(f"marketplace entry {entry['name']} says {entry.get('version')}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        problems.append(f"CHANGELOG.md has no '## [{version}]' section")

    if problems:
        print(f"Release {tag} is not consistent:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"Release {tag} is consistent across every manifest and the changelog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
