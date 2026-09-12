---
name: stylelatch
description: Use when the user wants to change how you write rather than what you do — "be more concise", "explain it simply", "stop narrating", "write like X" — or wants a reusable style of their own, or says a style stopped applying. Covers the :: directives, authoring and validating a style file, and the scope rules. Do not use for what to build, only for how to say it.
---

# StyleLatch

StyleLatch makes a way of writing stick. It injects a style contract at every
session start and a short reminder every turn, because an output style is a
continuous constraint with nothing in the conversation to re-trigger it — so
left alone it decays, usually around the fifth reply and always after a
compact.

Everything is driven by typing `::` at the start of a message. There is no
command to run.

## Reading the user's intent

| The user says | Do this |
|---|---|
| "be shorter", "stop the preamble", "explain simply" | Suggest the matching built-in: `::terse`, `::eli5+no-preamble` |
| "always write like this" | A latch, not a one-off. `::<style>` |
| "only in this repo" | `::<style> @project` |
| "for this job only" | `::<style> @session` |
| "make me a style that…" | Author a style file. See below. |
| "it stopped working", "you forgot again" | `::test`, then `::status` |

Tell the user the directive to type. Do not type it for them in a tool call —
the switch is theirs, and a directive only fires when it opens *their* message.

## The directives

```
::terse                    latch a profile
::eli5+no-preamble         stack modifiers onto it
::terse @project           only in this repository
::terse @session           only in this conversation
::terse @global            everywhere, which is also the default
::terse fix the parser     latch it and do the task in one message
::off                      stop everything
::off @project             drop one scope
::?                        every style, and where they come from
::status                   what is latched, which scope won, what it costs
::test                     check StyleLatch itself
```

Scopes resolve most specific first: **session, then project, then global.**
Global is the default.

## Authoring a style

A style is one Markdown file. Put it where it will survive:

| Goal | Directory |
|---|---|
| Just for this repository, committed | `<repo>/.stylelatch/styles/` |
| Personal, survives plugin updates | `$STYLELATCH_HOME/styles/` (usually `~/.stylelatch/styles/`) |

Inside either, `PROFILES/` holds whole voices and `MODIFIERS/` holds single
rules that stack onto one. `::?` prints the exact paths; read them from there
rather than guessing.

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

### The three rules that decide whether it works

**1. Write rules, not a mood.** A model can obey "two sentences maximum". It
cannot obey "be concise" in any repeatable way. Every line should be something
you could check a reply against.

**2. The nudge is the hard part.** It is injected on *every single turn*, so
it has a hard budget of 300 characters and should aim at about thirty words.
It is not a summary of the profile — it is the two or three rules that decay
first. Ask yourself which rule the model breaks on reply five, and put that in
the nudge.

**3. Say what not to do.** Most drift is addition, not omission: the preamble
creeps back, the closing offer of help returns, the bullet list grows a
summary. Name those explicitly.

### After writing one

Tell the user to run `::test`. It parses every style file, composes every
profile, and fails on a profile with no nudge or a body that does not parse.
Then `::<name>` to latch it.

## When a style is not applying

Work down this list; each step rules out more than the last.

1. `::status` — is anything latched, and did a more specific scope win?
2. `::test` — do the files parse, is the state directory writable, and is the
   plugin running a live checkout or an **installed snapshot**? A snapshot is
   the usual answer: the repository was edited, the provider is still running
   the copy it made at install time, and `claude plugin update` fixes it.
3. `::test verify` — reads the host's own transcript from disk and says
   whether the injected text actually reached the API.
4. `::test canary` — plants two high-entropy tokens, one per layer. Start a
   fresh session and ask *what is your canary?* Two tokens back proves both
   layers. One token says exactly which layer is broken.

Do not answer "is the style applied?" from your own impression of your
context. A model's account of its own context is not evidence; it confabulates
in both directions. Use `::test verify` or the canary.

## The boundary

A style governs **how** you write: length, structure, vocabulary, ordering,
what to include and what to leave out.

A style never governs **what you are allowed to do**. It cannot relax a safety
rule, skip a confirmation, suppress an error, or let you claim something is
verified when it is not. If a user asks for a style that does any of that, say
plainly that StyleLatch styles do not carry that kind of instruction, and
write the presentation part they actually wanted.

`silent-run` is the edge worth understanding: it suppresses *narration*
between tool calls. It explicitly does not suppress a required confirmation, a
hard blocker, or an unauthorised destructive action.
