"""Does the style actually hold? Measured, not assumed.

Everything else in StyleLatch is about *delivering* a style. This module is
about finding out whether it landed, which is the only part of the thesis that
can be wrong.

A style may declare machine-checkable assertions:

    checks: max_sentence_words=25; forbid=Great question; no_headings

After the model replies, the Stop hook reads that reply out of the host's own
transcript, evaluates the assertions, and records the result. The next turn's
nudge then carries one short correction naming what broke.

That closes the loop. Layer 3 stops being a reminder of the rules and becomes
a correction of the specific rule that just failed, which is a far stronger
signal for the same number of tokens.

Limits, stated plainly:

- Only mechanical rules can be checked. "Name the mechanism, not the vibe" is
  not checkable and is not meant to be. This measures the rules that decay in
  ways a regular expression can see -- which, in practice, is most of them.
- Code blocks are stripped before prose rules run. A style that says sentences
  must be short is not talking about a shell command.
- A style with no `checks` costs nothing here beyond one early return.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import _style

# Bounded, like everything else that accumulates. Twenty turns is enough to
# see a trend and small enough that nobody has to think about it.
MAX_RECORDED = 20

# The correction is appended to the per-turn nudge, so it gets its own budget
# rather than eating the nudge's.
MAX_CORRECTION_CHARS = 200

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_SENTENCE = re.compile(r"[^.!?\n]+")


# --------------------------------------------------------------------------
# the rule language
# --------------------------------------------------------------------------
#
# Deliberately tiny. A style file is prose, and a check that needs its own
# manual has already lost. Everything is "name" or "name=value", separated by
# semicolons, on one frontmatter line.

COUNTING_RULES = ("max_sentence_words", "max_reply_lines", "max_reply_chars", "max_paragraphs")
TEXT_RULES = ("forbid", "forbid_opening", "require")
FLAG_RULES = ("no_headings", "no_bullets")
KNOWN_RULES = COUNTING_RULES + TEXT_RULES + FLAG_RULES


def parse_checks(declaration: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (rules, problems). Never raises; a bad rule is reported, not fatal."""
    rules: list[tuple[str, str]] = []
    problems: list[str] = []
    for chunk in (declaration or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, value = chunk.partition("=")
        name = name.strip().lower()
        value = value.strip()
        if name not in KNOWN_RULES:
            problems.append(f"unknown check '{name}'")
            continue
        if name in COUNTING_RULES:
            if not value.isdigit() or int(value) <= 0:
                problems.append(f"{name} needs a positive number, got '{value}'")
                continue
        elif name in TEXT_RULES and not value:
            problems.append(f"{name} needs something to look for")
            continue
        rules.append((name, value))
    return rules, problems


# --------------------------------------------------------------------------
# evaluating a reply
# --------------------------------------------------------------------------


def prose_of(reply: str) -> str:
    """The reply with code removed.

    A rule about sentence length is talking about writing, not about a shell
    command that happens to contain full stops.
    """
    return _INLINE_CODE.sub(" ", _FENCE.sub("\n", reply or ""))


def _longest_sentence(prose: str) -> tuple[int, str]:
    worst, worst_text = 0, ""
    for match in _SENTENCE.finditer(prose):
        sentence = match.group().strip()
        # A bullet marker or a table row is not a sentence.
        if not sentence or sentence.startswith(("|", "-", "*", ">", "#")):
            continue
        words = len(sentence.split())
        if words > worst:
            worst, worst_text = words, sentence
    return worst, worst_text


def evaluate(reply: str, rules: list[tuple[str, str]]) -> list[str]:
    """Return a list of plain-English violations. Empty means the style held."""
    prose = prose_of(reply)
    broken: list[str] = []

    for name, value in rules:
        if name == "max_sentence_words":
            worst, text = _longest_sentence(prose)
            if worst > int(value):
                excerpt = " ".join(text.split()[:6])
                broken.append(f"a {worst}-word sentence (max {value}): “{excerpt}…”")
        elif name == "max_reply_lines":
            count = len(reply.splitlines())
            if count > int(value):
                broken.append(f"{count} lines (max {value})")
        elif name == "max_reply_chars":
            if len(reply) > int(value):
                broken.append(f"{len(reply)} characters (max {value})")
        elif name == "max_paragraphs":
            count = len([p for p in prose.split("\n\n") if p.strip()])
            if count > int(value):
                broken.append(f"{count} paragraphs (max {value})")
        elif name == "forbid":
            if value.lower() in prose.lower():
                broken.append(f"wrote “{value}”")
        elif name == "forbid_opening":
            if value.lower() in prose.lstrip()[:140].lower():
                broken.append(f"opened with “{value}”")
        elif name == "require":
            if value.lower() not in prose.lower():
                broken.append(f"never said “{value}”")
        elif name == "no_headings":
            if any(line.lstrip().startswith("#") for line in prose.splitlines()):
                broken.append("used a markdown heading")
        elif name == "no_bullets":
            if any(line.lstrip().startswith(("- ", "* ")) for line in prose.splitlines()):
                broken.append("used a bullet list")
    return broken


# --------------------------------------------------------------------------
# reading the reply out of the host's transcript
# --------------------------------------------------------------------------


def _texts_of(record: Any) -> list[str]:
    """Every string under a "text" or "content" key, at any depth."""
    found: list[str] = []
    if isinstance(record, dict):
        for key, value in record.items():
            if key in ("text", "content") and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_texts_of(value))
    elif isinstance(record, list):
        for value in record:
            found.extend(_texts_of(value))
    return found


def _is_assistant(record: dict[str, Any]) -> bool:
    for key in ("type", "role"):
        if str(record.get(key, "")).lower() == "assistant":
            return True
    message = record.get("message")
    if isinstance(message, dict) and str(message.get("role", "")).lower() == "assistant":
        return True
    payload = record.get("payload")
    if isinstance(payload, dict):
        return _is_assistant(payload)
    return False


def last_reply(transcript: str) -> str:
    """The most recent assistant message in a .jsonl transcript, or "".

    Transcript shapes are host-specific and undocumented, so this reads
    conservatively: find the last record that identifies itself as an
    assistant message, and take the text out of it. Anything it cannot
    recognise produces "", which is reported rather than guessed around.
    """
    path = Path(transcript)
    if not transcript or not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or not _is_assistant(record):
            continue
        texts = [t for t in _texts_of(record) if t.strip()]
        if texts:
            return "\n".join(texts)
    return ""


# --------------------------------------------------------------------------
# the record
# --------------------------------------------------------------------------


def active_rules() -> tuple[list[tuple[str, str]], list[str]]:
    state = _style.load_state()
    if not state.get("enabled"):
        return [], []
    return parse_checks(str(state.get("checks", "")))


def record(broken: list[str], label: str) -> None:
    state = _style.load_scoped()
    entries = [e for e in state.get("adherence", []) if isinstance(e, dict)]
    entries.append({"at": time.time(), "label": label, "broken": broken})
    state["adherence"] = entries[-MAX_RECORDED:]
    _style.save_state_raw(state)


def recorded() -> list[dict[str, Any]]:
    """Most recent first."""
    return list(reversed(_style.load_scoped().get("adherence", [])))


def clear_record() -> None:
    state = _style.load_scoped()
    state.pop("adherence", None)
    _style.save_state_raw(state)


def take_correction() -> str:
    """One short line naming what the last reply broke, or "".

    This is what makes the loop closed. A reminder of the whole style is a
    weak signal; "you wrote a 34-word sentence, the limit is 25" is a strong
    one, and costs fewer tokens.

    Each breach is delivered exactly once. If the Stop hook is not running --
    an unsupported host, an unreadable transcript -- the last record never
    changes, and a correction that repeated every turn from then on would be
    nagging about a reply the user has long since moved past.
    """
    state = _style.load_scoped()
    entries = [e for e in state.get("adherence", []) if isinstance(e, dict)]
    if not entries:
        return ""

    latest = entries[-1]
    if latest.get("delivered") or not latest.get("broken"):
        return ""
    # A breach recorded under a different style is not this style's problem.
    if latest.get("label") != state.get("label"):
        return ""

    latest["delivered"] = True
    _style.save_state_raw(state)

    text = (
        "STYLE BREACH last reply: "
        + "; ".join(latest["broken"][:2])
        + ". Do not repeat it in this one."
    )
    if len(text) > MAX_CORRECTION_CHARS:
        text = text[: MAX_CORRECTION_CHARS - 1].rstrip() + "…"
    return text


def summary() -> str:
    """A compact adherence report for ::status."""
    rules, problems = active_rules()
    if not rules and not problems:
        return ""

    lines = ["", f"  checks       {len(rules)} declared by the latched style"]
    for problem in problems:
        lines.append(f"               ignored: {problem}")

    past = recorded()
    if not past:
        lines.append("               no replies measured yet")
        return "\n".join(lines)

    clean = sum(1 for entry in past if not entry.get("broken"))
    lines.append(f"  adherence    {clean}/{len(past)} of the last replies held")
    for entry in past[:3]:
        if entry.get("broken"):
            lines.append(f"               broke: {'; '.join(entry['broken'][:2])}")
    return "\n".join(lines)
