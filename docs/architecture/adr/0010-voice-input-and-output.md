# 10. Voice input and output on the machine

- **Status:** Proposed
- **Date:** 2026-11-06
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

Specification version 6.0 lets the user speak to the companion (FR-38) and hear its replies (FR-39),
with its mouth moving (UC-26). Everything must stay on the machine (NFR-01, C-03), and the installer
must hold everything (NFR-14). The companion speaks English only (C-06).

C-05 allows four facts from Windows. A microphone and a key combination are new inputs. They are not
facts about the user if the user starts each use, and no other key is read. Section 6.12 of
[`ARCHITECTURE.md`](../ARCHITECTURE.md) forbids `SetWindowsHookEx*` and `GetAsyncKeyState`, because they
can read keystrokes.

## Decision

**whisper.cpp turns speech into text.** `whisper-server.exe` runs as a child process on `127.0.0.1`,
with the model `base.en-q5_1` (57 MiB, MIT). The model supervisor of D-49 starts it at the first need,
and the job object of D-48 ends it with Cognia.

**Kokoro-82M with espeak-ng gives the companion its voice.** Kokoro runs with `onnxruntime` on a
`speech_thread`, and Qt plays the audio. espeak-ng turns words into phonemes, so each name is said
correctly. Each character has its own Kokoro voice. The speed follows the mood (section 6.5.4).

**The loudness of the audio moves the mouth.** The speech thread sends a weight for the VRM presets
`aa`, `ih`, `ou`, `ee` and `oh` to the page.

**The user starts each use.** A key combination through `RegisterHotKey` starts listening, and a second
press or 1.5 s of silence stops it. A button beside the companion listens while the user holds it. A
button in the composer does the same, because the companion is never the only route (FR-28).
`infrastructure/voice` declares `RegisterHotKey` and `UnregisterHotKey`.

**The audio stays in memory.** The audio goes to `whisper-server` and then is dropped. The text goes
into the composer, and the user sends it.

## Consequences

**Positive:**

- Speech in and out with no network and no account.
- No key other than the combination reaches Cognia.

**Negative:**

- espeak-ng is GPL-3.0. The installer distributes it under GPL-3.0, with its licence text and an offer
  of its source. The author checks what this asks of the distribution as a whole before a release.
- The installer grows by about 57 MiB for whisper and about 115 MB for Kokoro.
- Kokoro runs on the CPU. On a machine with no usable GPU, speech and the chat model compete for it.
- Kokoro and `onnxruntime` run inside the Cognia process, so a native fault there stops Cognia.
  `onnxruntime` enters `desktop/uv.lock`.
- Nobody has checked that the Windows release of whisper.cpp holds `whisper-server.exe` (section 12 of
  `ARCHITECTURE.md`).

**Neutral:**

- A user who never speaks pays only the disk space. Neither engine loads before its first use.

## Alternatives considered

**sherpa-onnx with Moonshine, in the process.** Fast and permissive. Rejected for speech to text,
because whisper.cpp follows the pattern of `llama-server`: a child process that the supervisor starts
again after a fault.

**Qt TextToSpeech with the `winrt` engine.** It is in PySide6, it costs no disk space, and it reports
each word. Rejected, because the author's machine has only three English voices for four characters.

**Piper.** Rejected, because its MIT version is archived and its new version is GPL-3.0.

**Kokoro with its dictionary only, with no espeak-ng.** No GPL. Rejected, because each word outside the
dictionary, the user's name too, is spelled letter by letter.

**A held key combination with `GetAsyncKeyState`.** Rejected, because that function is on the
forbidden list of section 6.12.

**A wake word.** Rejected, because the microphone would always be open.
