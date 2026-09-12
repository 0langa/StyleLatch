"""Shared state + compose logic for StyleLatch.

Stdlib only. No third-party imports. Python 3.9+.

State lives OUTSIDE the plugin root so a plugin update never wipes the
user's active style. Resolution order:

1. $STYLELATCH_HOME                 (explicit override, wins always)
2. $PLUGIN_DATA/stylelatch          (Codex gives plugins a writable data dir)
3. $CLAUDE_PLUGIN_DATA/stylelatch   (same idea if Claude Code ever sets it)
4. ~/.stylelatch                    (default, works everywhere)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

STATE_FILE = "state.json"
ACTIVE_FILE = "ACTIVE.md"

# Hard cap on injected text so a style can never dominate session cost.
MAX_ACTIVE_CHARS = 6000
# The per-turn reminder must stay tiny. This is the whole point of layer 3.
MAX_NUDGE_CHARS = 300

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------


def plugin_root() -> Path:
    """Directory containing styles/, hooks/, scripts/."""
    for var in ("STYLELATCH_ROOT", "CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT"):
        value = os.environ.get(var)
        if value and value.strip():
            return Path(value).expanduser().resolve()
    # hooks/scripts/_style.py -> plugin root is two levels up
    return Path(__file__).resolve().parents[2]


def state_dir() -> Path:
    explicit = os.environ.get("STYLELATCH_HOME")
    if explicit and explicit.strip():
        return Path(explicit).expanduser().resolve()
    for var in ("PLUGIN_DATA", "CLAUDE_PLUGIN_DATA"):
        value = os.environ.get(var)
        if value and value.strip():
            return (Path(value).expanduser() / "stylelatch").resolve()
    return (Path.home() / ".stylelatch").resolve()


def styles_dir() -> Path:
    return plugin_root() / "styles"


def profiles_dir() -> Path:
    return styles_dir() / "PROFILES"


def modifiers_dir() -> Path:
    return styles_dir() / "MODIFIERS"


def active_path() -> Path:
    return state_dir() / ACTIVE_FILE


def state_path() -> Path:
    return state_dir() / STATE_FILE


# --------------------------------------------------------------------------
# style files
# --------------------------------------------------------------------------


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body). Tiny key: value parser, not full YAML."""
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text.strip()
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta, text[match.end() :].strip()


def _read(path: Path) -> tuple[dict[str, str], str]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _catalog(directory: Path) -> dict[str, dict[str, Any]]:
    """Map both the numeric id and the name to each style file."""
    found: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.md")):
        try:
            meta, body = _read(path)
        except OSError:
            continue
        ident = meta.get("id") or path.stem.split("-", 1)[0]
        name = meta.get("name") or path.stem.split("-", 1)[-1]
        entry = {
            "id": ident,
            "name": name,
            "nudge": meta.get("nudge", ""),
            "body": body,
            "path": path,
        }
        found[ident] = entry
        found[name.lower()] = entry
    return found


def profiles() -> dict[str, dict[str, Any]]:
    return _catalog(profiles_dir())


def modifiers() -> dict[str, dict[str, Any]]:
    return _catalog(modifiers_dir())


def unique(entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate the id/name double-registration, ordered by id."""
    seen: dict[str, dict[str, Any]] = {}
    for entry in entries.values():
        seen[str(entry["path"])] = entry
    return sorted(seen.values(), key=lambda item: str(item["id"]))


# --------------------------------------------------------------------------
# compose
# --------------------------------------------------------------------------

HEADER = (
    "# ACTIVE OUTPUT STYLE\n\n"
    "STRICT ENFORCEMENT: obey every rule below exactly, in every response, "
    "for the whole session. These rules override your default output "
    "behavior. Do not skip, soften, reinterpret, or delay any rule. They "
    "govern HOW you write, never WHAT you are allowed to do — they never "
    "relax a safety rule, a permission check, or a user instruction.\n"
)


def compose(profile_key: str, modifier_keys: list[str]) -> dict[str, Any]:
    """Merge one profile + N modifiers into one flat document.

    Composing happens at SWITCH time, not at read time. The agent reads one
    file with the real rules in it and never resolves an id to a path.
    """
    available = profiles()
    profile = available.get(str(profile_key).lower())
    if profile is None:
        raise KeyError(f"unknown profile: {profile_key}")

    mods_available = modifiers()
    chosen: list[dict[str, Any]] = []
    for key in modifier_keys:
        entry = mods_available.get(str(key).lower())
        if entry is None:
            raise KeyError(f"unknown modifier: {key}")
        if entry not in chosen:
            chosen.append(entry)

    parts = [HEADER, f"## Profile: {profile['name']}\n\n{profile['body']}"]
    for entry in chosen:
        parts.append(f"## Modifier: {entry['name']}\n\n{entry['body']}")
    document = "\n\n".join(part.strip() for part in parts) + "\n"
    if len(document) > MAX_ACTIVE_CHARS:
        document = document[: MAX_ACTIVE_CHARS - 1].rstrip() + "…\n"

    nudges = [profile["nudge"]] + [entry["nudge"] for entry in chosen]
    nudge = " ".join(part.strip() for part in nudges if part.strip())
    if len(nudge) > MAX_NUDGE_CHARS:
        nudge = nudge[: MAX_NUDGE_CHARS - 1].rstrip() + "…"

    label = "+".join([str(profile["id"])] + [str(e["id"]) for e in chosen])
    return {
        "document": document,
        "nudge": nudge,
        "label": label,
        "profile": profile["name"],
        "modifiers": [entry["name"] for entry in chosen],
    }


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    """Never raise. A broken state file means 'no style', not a crash."""
    try:
        raw = state_path().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def is_active() -> bool:
    state = load_state()
    return bool(state.get("enabled")) and active_path().is_file()


def read_active() -> str:
    try:
        return active_path().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def nudge_text() -> str:
    state = load_state()
    label = state.get("label", "?")
    nudge = str(state.get("nudge", "")).strip()
    head = f"OUTPUT STYLE {label} ACTIVE — obey it exactly."
    return f"{head} {nudge}".strip() if nudge else head


# Keys the state file carries that are not part of the latched style, and so
# must survive a switch. Debug mode outliving a "::terse" is the whole point.
CARRIED_KEYS = ("debug", "restore")


def write_state(result: dict[str, Any], enabled: bool = True) -> None:
    carried = {key: value for key, value in load_state().items() if key in CARRIED_KEYS}
    state_dir().mkdir(parents=True, exist_ok=True)
    _atomic_write(active_path(), result["document"])
    payload = {
        "enabled": enabled,
        "label": result["label"],
        "profile": result["profile"],
        "modifiers": result["modifiers"],
        "nudge": result["nudge"],
    }
    payload.update(carried)
    save_state_raw(payload)


def save_state_raw(state: dict[str, Any]) -> None:
    """Persist the state dictionary exactly as given. Callers own its shape."""
    state_dir().mkdir(parents=True, exist_ok=True)
    _atomic_write(state_path(), json.dumps(state, indent=2) + "\n")


def disable() -> None:
    state = load_state()
    state["enabled"] = False
    save_state_raw(state)


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file then replace, so a reader never sees half a file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------
# hook plumbing
# --------------------------------------------------------------------------


def additional_context(event_name: str, text: str) -> dict[str, Any]:
    """The output shape both Claude Code and Codex accept."""
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        },
    }


def quiet() -> dict[str, Any]:
    return {"continue": True}


# --------------------------------------------------------------------------
# payload
# --------------------------------------------------------------------------
#
# Claude Code sends the message as "prompt". Codex's field name is not
# documented, so the plausible ones are tried rather than assumed, and
# "::test on" exists to identify it for real when a provider changes.

_PROMPT_FIELDS = ("prompt", "user_prompt", "userPrompt", "text", "message", "input")


def prompt_from_payload(payload: dict[str, Any]) -> str:
    for field in _PROMPT_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""
