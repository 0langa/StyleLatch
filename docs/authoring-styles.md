# Writing a style

A style is one Markdown file. Getting the file right takes five minutes.
Getting it to still be obeyed on reply twenty is the actual work, and that is
what this page is about.

## Where to put it

| Goal | Directory |
|---|---|
| This repository, committed, shared with everyone working in it | `<repo>/.stylelatch/styles/` |
| Yours, everywhere, survives plugin updates | `$STYLELATCH_HOME/styles/` — usually `~/.stylelatch/styles/` |
| A built-in, shipped to everyone | `styles/` in this repository, via a pull request |

Inside any of those, `PROFILES/` holds whole voices and `MODIFIERS/` holds
single rules that stack onto one. Type `::?` to see the exact paths on your
machine rather than guessing.

Nothing is created for you. An empty directory you did not ask for is clutter,
and `::?` naming the path is enough.

## The file

```markdown
---
id: "50"
name: review-voice
nudge: Lead with the verdict. One finding per paragraph. Cite file:line. No praise.
---

Every reply is a review, not a conversation.

Open with the verdict in one line: ship, ship with changes, or do not ship.

Then one finding per paragraph, ordered by severity. Each finding names the
file and line, states what breaks, and stops. Do not suggest a fix unless the
fix is shorter than the explanation of the problem.

Never open with praise. Never close with an offer of more help.
```

| Key | |
|---|---|
| `id` | Short handle for `::50`. Unique within its source. Falls back to the filename prefix. |
| `name` | What you type: `::review-voice`. Falls back to the rest of the filename. |
| `nudge` | Required on a profile. Injected every turn. Hard cap 300 characters. |
| `checks` | Optional. Machine-checkable assertions, measured against each reply. |

The body is injected verbatim. Write it as rules addressed to the model.

## Four rules that decide whether it holds

### 1. Write rules, not a mood

A model can obey "two sentences maximum". It cannot obey "be concise" in any
repeatable way — every reply will be as concise as that reply happened to feel.

Every line should be something you could check a reply against.

| Instead of | Write |
|---|---|
| Be concise | Answer in one line. Add detail only if asked. |
| Be technical | Name the function and file. Cite `file:line`. |
| Don't ramble | One idea per sentence. No sentence over 20 words. |
| Be friendly | (Delete it. This is a mood, and it is the default anyway.) |

### 2. The nudge is the hard part

It goes into **every single turn**, so it is capped at 300 characters and
should aim at about thirty words. That is not enough room for a summary of the
profile, and trying to write one is the usual mistake.

Write the two or three rules that **decay first** instead. Ask: on reply five,
which rule breaks? That rule goes in the nudge.

In practice the answer is nearly always a negative rule. Models re-acquire the
preamble, the closing offer of help, and the summarising paragraph long before
they forget how long a sentence should be.

### 3. Say what not to do

Most drift is addition, not omission. The style is still there; the habits grew
back around it.

```
Never open with a restatement of the question.
Never close with an offer of more help.
Never add a summary section to a reply under ten lines.
```

These are worth their space because they are the ones that fail.

### 4. Style governs how, never what

A style controls length, structure, vocabulary, ordering, what to include and
what to leave out.

It does not control what the model is allowed to do. A style that tries to skip
a confirmation, suppress an error, hide what was not verified, or let the model
claim success without evidence is a bug, and it will be rejected as a built-in.
See [SECURITY.md](../SECURITY.md).

`silent-run` is the instructive edge: it suppresses **narration** between tool
calls, and it says in its own text that it never suppresses a required
confirmation, a hard blocker, or an unauthorised destructive action. A style
that removes output has to name what it will still say.

## Making a rule checkable

A style can declare assertions that are measured against the reply after it is
written. Breaking one puts a correction in the *next* turn's nudge, naming the
specific rule rather than restating the whole style.

```yaml
checks: max_sentence_words=25; forbid=let me know if; forbid_opening=Great question
```

One line, semicolon-separated, `name` or `name=value`.

| Rule | Catches |
|---|---|
| `max_sentence_words=N` | the longest prose sentence |
| `max_reply_lines=N` | a reply that sprawled |
| `max_reply_chars=N` | the same, by size |
| `max_paragraphs=N` | a two-line answer that became an essay |
| `forbid=<text>` | a phrase anywhere, case-insensitive |
| `forbid_opening=<text>` | a phrase in the first 140 characters only |
| `require=<text>` | something that had to be said and was not |
| `no_headings` | markdown headings in a reply that should be prose |
| `no_bullets` | a bullet list where sentences were asked for |

Modifiers can add checks too, and they accumulate: `::terse+show-evidence`
enforces both sets.

### Choosing what to check

Check the rule you expect to **decay**, not the rule you care most about. They
are rarely the same. `terse` cares most about leading with the answer, which no
regular expression can see — so it checks the four phrases that creep back
instead:

```yaml
checks: max_sentence_words=25; forbid=let me know if; forbid=hope that helps;
        forbid=feel free to; forbid=anything else
```

Two things not to do:

- **Do not check what code will trip.** Fenced and inline code is stripped
  before prose rules run, so `max_sentence_words` will not fire on a shell
  command — but `forbid=error` still will, if the word appears in prose.
- **Do not check taste.** A check that fires on a reply that was actually fine
  trains you to ignore the correction, and then the mechanism is worthless.

`::status` reports how many of the recent replies held, and what broke:

```
  checks       5 declared by the latched style
  adherence    7/9 of the last replies held
               broke: wrote "let me know if"; a 31-word sentence (max 25)
```

`::test` fails on a `checks` line it cannot parse. A check that is silently
never enforced is the worst outcome: the style looks measured and is not.

## Modifiers

A modifier is a single rule that stacks onto any profile. Keep it to one idea.

```markdown
---
id: "03"
name: show-evidence
nudge: Show the command and its real output. Never claim green without pasting it.
---

Never claim something works without showing the evidence.

Paste the command you ran and its actual output. If you did not run it, say so
in those words. "Should work" is not a result.
```

Modifiers compose in the order given, after the profile. Their nudges are
concatenated onto the profile's, and the whole thing is truncated at 300
characters — so stacking four modifiers with long nudges will silently cost you
the end of the last one. `::test` reports the real length.

## Checking it

```
::test          parses every file, composes every profile, fails on a
                missing nudge or a body that will not parse
::<name>        latch it
::<name>! ...   try it on one message without latching it
::status        confirms what is latched and what it costs per turn
```

Then use it for a real task, not a test question. A style that survives "say
hello" tells you nothing.

### Proving it is actually arriving

Your own reading of a reply is weak evidence, and the model's account of its
context is no evidence at all — it confabulates in both directions.

```
::test verify   searches the host's own transcript on disk for the injection
::test canary   plants two high-entropy tokens, one per layer
```

For the canary: arm it, start a **fresh** session, and ask *what is your
canary?* Both tokens back means both layers deliver. One token tells you
exactly which layer is broken. A token that comes back wrong means the model is
guessing, and nothing it says about its context can be trusted.

Re-arm before every test. A token that has appeared in a transcript proves
nothing again, because the model can read it there.

## Overriding a built-in

Give your file the same `name` as the built-in and put it in a more specific
source. `~/.stylelatch/styles/PROFILES/01-eli5.md` replaces the shipped `eli5`
everywhere, for you.

`::?` will list what you shadowed, so it stays visible rather than becoming a
mystery six months later.
