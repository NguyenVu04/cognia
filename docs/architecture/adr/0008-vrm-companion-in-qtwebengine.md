# 8. The companion as a 3D VRM character in QtWebEngine

- **Status:** Proposed
- **Date:** 2026-10-30
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

FR-25 draws the companion on the desktop, above other windows, and it must never take the keyboard
focus. FR-27 asks that its appearance carries its mood. BR-07 allows ambient motion at any time, and
treats motion addressed to the user as speech. The design document shows an anime-style character.

NFR-07 limits the companion on screen to 3% CPU and 200 MB, and to 1% CPU and 150 MB when hidden. The
specification says that these are its least founded figures, and that ambient motion must be
measured against them.

Cognia is a Python and Qt application, and its repository is public and MIT-licensed.

## Decision

**The companion is a 3D VRM character.** VRM defines a humanoid skeleton and preset expressions with
weights, so a mood can show as a partial expression.

**QtWebEngine with `three-vrm` draws it.** A transparent `QWebEngineView` in `CompanionWindow` loads a
local page. The page uses three.js and `@pixiv/three-vrm`, which are stored in the repository at fixed
versions. Python sends expressions to the page, and the page draws at a limited frame rate.

**Ambient motion stays inside the page.** The page has no function that moves the window. Only the
drag handle in Qt can move it. Addressed motion arrives through `SpeechOutput`, so it passes the
SpeechGate (ADR 0001).

**The page has no network.** A URL interceptor refuses each URL that is not a local file. The profile
is off the record, so Chromium writes nothing to disk.

**Hidden and paused end the render process.** This returns the memory. Showing the companion loads the
page again. This is D-25 in [`ARCHITECTURE.md`](../ARCHITECTURE.md), and it is a proposal.

**The author makes the four characters in VRoid Studio.** Each file keeps its licence beside it, and
the assets are not under the repository's MIT licence. D-26 gives the rules for each file.

## Consequences

**Positive**

- VRM, MToon and expressions work with little new code, and no new language.
- A render crash cannot stop the application, so FR-28 holds.
- Expression weights fit a continuous mood.

**Negative**

- Chromium's memory is likely above the NFR-07 figure. Nobody has measured it.
- The installer grows by QtWebEngine.
- Keyboard focus, the transparent background on Windows and click-through all need proof. Desktop
  Homunculus warns about a black background on some NVIDIA setups.
- The model and the character can share a GPU, so a reply can slow the animation.
- The Chromium processes join the NFR-01 network capture.
- The terms of VRoid Studio on redistribution are not yet confirmed.

**Neutral**

- A short test build must come before other phase 2 work (`ARCHITECTURE.md`, section 12). If the
  measurement fails, the author chooses one of these: a lower frame limit, a changed figure in the
  specification, or frames rendered in advance.

## Alternatives considered

**Layered PNG sprites.** The lowest cost, with Qt alone. Rejected by the author in favour of a real 3D
character.

**Live2D Cubism.** Fluid motion, used by AIRI and Open-LLM-VTuber. Rejected because the SDK has its own
licence agreements, and it needs a Python bridge.

**Vector art.** Small files. Rejected because rasterising costs CPU in each frame, and the anime style is
hard to reach.

**Godot as a child process.** `godot-vrm` has a full MToon, and it may be lighter than Chromium. Rejected
because it adds a language, a toolchain, IPC, and a second window to align with the speech bubble.

**Qt Quick 3D.** One process, native. Rejected because its licence is GPLv3 or commercial, not LGPL, and
`RuntimeLoader` reads glTF with no VRM support. Expressions, MToon and spring bones would all be new work.

**VRM authoring with frames rendered in advance.** The surest option against NFR-07. Kept as the fallback.
It is not real-time 3D, so it has a fixed camera and no continuous blending.
