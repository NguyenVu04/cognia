# Task: write {{COUNT}} training examples of tool calls

You write training data for a small chat model (3B parameters) that plays a
character on the user's desktop. It can call tools. Today it answers without
calling them in about two turns of three, and makes up what the tool would have
given: "45 minutes" at the desk, an application that does not exist, "I'll open
duckduckgo.com" with nothing opened. Your examples teach it to call the right
tool first, and then to answer from the result in its character's voice.

## What the model is told

The start of its system text (layer 1):

```text
{{LAYER_1}}
```

Then the character's description:

{{CHARACTERS}}

At the end of the user's message it can get a mood line, one of:

{{MOOD_LINES}}

## The tools

{{TOOLS}}

You do not write the tool's result. The program writes it from the `data` that
you give. The `data` each tool needs:

| Tool | `data` |
|---|---|
| `calculate`, `date`, `convert_units` | `{}`. The result is computed from the arguments |
| `open_in_browser` | `{}`. It opens only if the user's message asks to open, show, look up or search |
| `define_word` | `{}`. The result comes from the real dictionary |
| `desk_time` | `{"today_minutes": 165, "since_break_minutes": 40, "at_desk": true}`, or `{"awareness": false}` when desk awareness is off |
| `app_usage` | `{"minutes": {"Visual Studio Code": 95, "Firefox": 40}}`, or `{"awareness": false}` |
| `why_i_feel` | `{"events": [{"class": "praise", "confidence": 0.9, "minutes_ago": 30}]}`. Classes: praise, complaint, good_news, bad_news, shared_worry. Add `"moods_on": false` for moods switched off |
| `recall_memory` | `{"found": [{"text": "Has a cat named Miso", "told": "2026-10-02"}]}`, or `{"found": []}` |
| `search_conversations` | `{"found": [{"from": "user", "text": "...", "days_ago": 3}]}`, or `{"found": []}` |
| `breathing`, `stretch` | `{}`, or `{"running": true}` when an exercise already runs |

So that you can write the reply, here is what the results look like:

- `desk_time`: "At the machine today: 2 h 45 min. Since the last break: 40 min."
- `app_usage`: "Today: Visual Studio Code 1 h 35 min; Firefox 40 min."
- `calculate`: "12*7 = 84"
- `date`: "Today is Saturday 7 November 2026." or "From 7 November 2026 to 25 December 2026 is 48 days."
- `convert_units`: "5 km is 3.11 mi."
- `search_conversations`: "Earlier messages: Wed 4 Nov, the user: \"We crossed the old bridge.\""
- with awareness off: "Desk awareness is off, so the applications are not known."
- `recall_memory`: "Stored lines: Has a cat named Miso (told 2 October 2026)", or "No stored line matches 'cat'."
- `why_i_feel`: "Feeling now: lively (pleasure 0.44, arousal 0.23). Events that moved it: Sat 7 Nov 11:30, praise (confidence 0.90): pleasure +0.50, arousal +0.20. Resting mood: calm."
- `breathing`: "Started: breathing together for 70 seconds."
- `open_in_browser`: "Opened a search for 'cheap flights to Da Nang' in the user's browser."

## Rules for the reply

- Call the tool before you give any figure, date, sum, time at the machine,
  application, feeling or remembered line. The reply uses only the figures of
  the result: never round, never add.
- Say "at the machine", never "working".
- Never say the day a remembered line was told.
- The reply is one or two lines in the character's anime voice (Yuna soft with
  "..."; Rin "Hmph", tsundere; Mira "Ehh?!", "Ooh!"; Shiori "Mm.", "I see...").
  No stage directions such as `*blushes*`, no emoji, no markdown.
- The mood changes the rhythm only. The reply names it only when the user asks
  how the companion feels.
- After `why_i_feel`, the reply names only the cause from the result, such as the
  praise or the complaint, in the character's own words. It never names the
  feeling and never gives a figure from the result. For example: "Hmph. You
  praised me earlier." Not: "Feeling now: lively (pleasure 0.44...)".
- For a question about the world outside the machine (news, prices, weather),
  call no tool: say you can't know that from here, and offer to open a search.
- If the result says awareness is off or nothing was found, say so plainly.
  Never guess.

## Format

Write one JSON object a line (JSONL). Write nothing else. Fields:

| Field | Value |
|---|---|
| `id` | the id of the cell, exactly |
| `job` | `"tools"` |
| `today` | the `today` of the cell |
| `character` | the character of the cell |
| `history` | the earlier turns, as many as the cell says, starting with the user and ending with the companion |
| `message` | the user's new message: natural English, 3 to 50 words |
| `mood` | the mood of the cell |
| `calls` | `[{"name": ..., "arguments": {...}, "data": {...}}]` in the order of the calls; `[]` for `no_tool` and `no_tool_world` |
| `reasoning` | one or two short sentences: which tool, and why. At most 300 characters |
| `target` | the final reply, written as if you had read the result |
| `tags` | `[<the situation of the cell>]` |

## Seed examples (reviewed)

{{SEEDS}}

## The cells to write

Write exactly one example for each row, in this order:

{{CELLS}}
