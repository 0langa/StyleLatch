#!/usr/bin/env python3
"""Prove injection off the host's own session log. No model testimony.

The model's account of its context is not evidence, and neither is a hook
status indicator -- that only proves a script ran. The host, however, writes
the exact payload it sends to the API into a session file on disk:

    Codex        ~/.codex/sessions/<y>/<m>/<d>/rollout-*.jsonl
                 injected hook context lands as a role="developer" message
    Claude Code  ~/.claude/projects/<slug>/<uuid>.jsonl

That file is written by the host, not the model. If the text is in there, it
reached the API. That is the end of the argument.

    python scripts/verify_injection.py                 newest Codex session
    python scripts/verify_injection.py --provider claude
    python scripts/verify_injection.py --file <path.jsonl>
    python scripts/verify_injection.py --grep SL-DOC-063bb0966677
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, OSError):  # pragma: no cover
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Text StyleLatch injects. Layer 2 opens with the strict-enforcement header;
# layer 3 opens with the label line.
MARKERS = {
    "SessionStart document": "STRICT ENFORCEMENT",
    "UserPromptSubmit nudge": "OUTPUT STYLE",
}

SEARCH_ROOTS = {
    "codex": [Path.home() / ".codex" / "sessions"],
    "claude": [Path.home() / ".claude" / "projects"],
}


def newest_log(provider: str) -> Path | None:
    candidates: list[Path] = []
    for root in SEARCH_ROOTS[provider]:
        if root.is_dir():
            candidates.extend(root.rglob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def walk_strings(value) -> list[str]:
    """Every string anywhere in the record, regardless of host schema."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in walk_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in walk_strings(v)]
    return []


def scan(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = data.get("payload", data)
            records.append(
                {
                    "line": number,
                    "role": payload.get("role") or data.get("role") or "",
                    "text": "\n".join(walk_strings(payload)),
                }
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["codex", "claude"], default="codex")
    parser.add_argument("--file", help="a specific .jsonl session log")
    parser.add_argument("--grep", help="extra exact string to look for, e.g. a canary token")
    args = parser.parse_args()

    path = Path(args.file) if args.file else newest_log(args.provider)
    if path is None or not path.is_file():
        print(f"no session log found for {args.provider}.", file=sys.stderr)
        return 2

    records = scan(path)
    print(f"log:      {path}")
    print(f"records:  {len(records)}")
    print()

    targets = dict(MARKERS)
    if args.grep:
        targets[f"custom: {args.grep}"] = args.grep

    worst = 0
    for label, needle in targets.items():
        hits = [r for r in records if needle in r["text"]]
        if hits:
            roles = sorted({r["role"] for r in hits if r["role"]}) or ["(no role)"]
            lines = ", ".join(str(r["line"]) for r in hits[:5])
            print(f"  FOUND    {label}")
            print(f"           {len(hits)} record(s), role={'/'.join(roles)}, line {lines}")
        else:
            print(f"  ABSENT   {label}")
            worst = 1

    print()
    if worst:
        print("Something did not reach the API. Check in this order:")
        print("  1. Is the provider running a stale copy of the plugin?")
        print("  2. Are the hooks trusted? Codex: Settings > Coding > Hooks.")
        print("  3. Is a style actually latched? python scripts/style.py show")
    else:
        print("Every marker is in the host's own log. The text reached the API.")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
