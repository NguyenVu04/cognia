# Resources that Cognia needs beside the code

| | |
|---|---|
| **Document** | How to get and install the files that the code does not hold: the 3D characters, the speech models and the dictionary |
| **Date** | 2026-11-08. Each version and size below was read from its release page or from the file on that day |
| **Related** | [`ARCHITECTURE.md`](architecture/ARCHITECTURE.md) sections 6.15, 8.1 and 8.4; D-08, D-26, D-64, D-65; ADR 0008 and ADR 0010 |

The chat model, the embedding model and the two `llama-server` builds are in the
[README](../README.md). This document covers the rest. Cognia downloads nothing
while it runs (NFR-14), so a person gets each file once and puts it in place. The
installer later copies the same files.

**Status today.** Every file below is in use: the 3D page draws the VRM files,
speech to text runs through `whisper-server`, the voice through Kokoro, and
`define_word` reads the dictionary.

**Rules for each file** (D-26). Keep its licence file beside it, as the fonts do.
Record its source and the date in a `SOURCE.md` or `LICENSE.md` beside it. A file
that is not under the repository's MIT licence says so. A value marked "a person
must check" could not be read automatically.

## 1. The 3D characters

### 1.1 VRM files

| | |
|---|---|
| What | One VRM 1.0 file for each ready-made character: `yuna`, `rin`, `mira`, `shiori` (the `appearance` of each in `src/resources/characters.toml`) |
| Made with | VRoid Studio 2.16.0, by the author (D-26) |
| Licence | Each file states the VRM 1.0 licence in its `meta`: `allowRedistribution` true, `modification` `allowModificationRedistribution`. `LICENSE.md` beside each file copies these fields. Base content from pixiv is under the VRoid Studio terms, which a person must read before a public release (section 12, item 8) |
| Size | 15.8 MB to 17.9 MB each |
| Put it in | `desktop/src/resources/companion/<id>/<id>.vrm` |
| Check before it enters | Read the VRM `meta`: `allowRedistribution` must be true or the file must be CC0, and `modification` must allow the changes the project makes. The picture in the character pickers is the `thumbnailImage` of the file |

**Why.** A real character in three dimensions, with gaze and expressions that have
a weight from 0 to 1, so a mood can show as a slight smile (D-08, section 6.5.3).
Own characters are the only option that gives each ready-made character its own
design (D-26).

### 1.2 Motion

No file. Every motion — breathing, blinking, sway, gaze, waiting, dozing, each
gesture, the exercises and the mouth — is code in
`desktop/src/resources/companion/page/companion.js`, which turns the humanoid bones
and sets the expressions of the VRM (D-64). The same code works on the four
characters, because they have the same humanoid bones.

### 1.3 three.js and three-vrm

| Package | Version | Licence | Source |
|---|---|---|---|
| `three` | 0.180.0 | MIT | <https://www.npmjs.com/package/three> |
| `@pixiv/three-vrm` | 3.5.5 | MIT | <https://www.npmjs.com/package/@pixiv/three-vrm> |

`three-vrm` 3.5.5 is built against `three` 0.180.0, so that version is kept. The
module files are in `desktop/src/resources/companion/vendor/`, each package with its
licence and `SOURCE.md`. The page loads only local files; an interceptor refuses
every other URL (section 6.15).

**Why.** `three-vrm` already draws VRM, MToon and expressions, inside QtWebEngine,
which the full PySide6 package already holds. A crash of the render process cannot
stop the application (D-08).

## 2. Speech to text: whisper.cpp

| | |
|---|---|
| Program | `whisper-server.exe` from whisper.cpp, with its DLLs. It takes `--host`, `--port`, `--model`, `--language` and `--threads`, and answers `POST /inference` |
| Licence | MIT |
| Model | `ggml-base.en-q5_1.bin`, 59 721 011 bytes, SHA-256 `4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f`, from <https://huggingface.co/ggerganov/whisper.cpp>. MIT |
| Put it in | `desktop/models/runtime/whisper/` for the program and its DLLs; `desktop/models/speech.bin` for the model (ARCHITECTURE 8.4) |

**Why.** The same pattern as `llama-server`: a child process on `127.0.0.1` that
starts at the first use and ends with Cognia. A native fault cannot stop the
application. The English base model is small (57 MiB) and the companion speaks
English only (C-06). The audio stays in memory until it becomes text (D-65).

## 3. Speech: Kokoro

| | |
|---|---|
| Weights | `kokoro-v1.0.onnx` (32-bit), 325 505 369 bytes, release `model-files-v1.1` of <https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1>. The Kokoro-82M weights are Apache-2.0 (<https://huggingface.co/hexgrad/Kokoro-82M>) |
| Voices | `voices-v1.0.bin`, 28 214 398 bytes, same release |
| Runtime | `kokoro-onnx` 0.6.1 (MIT) with `onnxruntime` 1.31.1 (MIT), in `desktop/uv.lock` |
| Phonemes | espeak-ng, from the `espeakng-loader` 0.2.4 package that `kokoro-onnx` installs: it holds `espeak-ng.dll` and `espeak-ng-data/`. espeak-ng is GPL-3.0; the package has no licence file and does not state its espeak-ng version (section 12, item 28) |
| Put it in | `desktop/models/voice.onnx` and `desktop/models/voices.bin`. espeak-ng needs no file in `desktop/models/` |

**Why the 32-bit file.** On the author's laptop the 8-bit file
(`kokoro-v1.0.int8.onnx`, 114 119 327 bytes) took 8.1 s to make 3 s of speech, and
the 32-bit file took 0.76 s, measured on 2026-11-08. Only the 32-bit file can speak
a reply while it streams.

**Why Kokoro.** Good quality, a different voice for each character, and names said
correctly. The speed follows the mood (section 6.5.4), and Kokoro gives the time of
each phoneme, which moves the mouth. Qt TextToSpeech had only three English voices
on the author's machine, and Kokoro with its dictionary alone spells an unknown
word letter by letter, the user's name too (D-65). The cost is GPL-3.0 for
espeak-ng, which the author checks before a release.

## 4. The dictionary of `define_word`

| | |
|---|---|
| Data | Open English WordNet, 2025 edition, `english-wordnet-2025.xml.gz`, 11 363 503 bytes, <https://github.com/globalwordnet/english-wordnet/releases/tag/2025-edition> |
| Licence | Two licences: the Open English WordNet work is under CC BY 4.0, and the data from Princeton WordNet is under the WordNet License. Both files ship: `LICENSE-OEWN.md` and `WNDB_License.txt`. Attribution goes to both teams |
| Built file | `desktop/src/resources/dictionary/oewn.sqlite3`, 14 757 888 bytes, committed. The first 3 definitions of each word for each part of speech |
| Build it again | `task dictionary -- <path to english-wordnet-<year>.xml.gz>`, then update `SOURCE.md` beside it |

**Why.** A small model is often wrong about the meaning of a rare word, and a
dictionary on the machine needs no network (D-59, D-69).

## 5. Where everything goes

```text
desktop/
├── models/                      Git ignores it; placed by hand (README)
│   ├── chat.gguf, embedding.gguf, runtime/vulkan, runtime/cpu   (README)
│   ├── runtime/whisper/whisper-server.exe and its DLLs
│   ├── speech.bin               ggml-base.en-q5_1.bin
│   ├── voice.onnx               kokoro-v1.0.onnx (32-bit)
│   └── voices.bin               voices-v1.0.bin
└── src/resources/
    ├── companion/<id>/          <id>.vrm and LICENSE.md, for each character
    ├── companion/page/          index.html and companion.js: the 3D page and all motion
    ├── companion/vendor/        three.js, three-vrm, their licences, SOURCE.md
    └── dictionary/              oewn.sqlite3, LICENSE-OEWN.md, WNDB_License.txt, SOURCE.md
```
