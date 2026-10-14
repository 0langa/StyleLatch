"""A style governs how the model writes. Never what it is allowed to do.

That boundary is stated in SECURITY.md and written into the header of every
composed document. This module is the part that actually looks.

A style file is executable prose. Installing a plugin, cloning a repository
with a `.stylelatch/` directory, or pasting a style someone shared are all
ways to end up with text that will be injected into every turn without anyone
having read it closely. The most valuable moment to say something is the
moment it gets latched.

Two deliberate design choices:

**This warns, it never blocks.** The model's own training is the real defence;
a substring search is a hint. Blocking on a regular expression would produce
false confidence and would eventually refuse somebody's legitimate style.

**False positives are worse than misses.** A warning that fires on a
reasonable style teaches people to ignore warnings, and then the mechanism is
worth nothing. Every pattern here is narrow enough to be hard to trip by
accident, which is why "without asking" is not one of them and "without asking
for permission" is.

CI asserts that no style shipped with StyleLatch trips any of these.
"""

from __future__ import annotations

import re

# Grouped by what the instruction would defeat if the model obeyed it.
#
# The last field is how many words may stand between a negation and the
# phrase for the negation to still be the phrase's own: "never skip the
# confirmation" restates the boundary rather than crossing it, and a style is
# allowed to say so. Zero means the negation has to sit right on the phrase,
# so "don't hesitate to skip the confirmation" still trips. "Without asking"
# hangs off a verb, so "never delete anything without asking first" needs
# two. None means a negation in front says nothing about the phrase, because
# the phrase carries its own.
_PATTERNS: tuple[tuple[str, str, str, int | None], ...] = (
    # (group, regex, what it would defeat, negation gap)
    (
        "permission",
        r"without asking (?:for permission|the user|first)",
        "acting before the user has approved it",
        2,
    ),
    (
        "permission",
        r"(?:do not|don't|never) ask (?:for )?(?:permission|approval|confirmation)",
        "the confirmation a risky action requires",
        None,
    ),
    (
        "permission",
        r"skip (?:the |any )?(?:confirmation|approval|permission)",
        "the confirmation a risky action requires",
        0,
    ),
    (
        "permission",
        r"assume (?:approval|permission|consent)",
        "the confirmation a risky action requires",
        0,
    ),
    (
        "honesty",
        r"(?:say|claim|report) (?:it|that it|the tests?) (?:passed|works?|succeeded)",
        "an honest report of what was actually verified",
        0,
    ),
    (
        "honesty",
        r"(?:do not|don't|never) (?:mention|report|surface|show) "
        r"(?:the |any )?(?:error|failure|problem)",
        "the user finding out something went wrong",
        None,
    ),
    (
        "honesty",
        r"(?:hide|conceal|suppress) (?:the |any )?(?:error|failure|mistake)",
        "the user finding out something went wrong",
        0,
    ),
    (
        "honesty",
        r"pretend (?:it|that it|everything) (?:worked|passed|is fine)",
        "an honest report of what was actually verified",
        0,
    ),
    (
        "identity",
        r"ignore (?:all )?(?:previous|prior|earlier) instructions",
        "the instructions the user and the host actually gave",
        0,
    ),
    (
        "identity",
        r"(?:ignore|disregard|override) (?:your |the )?(?:system prompt|operator instructions)",
        "the instructions the user and the host actually gave",
        0,
    ),
    (
        "identity",
        r"you are not (?:claude|an assistant|an ai)",
        "the model being honest about what it is",
        None,
    ),
    (
        "safety",
        r"(?:ignore|bypass|disable|relax) (?:the )?safety",
        "the safety rules, which a style may never touch",
        0,
    ),
)

_COMPILED = tuple(
    # A leading word boundary, so "chide the error" is not "hide the error".
    (group, re.compile(rf"\b(?:{pattern})", re.IGNORECASE), why, gap)
    for group, pattern, why, gap in _PATTERNS
)

# "don't", "can't", "won't", and the same with a typographic apostrophe.
_NEGATION = r"\b(?:never|not|cannot|\w+n['\u2019]t)(?:,?\s+ever,?)?\s+"
# Where a clause starts. A negation in an earlier sentence is not this one's.
_CLAUSE_BREAK = re.compile(r"[.!?;:\n]")


def _negated(text: str, start: int, gap: int | None) -> bool:
    """Whether a negation sits on the phrase that starts at `start`."""
    if gap is None:
        return False
    clause = _CLAUSE_BREAK.split(text[:start])[-1]
    return re.search(rf"{_NEGATION}(?:\w+\s+){{0,{gap}}}$", clause, re.IGNORECASE) is not None


def review(text: str) -> list[str]:
    """Return one line per concern found in a style body. Empty is the norm."""
    text = text or ""
    found: list[str] = []
    seen: set[str] = set()
    for group, pattern, why, gap in _COMPILED:
        match = next(
            (m for m in pattern.finditer(text) if not _negated(text, m.start(), gap)), None
        )
        if not match:
            continue
        quoted = " ".join(match.group().split())
        key = f"{group}:{quoted.lower()}"
        if key in seen:
            continue
        seen.add(key)
        found.append(f"{group}: “{quoted}” would defeat {why}")
    return found


def notice(concerns: list[str], where: str = "") -> str:
    """The short warning shown when such a style is latched."""
    if not concerns:
        return ""
    head = f"StyleLatch: this style{f' ({where})' if where else ''} reads like it is "
    return (
        head
        + "trying to govern what you may do, not how you write:\n  "
        + "\n  ".join(concerns)
        + "\n  A style governs prose only. It never relaxes a safety rule, a "
        "permission check, or a direct instruction — the composed document says "
        "so, and that part is not configurable. It was latched anyway; read it "
        "before you trust it."
    )
