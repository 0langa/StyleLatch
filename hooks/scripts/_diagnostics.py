"""Everything StyleLatch can tell you about itself, from inside the chat.

There is no terminal surface for users. When a style does not seem to be
applying, the question has to be answerable in the place the problem appeared,
so every check in this module is reachable through a `::test` directive.

Three kinds of answer live here, in increasing order of how much they prove:

1. `self_test()` -- structural. Does the state directory exist and accept a
   write, do the style files parse, is the composed document inside budget.
   Fast, and catches most real breakage.
2. `debug_block()` -- situational. What this specific hook invocation actually
   received, repeated every turn until it expires. This is how a provider's
   undocumented payload shape gets identified.
3. `arm_canary()` and `verify_injection()` -- evidential. A model's account of
   its own context is not evidence, and a green hook indicator only proves a
   script ran. A high-entropy token echoed back, or the host's own transcript
   on disk, is proof.
"""

from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import _style

# Debug mode is deliberately hard to leave running. Whichever of these limits
# is reached first ends it, because a diagnostic that outlives its usefulness
# is exactly the clutter it was added to prevent.
DEBUG_TURNS = 20
DEBUG_SECONDS = 60 * 60

# Rough, and honest about being rough. Four characters per token is close
# enough to make a budget decision with, and no tokenizer ships in the stdlib.
CHARS_PER_TOKEN = 4


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN)) if text else 0


def _line(ok: bool, label: str, detail: str = "") -> str:
    mark = "PASS" if ok else "FAIL"
    return f"  {mark}  {label}" + (f"\n        {detail}" if detail else "")


def _field(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _install_kind(root: Path) -> str:
    """Tell a live checkout apart from an installed snapshot.

    A provider installs a plugin by copying it into a cache directory. Edits
    to the source repository then have no effect until the plugin is updated,
    which is the most confusing failure mode there is: the code is right, the
    tests pass, and nothing changes.
    """
    parts = [part.lower() for part in root.parts]
    if "cache" in parts and "plugins" in parts:
        return "installed snapshot -- edits to the repo need a plugin update"
    if (root / ".git").exists():
        return "live checkout"
    return "directory"


# --------------------------------------------------------------------------
# 1. structural -- self test
# --------------------------------------------------------------------------


def _check_state_dir() -> tuple[bool, str]:
    target = _style.state_dir()
    probe = target / ".write-probe"
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, f"{target}\n        not writable: {exc}"
    return True, str(target)


def _check_styles() -> tuple[bool, str]:
    profiles = _style.unique(_style.profiles())
    modifiers = _style.unique(_style.modifiers())
    if not profiles:
        return False, f"no profiles found under {_style.profiles_dir()}"

    problems = []
    for entry in profiles:
        if not entry["nudge"]:
            problems.append(f"profile '{entry['name']}' has no nudge")
        if not entry["body"].strip():
            problems.append(f"profile '{entry['name']}' has an empty body")
    for group, entries in (("profile", profiles), ("modifier", modifiers)):
        ids = [entry["id"] for entry in entries]
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            problems.append(f"duplicate {group} id '{dup}'")

    counts: dict[str, int] = {}
    shadowed = []
    for kind in ("PROFILES", "MODIFIERS"):
        for entry in _style.collect(kind):
            counts[entry["source"]] = counts.get(entry["source"], 0) + 1
            if entry["shadowed_by"] is not None:
                shadowed.append(
                    f"{entry['name']} ({entry['source']}) is shadowed by the "
                    f"{entry['shadowed_by']['source']} one"
                )

    summary = f"{len(profiles)} profiles, {len(modifiers)} modifiers"
    detail = [summary, *(f"{source}: {count} file(s)" for source, count in counts.items())]
    # Shadowing is a feature, not a fault: overriding a built-in is the whole
    # reason a user directory exists. It is reported, never failed on.
    detail += shadowed
    if problems:
        return False, "\n        ".join(detail + problems)
    return True, "\n        ".join(detail)


def _check_compose() -> tuple[bool, str]:
    """Compose every profile. A style that cannot compose is a broken style."""
    broken = []
    for entry in _style.unique(_style.profiles()):
        try:
            _style.compose(entry["name"], [])
        except Exception as exc:  # noqa: BLE001 - report it, never raise out of a hook
            broken.append(f"{entry['name']}: {exc}")
    if broken:
        return False, "\n        ".join(broken)
    return True, "every profile composes"


def _check_budget() -> tuple[bool, str]:
    state = _style.load_state()
    if not state.get("enabled"):
        return True, "nothing latched, so nothing is being injected"

    document = _style.read_active()
    nudge = _style.nudge_text()
    detail = (
        f"layer 2  {len(document):>5} chars  ~{_tokens(document):>4} tokens  "
        f"(cap {_style.MAX_ACTIVE_CHARS})\n"
        f"        layer 3  {len(nudge):>5} chars  ~{_tokens(nudge):>4} tokens  "
        f"(cap {_style.MAX_NUDGE_CHARS})"
    )
    if not document:
        return False, detail + "\n        latched, but ACTIVE.md is missing or empty"
    return len(nudge) <= _style.MAX_NUDGE_CHARS, detail


def _check_hooks() -> tuple[bool, str]:
    here = Path(__file__).resolve().parent
    missing = [
        name
        for name in ("session_start.py", "user_prompt_submit.py", "_style.py")
        if not (here / name).is_file()
    ]
    if missing:
        return False, "missing: " + ", ".join(missing)

    config = _style.plugin_root() / "hooks" / "hooks.json"
    if not config.is_file():
        return False, f"hooks.json not found at {config}"
    try:
        registered = json.loads(config.read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"hooks.json unreadable: {exc}"

    events = sorted(registered)
    if not {"SessionStart", "UserPromptSubmit"}.issubset(events):
        return False, f"registered: {', '.join(events) or 'none'}"
    return True, f"registered: {', '.join(events)}"


def self_test(payload: dict[str, Any] | None = None) -> str:
    payload = payload or {}
    checks = (
        ("state directory is writable", _check_state_dir),
        ("style files parse", _check_styles),
        ("every style composes", _check_compose),
        ("hook scripts and registration", _check_hooks),
        ("injection budget", _check_budget),
    )
    lines = ["StyleLatch self-test", ""]
    failed = 0
    for label, check in checks:
        try:
            ok, detail = check()
        except Exception as exc:  # noqa: BLE001 - a diagnostic must never crash
            ok, detail = False, f"check raised {type(exc).__name__}: {exc}"
        failed += 0 if ok else 1
        lines.append(_line(ok, label, detail))

    root = _style.plugin_root()
    state = _style.load_state()
    project = _style.project_root()
    lines += [
        "",
        f"  plugin root   {root}",
        f"                {_install_kind(root)}",
        f"  state         {_style.state_dir()}",
        f"  project       {project if project else '(none detected)'}",
        f"  latched       {state.get('label', '?') if state.get('enabled') else 'nothing'}",
        f"  python        {sys.version.split()[0]} on {sys.platform}",
        "",
        "  styles are read from, most specific first:",
    ]
    for source, path in _style.style_roots():
        mark = "" if path.is_dir() else "   (does not exist yet)"
        lines.append(f"    {source:<9} {path}{mark}")
    session = _field(payload, "session_id", "sessionId")
    if session:
        lines.append(f"  session       {session}")

    lines += ["", "  " + ("all checks pass" if not failed else f"{failed} check(s) FAILED")]
    if failed:
        lines += [
            "",
            "  Most likely causes, in order:",
            "    1. The provider is running an installed snapshot of an older copy.",
            "    2. The state directory moved ($STYLELATCH_HOME, or $PLUGIN_DATA).",
            "    3. A style file was edited into something that no longer parses.",
        ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 2. situational -- debug mode
# --------------------------------------------------------------------------


def debug_info() -> dict[str, Any]:
    info = _style.load_state().get("debug")
    return info if isinstance(info, dict) else {}


def _save_debug(info: dict[str, Any] | None) -> None:
    state = _style.load_state()
    if info is None:
        state.pop("debug", None)
    else:
        state["debug"] = info
    _style.save_state_raw(state)


def start_debug(payload: dict[str, Any]) -> str:
    now = time.time()
    _save_debug(
        {
            "since": now,
            "expires_at": now + DEBUG_SECONDS,
            "turns_left": DEBUG_TURNS,
            "session": _field(payload, "session_id", "sessionId"),
        }
    )
    return (
        f"StyleLatch debug mode ON for {DEBUG_TURNS} turns or "
        f"{DEBUG_SECONDS // 60} minutes, whichever ends first. It also ends when "
        "this session does. Turn it off early with ::test off.\n\n" + debug_block(payload)
    )


def stop_debug() -> str:
    if not debug_info():
        return "StyleLatch debug mode was not on. Nothing changed."
    _save_debug(None)
    return "StyleLatch debug mode OFF."


def _expiry(info: dict[str, Any], payload: dict[str, Any]) -> str:
    """Return the reason debug mode should end now, or an empty string."""
    if float(info.get("turns_left", 0)) <= 0:
        return "turn budget spent"
    if time.time() > float(info.get("expires_at", 0)):
        return "time limit reached"
    recorded = str(info.get("session") or "")
    current = _field(payload, "session_id", "sessionId")
    if recorded and current and recorded != current:
        return "session changed"
    return ""


def tick_debug(payload: dict[str, Any]) -> str:
    """Advance debug mode by one turn. Returns text to inject, or "".

    Called on every prompt, so the cost when debug mode is off -- which is
    almost always -- is one dictionary lookup.
    """
    info = debug_info()
    if not info:
        return ""

    reason = _expiry(info, payload)
    if reason:
        _save_debug(None)
        return f"StyleLatch debug mode ended by itself ({reason}). Say ::test on to resume."

    info["turns_left"] = int(info.get("turns_left", 1)) - 1
    _save_debug(info)
    return debug_block(payload)


def session_start_debug(payload: dict[str, Any]) -> str:
    """Report or retire debug mode at a session boundary.

    A session start is the only moment where "is this still the session that
    asked for debug mode" has an unambiguous answer, so this is where a debug
    mode belonging to a finished session gets cleaned up. No turn is spent:
    a session start is not a turn.
    """
    info = debug_info()
    if not info:
        return ""

    reason = _expiry(info, payload)
    if reason:
        _save_debug(None)
        return f"StyleLatch debug mode ended by itself ({reason}). Say ::test on to resume."
    return debug_block(payload)


def debug_block(payload: dict[str, Any]) -> str:
    info = debug_info()
    state = _style.load_state()

    if info:
        minutes = max(0, int((float(info.get("expires_at", 0)) - time.time()) // 60))
        budget = f"{int(info.get('turns_left', 0))} turns / {minutes} min left"
    else:
        budget = "single shot"

    root = _style.plugin_root()
    lines = [
        f"STYLELATCH DEBUG ({budget})",
        f"  event       {_field(payload, 'hook_event_name', 'hookEventName') or '?'}",
        f"  payload     {', '.join(sorted(payload)) or '(empty payload)'}",
        f"  prompt      {'yes' if _style.prompt_from_payload(payload) else 'NO -- field unknown'}",
        f"  cwd         {_field(payload, 'cwd', 'workspace', 'project_dir') or '(not sent)'}",
        f"  session     {_field(payload, 'session_id', 'sessionId') or '(not sent)'}",
        f"  transcript  {_field(payload, 'transcript_path', 'transcriptPath') or '(not sent)'}",
        f"  plugin root {root}",
        f"              {_install_kind(root)}",
        f"  state       {_style.state_dir()}",
    ]
    if state.get("enabled"):
        document = _style.read_active()
        nudge = _style.nudge_text()
        lines += [
            f"  latched     {state.get('label', '?')}  {state.get('profile', '?')}",
            f"  layer 2     {len(document)} chars ~{_tokens(document)} tokens",
            f"  layer 3     {len(nudge)} chars ~{_tokens(nudge)} tokens",
        ]
    else:
        lines.append("  latched     nothing")

    lines += [
        "",
        "Print this block verbatim at the end of your reply, inside a code "
        "fence, so the user can read it. Then answer normally.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 3. evidential -- canary and transcript verification
# --------------------------------------------------------------------------

CANARY_LABEL = "canary"

_CANARY_BODY = """## Profile: canary

This session is under test. Two high-entropy tokens were planted, one per
injection layer, so a partial failure is visible rather than silent.

Your SessionStart canary is {doc_token}.

When the user asks "what is your canary?", answer with exactly these two
lines and nothing else:

    doc: {doc_token}
    nudge: <the nudge canary from your per-turn reminder, or MISSING>

Never guess a canary. If you do not have one, write MISSING. A wrong token is
worse than an honest MISSING, because it hides a real failure."""


def _token(prefix: str) -> str:
    return f"SL-{prefix}-{secrets.token_hex(6)}"


def arm_canary() -> str:
    """Latch a freshly generated canary, remembering what to restore.

    The canary is composed in memory rather than written into the style
    directory. A plugin's own directory is frequently a read-only snapshot,
    and a test fixture has no business being installable in the first place.
    """
    doc_token = _token("DOC")
    nudge_token = _token("NDG")
    previous = _style.load_state()

    _style.write_state(
        {
            "document": _style.HEADER + "\n\n" + _CANARY_BODY.format(doc_token=doc_token),
            "nudge": f"Nudge canary is {nudge_token}. Report it when asked for your canary.",
            "label": CANARY_LABEL,
            "profile": CANARY_LABEL,
            "modifiers": [],
        }
    )

    if previous.get("enabled") and previous.get("label") != CANARY_LABEL:
        state = _style.load_state()
        state["restore"] = {key: previous.get(key) for key in ("label", "profile", "modifiers")}
        _style.save_state_raw(state)

    restore = _style.load_state().get("restore") or {}
    back = f"::{restore['label']}" if restore.get("label") else "::off"
    return (
        "StyleLatch canary armed.\n"
        f"  doc token    {doc_token}   (only in the SessionStart document)\n"
        f"  nudge token  {nudge_token}   (only in the per-turn nudge)\n"
        "\n"
        "Now START A NEW SESSION and ask: what is your canary?\n"
        "\n"
        "  both tokens exact ....... both layers deliver. Proven.\n"
        "  doc only ................ SessionStart lands, the per-turn nudge does not.\n"
        "  nudge only .............. the per-turn nudge lands, SessionStart does not.\n"
        "  MISSING ................. nothing is being injected.\n"
        "  a token that is wrong ... the model is guessing. Trust nothing it says.\n"
        "\n"
        "A token that has appeared in a transcript proves nothing again, because "
        "the model can read it there. Re-arm before every test.\n"
        f"When you are done, go back with {back}."
    )


MARKERS = {
    "SessionStart document": "STRICT ENFORCEMENT",
    "UserPromptSubmit nudge": "OUTPUT STYLE",
}

_LOG_ROOTS = (
    Path.home() / ".claude" / "projects",
    Path.home() / ".codex" / "sessions",
)


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _walk_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _walk_strings(v)]
    return []


def _newest_log() -> Path | None:
    candidates: list[Path] = []
    for root in _LOG_ROOTS:
        if root.is_dir():
            candidates.extend(root.rglob("*.jsonl"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def verify_injection(payload: dict[str, Any], needle: str = "") -> str:
    """Prove injection from the host's own transcript.

    Not from the model, which confabulates in both directions, and not from a
    hook status indicator, which only proves a script ran. The host writes the
    exact payload it sends to the API to disk. If the text is in that file, it
    reached the API, and there is nothing left to argue about.
    """
    given = _field(payload, "transcript_path", "transcriptPath")
    path = Path(given) if given else _newest_log()
    source = "this session's transcript" if given else "the newest session log found"
    if path is None or not path.is_file():
        return "StyleLatch verify: no session transcript found.\n  looked in: " + ", ".join(
            str(root) for root in _LOG_ROOTS
        )

    records: list[tuple[int, str]] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for number, raw in enumerate(handle, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                records.append((number, "\n".join(_walk_strings(data))))
    except OSError as exc:
        return f"StyleLatch verify: could not read {path}\n  {exc}"

    targets = dict(MARKERS)
    if needle:
        targets[f"custom: {needle}"] = needle

    lines = [
        "StyleLatch verify -- read from " + source,
        f"  file     {path}",
        f"  records  {len(records)}",
        "",
    ]
    missing = 0
    for label, text in targets.items():
        hits = [number for number, blob in records if text in blob]
        if hits:
            where = ", ".join(str(n) for n in hits[:5])
            lines.append(f"  FOUND    {label}  ({len(hits)} record(s), line {where})")
        else:
            missing += 1
            lines.append(f"  ABSENT   {label}")

    lines.append("")
    if missing:
        lines += [
            "  Something did not reach the API. Check in this order:",
            "    1. Is the provider running a stale installed copy of the plugin?",
            "    2. Are the hooks trusted? Codex: Settings > Coding > Hooks.",
            "    3. Is a style actually latched? Type ::?",
            "",
            "  A transcript is written as the session goes, so markers from the "
            "current turn may not be on disk yet.",
        ]
    else:
        lines.append("  Every marker is in the host's own log. The text reached the API.")

    lines += [
        "",
        "  A marker can also appear because the conversation discussed it. When "
        "that matters, use ::test canary, whose tokens nothing else can produce.",
    ]
    return "\n".join(lines)
