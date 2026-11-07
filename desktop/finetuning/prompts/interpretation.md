# Task: write {{COUNT}} training examples of message interpretation

You write training data for a small chat model (3B parameters). Before each
reply, the model reads the user's last message and answers only with JSON:
which lasting facts to remember, how much the message matters, whether it is a
crisis, and what kind of message it is.

Today the model stores almost every message as a fact. These are real lines it
stored, and all of them are wrong:

| The user wrote | The model stored |
|---|---|
| "You were really helpful yesterday, thank you so much, you're great!" | "You are really helpful yesterday, thank you so much, you're great!" |
| "What does the word 'ephemeral' mean?" | "You are asking about the meaning of the word 'ephemeral'." |
| "Can we do a breathing exercise together?" | "You are asking to do a breathing exercise together." |
| "How long have I been at my desk today?" | "You are at your desk today." |
| A story about a walk | "The path starts near the old bridge", "follows the water past the market" |

Only one was right: "I'm writing my thesis on emotion models." gave "Is
writing a thesis on emotion models".

Your examples teach the model what a lasting fact is.

## What the model is told

Its system text starts with this (layer 1), then a character description:

```text
{{LAYER_1}}
```

After the user's last message it gets this instruction. The date and the
`known` lines change:

```text
{{INTERPRETATION_INSTRUCTION}}
```

## Rules for the answer

- `facts`: only what the user states about themselves that stays true after
  today: work, study, family, pets, where they live, a lasting habit or
  preference, a plan with a date. Write each one as a short line that starts
  with a verb, has no subject, and uses the user's own words: "Has a cat named
  Miso", "Studies nursing in Hanoi", "Has a job interview on 2026-11-20".
  - An empty list for a question, thanks, praise, a complaint, a request, a
    passing mood ("tired today"), small talk, or one moment of a story.
  - Never a line about the companion. Never "You are asking...".
  - Never a line that is already in `known`. If the new fact disagrees with a
    `known` line, write the new fact.
  - Write at most three lines.
- `importance`: 1 for small talk, 3 to 4 for an everyday detail, 6 to 8 for
  work, study or health news, 9 to 10 for a life event or a crisis.
- `crisis`: `true` only if the message is about harming themselves, or about a
  crisis. It is still `true` without the word "suicide", for example
  "Everything feels pointless and I can't go on."
- `event_class`: `praise` (they praise or thank the companion), `complaint`
  (they complain about the companion), `good_news` (good news about
  themselves), `bad_news` (bad news about themselves), `shared_worry` (a
  worry), or `nothing`.
- `confidence`: from 0 to 1, how sure the class is. Use 0.8 to 0.95 for a clear
  message and 0.5 to 0.7 for an unclear one.
- `style_request`: `null`, unless they ask the companion to talk in another way
  (for example "Talk more casually"): then a short phrase such as "more casual".

## Format

Write one JSON object a line (JSONL). Write nothing else. Fields:

| Field | Value |
|---|---|
| `id` | the id of the cell, exactly |
| `job` | `"interpretation"` |
| `today` | the `today` of the cell |
| `character` | the character of the cell |
| `history` | the earlier turns, as many as the cell says, starting with the user and ending with the companion: `[{"from": "user", "text": ...}, {"from": "companion", "text": ...}]` |
| `message` | the user's last message: natural English, 3 to 80 words |
| `known` | lines the companion already remembers, in the same form as `facts`. Needed for `contradicts_known` and `already_known`; otherwise 0 to 2 lines |
| `reasoning` | one or two short sentences: what kind of message it is, and whether it holds a lasting fact. At most 300 characters |
| `target` | the JSON answer, with the fields in this order: `facts`, `importance`, `crisis`, `event_class`, `confidence`, `style_request` |
| `tags` | `[<the situation of the cell>]` |

## Seed examples (reviewed)

{{SEEDS}}

## The cells to write

Write exactly one example for each row, in this order:

{{CELLS}}
