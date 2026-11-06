# Resources that Cognia needs beside the code

| | |
|---|---|
| **Document** | How to get and install the files that the code does not hold: the 3D characters, the speech models and the dictionary |
| **Date** | 2026-11-06. Each version and size below was read from its release page on that day |
| **Related** | [`ARCHITECTURE.md`](architecture/ARCHITECTURE.md) sections 6.15, 8.1 and 8.4; D-08, D-26, D-64, D-65; ADR 0008 and ADR 0010 |

The chat model, the embedding model and the two `llama-server` builds are in the
[README](../README.md). This document covers the rest. Cognia downloads nothing
while it runs (NFR-14), so a person gets each file once and puts it in place. The
installer later copies the same files.

**Status today.** Only the dictionary is used by the code. The 3D page, speech to
text and speech are not built yet: the companion window is a placeholder that
writes its face, gesture and exercise as text. Get the other files when their
feature is built.

**Rules for each file** (D-26). Keep its licence file beside it, as the fonts do.
Record its source and the date in a `SOURCE.md` beside it. A file that is not under
the repository's MIT licence says so. A value marked "a person must check" could
not be read automatically.

## 1. The 3D characters

### 1.1 VRM files

| | |
|---|---|
| What | One VRM file for each ready-made character: `yuna`, `rin`, `mira`, `shiori` (the `appearance` of each in `src/resources/characters.toml`) |
| Made with | VRoid Studio, by the author (D-26). Version: a person must check at <https://vroid.com/en/studio> |
| Licence | Textures that the author draws belong to the author. Base content from pixiv is under the VRoid Studio terms, which a person must read before the files enter a public repository (section 12, item 8). Fallback: VRoid sample models D to G, or Open Source Avatars, which are CC0 or CC-BY by their pages |
| Size | Measure each export. ARCHITECTURE section 12, item 6 measures memory with one VRM loaded |
| Put it in | `desktop/src/resources/companion/` (ARCHITECTURE 8.1) |
| Check before it enters | Read the VRM `meta`: `allowRedistribution` must be true or the file must be CC0, and `modification` must allow the changes the project makes. VRoid Studio exports a T-pose; the page turns `upperArm` down about 70 degrees |

**Why.** A real character in three dimensions, with gaze and expressions that have
a weight from 0 to 1, so a mood can show as a slight smile (D-08, section 6.5.3).
Own characters are the only option that gives each ready-made character its own
design (D-26).

### 1.2 Motion clips

| | |
|---|---|
| What | `.vrma` clips: `wave`, `nod`, `bow`, `cheer`, `comfort`, `sheepish`, `think` (the gestures of D-68), and `wait`, `doze`, `breathing`, `stretch` |
| Made with | Blender, by the author (D-64) |
| Licence | The author's own |
| Put it in | `desktop/src/resources/companion/` |

**Why.** Blinking, breathing, sway and gaze are procedural and need no file. Clips
for addressed motion belong to the author, so no licence question remains. Mixamo
forbids distribution of its raw files (D-64).

### 1.3 three.js and three-vrm

| Package | Version | Licence | Source |
|---|---|---|---|
| `three` | 0.187.0 | MIT | <https://www.npmjs.com/package/three> |
| `@pixiv/three-vrm` | 3.5.5 | MIT | <https://www.npmjs.com/package/@pixiv/three-vrm> |
| `@pixiv/three-vrm-animation` | 3.5.5 | MIT | <https://www.npmjs.com/package/@pixiv/three-vrm-animation> |

Put the module files in `desktop/src/resources/companion/` with each licence beside
them. The page loads only local files; an interceptor refuses every other URL
(section 6.15).

**Why.** `three-vrm` already draws VRM, MToon and expressions, inside QtWebEngine,
which the full PySide6 package already holds. A crash of the render process cannot
stop the application (D-08).

## 2. Speech to text: whisper.cpp

| | |
|---|---|
| Program | `whisper-server.exe` from whisper.cpp. The release `v1.9.5` (2026-10-06) has no files. The build `b5454` of the same day has `whisper-bin-x64.zip`, 8 928 640 bytes, at <https://github.com/ggml-org/whisper.cpp/releases/tag/b5454>. That the zip holds `whisper-server.exe`, and its options for the address and the port: a person must check (section 12, item 27) |
| Licence | MIT |
| Model | `ggml-base.en-q5_1.bin`, 59 721 011 bytes, SHA-256 `4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f`, from <https://huggingface.co/ggerganov/whisper.cpp>. MIT |
| Put it in | `desktop/models/runtime/whisper/` for the program and its DLLs; `desktop/models/speech.bin` for the model (ARCHITECTURE 8.4) |

**Why.** The same pattern as `llama-server`: a child process on `127.0.0.1` that
the supervisor starts, watches and ends with Cognia. A native fault cannot stop the
application. The English base model is small (57 MiB) and the companion speaks
English only (C-06). The audio stays in memory until it becomes text (D-65).

## 3. Speech: Kokoro with espeak-ng

| | |
|---|---|
| Weights | `kokoro-v1.0.int8.onnx`, 92 361 271 bytes, release `model-files-v1.0` of <https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0>. The Kokoro-82M weights are Apache-2.0 (<https://huggingface.co/hexgrad/Kokoro-82M>) |
| Voices | `voices-v1.0.bin`, 28 214 398 bytes, same release |
| Runtime | `onnxruntime` 1.31.1 (MIT), from PyPI, through `uv add` when speech is built. `kokoro-onnx` 0.6.1 (MIT) is one way to run the files; the choice is made with the speech feature |
| Phonemes | espeak-ng 1.52.0 (2024-12-12), GPL-3.0, <https://github.com/espeak-ng/espeak-ng/releases/tag/1.52.0>. The release has `espeak-ng.msi`, 12 765 862 bytes. Cognia needs its library and its `espeak-ng-data` folder, with the licence text and an offer of the source (section 12, item 28) |
| Put it in | `desktop/models/voice.onnx`, `desktop/models/voices.bin`, and the espeak-ng library and data beside them (ARCHITECTURE 8.1) |

**Why.** Good quality, a different voice for each character, and names said
correctly. The speed follows the mood (section 6.5.4). Qt TextToSpeech had only
three English voices on the author's machine, and Kokoro with its dictionary alone
spells an unknown word letter by letter, the user's name too (D-65). The cost is
GPL-3.0 for espeak-ng, which the author checks before a release.

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
│   ├── voice.onnx               kokoro-v1.0.int8.onnx
│   ├── voices.bin               voices-v1.0.bin
│   └── espeak-ng library and espeak-ng-data
└── src/resources/
    ├── companion/               VRM files, .vrma clips, three.js, three-vrm, licences
    └── dictionary/              oewn.sqlite3, LICENSE-OEWN.md, WNDB_License.txt, SOURCE.md
```
