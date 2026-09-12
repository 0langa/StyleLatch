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


def active_path() -> Path:
    return state_dir() / ACTIVE_FILE


def state_path() -> Path:
    return state_dir() / STATE_FILE


# --------------------------------------------------------------------------
# where styles come from
# --------------------------------------------------------------------------
#
# Three places, most specific first. A style you wrote has to outlive a plugin
# update, and a repository has to be able to carry the voice its contributors
# agreed on, so the built-ins are the last word rather than the only one.
#
#   project    <repo>/.stylelatch/styles     committed, shared with the team
#   user       $STYLELATCH_HOME/styles       yours, survives every update
#   built-in   <plugin>/styles               replaced on every update
#
# First source wins on a name or id collision. That is deliberate: shadowing a
# built-in is the point of having a user directory at all.

PROJECT_DIRNAME = ".stylelatch"

# A repository marker, or a .stylelatch directory that actually carries styles.
# Bare ".stylelatch" is deliberately not a marker: the default state directory
# is ~/.stylelatch, which would make the home directory a project and every
# session in it inherit styles from there.
_PROJECT_MARKERS = (".git", ".hg", ".jj", ".svn", f"{PROJECT_DIRNAME}/styles")

_project_hint: str = ""


def set_project_hint(path: str | None) -> None:
    """Record the working directory the host reported for this invocation.

    Hooks are not guaranteed to run with the project as their own working
    directory, but every provider that sends a payload sends a cwd in it.
    """
    global _project_hint
    _project_hint = (path or "").strip()


def project_root() -> Path | None:
    """The repository the current invocation belongs to, if there is one.

    Walks up from the reported working directory looking for a marker. A style
    latched in a subdirectory has to mean the same thing as one latched at the
    top, or the feature is a trap rather than a convenience.
    """
    explicit = os.environ.get("STYLELATCH_PROJECT", "").strip()
    start = explicit or _project_hint
    try:
        here = Path(start).expanduser().resolve() if start else Path.cwd().resolve()
    except OSError:
        return None
    if explicit:
        return here

    try:
        home = Path.home().resolve()
    except (OSError, RuntimeError):  # pragma: no cover - no home on this host
        home = None
    for candidate in (here, *here.parents):
        # A home directory is where personal styles live, never a project.
        if home is not None and candidate == home:
            break
        if any((candidate / marker).exists() for marker in _PROJECT_MARKERS):
            return candidate
    return None


def style_roots() -> list[tuple[str, Path]]:
    """(label, directory) pairs in precedence order, most specific first."""
    roots: list[tuple[str, Path]] = []
    project = project_root()
    if project is not None:
        roots.append(("project", project / PROJECT_DIRNAME / "styles"))
    roots.append(("user", state_dir() / "styles"))
    roots.append(("built-in", plugin_root() / "styles"))

    # A project whose own directory is the plugin checkout would otherwise
    # list the built-ins twice, once under each label.
    seen: set[Path] = set()
    unique_roots = []
    for label, path in roots:
        if path in seen:
            continue
        seen.add(path)
        unique_roots.append((label, path))
    return unique_roots


def styles_dir() -> Path:
    """The built-in style directory. Kept for messages that name a location."""
    return plugin_root() / "styles"


def profiles_dir() -> Path:
    return styles_dir() / "PROFILES"


def modifiers_dir() -> Path:
    return styles_dir() / "MODIFIERS"


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


def _read_dir(directory: Path, source: str) -> list[dict[str, Any]]:
    """Every style file in one directory, in filename order."""
    if not directory.is_dir():
        return []
    entries = []
    for path in sorted(directory.glob("*.md")):
        try:
            meta, body = _read(path)
        except (OSError, UnicodeDecodeError):
            # An unreadable style is skipped, never fatal. ::test names it.
            continue
        entries.append(
            {
                "id": meta.get("id") or path.stem.split("-", 1)[0],
                "name": meta.get("name") or path.stem.split("-", 1)[-1],
                "nudge": meta.get("nudge", ""),
                "body": body,
                "path": path,
                "source": source,
            }
        )
    return entries


def collect(kind: str) -> list[dict[str, Any]]:
    """Every style of one kind across all sources, most specific first.

    Shadowed entries stay in the list and carry "shadowed_by", so the reason a
    style is not the one being used stays answerable instead of silent.
    """
    claimed: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for source, root in style_roots():
        for entry in _read_dir(root / kind, source):
            keys = {str(entry["id"]).lower(), str(entry["name"]).lower()}
            winner = next((claimed[key] for key in keys if key in claimed), None)
            if winner is None:
                for key in keys:
                    claimed[key] = entry
                entry["shadowed_by"] = None
            else:
                entry["shadowed_by"] = winner
            ordered.append(entry)
    return ordered


def _catalog(kind: str) -> dict[str, dict[str, Any]]:
    """Map both the id and the name to each style. First source wins."""
    found: dict[str, dict[str, Any]] = {}
    for entry in collect(kind):
        if entry["shadowed_by"] is not None:
            continue
        found[str(entry["id"]).lower()] = entry
        found[str(entry["name"]).lower()] = entry
    return found


def profiles() -> dict[str, dict[str, Any]]:
    return _catalog("PROFILES")


def modifiers() -> dict[str, dict[str, Any]]:
    return _catalog("MODIFIERS")


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
