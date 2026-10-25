# 4. A hybrid emotion model: rules over a PAD state, the model only interpreting

- **Status:** Proposed
- **Date:** 2026-10-25
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

Version 5.0 of the specification (COG-UCS-001) makes the companion something
that behaves as though it has feelings and a will of its own. It has moods that
come from what happens between it and the user, including sadness at being
ignored (BR-08, UC-23); its mood changes what it does, not only how it sounds
(FR-32, UC-22); it learns how the user works and adjusts itself (UC-24); and it
reflects on its memories in a journal of its own (UC-25).

Three promises from earlier versions still hold and bear directly on how that is
built:

- Every decision, and now every change of feeling, must replay to an identical
  result over the same recorded input (NFR-14). ADR 0001 gets this from a pure
  domain fed an ordered journal.
- Every proactive message, and now every feeling, must be explainable in the real
  figures it came from (NFR-10, UC-17-A2, G-06).
- Everything that does not need the AI model keeps working when it fails (NFR-09).

The obvious way to give a character feelings is to let the language model decide
them: it reads the conversation and says how the character feels. That model is
nondeterministic, slow on an ordinary machine, and cannot say why in figures.

There is prior work to lean on. ALMA (Gebhard, AAMAS 2005) layers affect at three
time scales — emotion, mood and personality — computes emotions by appraisal of
events following the OCC model, and maps them into the PAD space (pleasure,
arousal, dominance). Generative Agents (Park et al., UIST 2023) keep a stream of
memories, retrieve them by recency, importance and relevance, and reflect when
the importance of recent events adds up past a threshold.

## Decision

We compute feelings with rules over a numeric state, and let the AI model only
interpret what the user said.

- **State.** The emotion state is a point in PAD, each axis in [-1, 1], held by
  the domain in `core/`. The mood is that point; a feeling caused by an event is
  a displacement of it. A fixed table maps regions of PAD to the names the user
  sees — pleased, low, restless — so the name is derived, never stored.
- **Temperament.** Each character version carries a temperament (UC-02): how far
  events move it, how fast the mood decays, and a resting point in PAD. The AI
  model reads it from the user's description once, the user sees and may adjust
  it, and it is then stored as fixed values (ADR 0003). It is never re-read on
  the fly.
- **Appraisal by rules.** Each event kind has an appraisal rule: a desirability
  and a weight, scaled by the temperament, producing a displacement in PAD. Desk
  and session events — arriving, being away, a session closed, a message answered
  or passed over, the time of day — are appraised by rules alone.
- **The model interprets, once.** A message the user sends is given to the model
  once, before it enters the queue, to classify it into one of a closed set of
  event kinds — praise, complaint, good news, bad news, shared worry, nothing —
  with an importance. That classification is the event that is journalled. The
  domain never calls the model, and a replay reads the recorded classification
  instead of asking again. An answer outside the closed set, or one the model is
  not confident in, raises no event (UC-23-A3).
- **Decay and floor.** Between events the mood moves towards the resting point
  at the temperament's rate, computed from the injected clock (ADR 0001). Sadness
  from being ignored accumulates with a floor below which pleasure does not fall,
  and the next conversation restores most of it (BR-08).
- **Feeling changes behaviour.** The domain's decision to start a conversation
  (UC-22) takes the mood as an input: arousal and pleasure scale how readily it
  speaks and which kinds it chooses. The `SpeechGate` of ADR 0001 is unchanged
  and still refuses any message it cannot explain.
- **Reflection by threshold.** Each journalled event carries its importance.
  When the sum since the last reflection passes a threshold, the application
  layer asks the model to write journal entries from the retrieved memories; the
  entries, with the `seq`s they drew on, are stored and journalled. Writing them
  is the one place the model produces something the companion keeps, and it is
  outside the domain.
- **Learning.** A learned pattern is a noticed memory item with its evidence
  (ADR 0003). The domain derives patterns from journalled events by rules —
  counts and proportions over sessions, presence, application totals and
  responses — and the model only words a pattern for the user. A self-adjustment
  is a journalled event referring to its pattern, so undoing it is another event.

## Consequences

**Positive**

- NFR-14 holds by construction, as ADR 0001 intended: every input to a feeling
  is a journalled event, including the model's interpretation, so a replay with
  the model switched off reproduces every feeling, decision and pattern.
- UC-17-A2 can show the events behind a feeling, how far each moved it, and the
  temperament values involved, because those are exactly the computation.
- NFR-09 holds: with the model stopped, every event except the user's words is
  still appraised, and the companion still has moods.
- The temperament is a handful of numbers, so G-03 — the character staying the
  same over months — can be checked directly, not only by asking participants.

**Negative**

- The closed set of event kinds limits what the companion can feel about what the
  user said. A nuance the set does not name is felt as nothing. Widening the set
  is a schema-level change to the journal's payload, not a prompt tweak.
- Appraisal weights and decay rates are hand-set and will need tuning by trial,
  and a poorly tuned rule is felt by the user as a character flaw.
- Removing a past feeling (UC-13-A2) means removing journal rows and
  recomputing, so a replay after a removal replays what is left (ADR 0003).
- One more model call per user message, made before the event is queued. On a
  slow machine it delays the feeling, not the reply, but it is still load.

**Neutral**

- PAD names are a lookup table, so changing what a region is called changes no
  stored data.
- The same structure would accept a different appraisal theory later: only the
  rule table changes.

## Alternatives considered

**The model decides the feeling.** The model reads the recent conversation and
returns the character's feeling directly. The most expressive option and the
least code. Rejected because it cannot replay (NFR-14), cannot explain itself in
figures (NFR-10, G-06), and stops working when the model does (NFR-09).

**Rules only.** No model anywhere in the emotion path; the user's words do not
move the feeling. Fully deterministic and cheap. Rejected because a companion that
feels nothing about being thanked or told bad news does not seem to have feelings
at all, which is G-01.

**The model proposes bounded deltas to the state.** The model returns a small
displacement in PAD for each message, capped per turn and journalled. Keeps
nuance and stays replayable. Rejected because the delta is still unexplainable —
"the model moved it by 0.1" is not a reason the user can check — and because a
cap is a guess about how much a model may be trusted with the character's
feelings. Classifying into named events keeps the model to a question it can
answer and the user can see.

**Discrete emotions without a continuous state.** A fixed list of six or eight
emotions, each with an intensity. Easy to draw and to explain. Rejected because
blending and decay are awkward without a space to move in, and ALMA's mapping
into PAD already gives the names back as a lookup.
