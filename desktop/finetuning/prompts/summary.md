# Task: write {{COUNT}} training examples of conversation summaries

You write training data for a small chat model (3B parameters). When a
conversation grows long, the model summarizes the older messages. Only the
model reads the summary: it goes at the end of the system text after the words
"Earlier in this conversation, in short: ".

Today the model starts its summary with a heading, `**Summary:** The user
begins by...`, and it sometimes adds things that nobody said. Your examples
teach it a plain paragraph that holds only what the messages say.

## What the model is told

The system text is exactly:

```text
{{SUMMARY_SYSTEM}}
```

The user text is the earlier summary, if any, then the messages:

```text
Earlier summary: <the earlier summary>

Messages:
User: ...
Companion: ...
```

## Rules for the summary

- One plain paragraph. No heading, no "Summary:", no markdown, no list.
- Third person: "The user...", "The companion...".
- At most 1 500 characters. Shorter is better if nothing is lost.
- Keep names, dates, numbers, what the user asked for, and what the two agreed.
- Write only what the messages say. Never add a reason, a feeling or a judgement
  that nobody said.
- With an earlier summary, merge it and the new messages into one summary.

## The conversations

Make each conversation an everyday chat between a user and one of four
companions: Yuna (gentle), Rin (teasing), Mira (energetic) or Shiori (quiet).
The companion's lines are in an anime voice ("Ehh?!", "Hmph.", "Mm.", "...").
Include some names, dates and numbers, so the summary must keep them. Vary the
subjects: study, work, family, a hobby, a trip, a bad day, plans.

## Format

Write one JSON object a line (JSONL). Write nothing else. Fields:

| Field | Value |
|---|---|
| `id` | the id of the cell, exactly |
| `job` | `"summary"` |
| `today` | the `today` of the cell |
| `previous` | for `with_previous`: the earlier summary, under 600 characters. Otherwise leave it out |
| `messages` | the messages, starting with the user: `[{"from": "user", "text": ...}, {"from": "companion", "text": ...}]` |
| `target` | the summary |
| `tags` | `[<the situation of the cell>]` |

## Seed examples (reviewed)

{{SEEDS}}

## The cells to write

Write exactly one example for each row, in this order:

{{CELLS}}
