#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md, for release notes.

python tools/changelog_section.py 0.2.0
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def section(version: str, text: str) -> str:
    wanted = f"## [{version}]"
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(wanted)), None)
    if start is None:
        return f"No changelog section for {version}."

    out = []
    for line in lines[start + 1 :]:
        if line.startswith("## ["):
            break
        out.append(line)
    return "\n".join(out).strip() or f"No changelog section for {version}."


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    print(section(sys.argv[1], (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
