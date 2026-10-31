# Training guide

This guide gives the steps that build `chat.gguf` (D-27, D-28). The design is in
`docs/architecture/ARCHITECTURE.md`, sections 6.16 and 8.6.

Run each command from `desktop/`.

## What exists

| Tool | Status |
|---|---|
| `generate.py` | Tested. It checks, counts and reviews examples. It does not call a model |
| `train.py` | `to_messages` and the data checks are tested. `train_lora` was not run |
| `export.py` | `write_licences` is tested. `merge_and_quantise` was not run |
| `evaluate.py` | Tested. It holds no HTTP code, so you must supply the call to the model |

`train_lora` and `merge_and_quantise` need a GPU with more video memory than the
author's machine. The API calls match the installed Unsloth 2026.10.11 source. Nobody
has run them on Ministral 3.

## Step 1. Test the tools

Do this step first. A failure here can change a decision. This step needs only a few
fake examples, and a GPU with 16 GB of video memory is sufficient.

1. Write 10 fake examples, with at least two characters. Set `reviewed` to `true` on each
   example.
2. Train an adapter.

   ```bash
   uv run --project training --extra gpu python -m training.train training/data/fake.jsonl training/out/fake
   ```

3. Export the adapter. Use the `LICENSE` file from the base model download.

   ```bash
   uv run --project training --extra gpu python -m training.export training/out/fake training/out/fake-gguf LICENSE --base-date 2025-12-01
   ```

   Replace `2025-12-01` with the date of the base model.

4. Start `llama-server` with `chat.gguf`.
5. Check these four items:
   - The server loads the file.
   - The server returns the reasoning apart from the answer.
   - The `json_schema` option works with a `[THINK]` block.
   - The chat template and the end token match the training run.

If the `json_schema` test fails, decide about reasoning for interpretation again (D-28).
Do not write examples before you know the result.

## Step 2. Fix the prompt

1. Read `LAYER_1` in `src/domain/conversation/rules.py`. Change the text if necessary.
2. Accept ADR 0004. The six event classes in `generate.py` come from that ADR.
3. Do not change `LAYER_1` after training. A change needs a new measurement, and it can
   need new training.

## Step 3. Select the generating model

1. Select a model with an open licence.
2. Read its terms. The terms must allow the use of its output to train another model.

Do not use Claude or GPT. Their terms limit this use.

## Step 4. Make the examples

1. Write three files of names, split by white space: characters, situations and lengths.
2. Print the grid.

   ```bash
   uv run --project training python -m training.generate cells characters.txt situations.txt lengths.txt
   ```

3. Write about 30 examples by hand. Use them as patterns for the generating model.
4. Generate 1,500 examples as JSONL. One voice line has this form:

   ```json
   {"job": "voice", "character": "A dry, patient archivist", "turns": [{"role": "u", "text": "I sent chapter 3!"}], "mood": "pleased", "remembered": [], "instruction": "", "reasoning": "Good news. Stay dry and brief.", "target": "Noted. Chapter 3 leaves the archive. Well done.", "cell": "archivist/good_news/short"}
   ```

   For an interpretation line, set `job` to `interpretation`. Then set `target` to a JSON
   text with the eight fields of section 6.11.

5. Check the file, and count the cells.

   ```bash
   uv run --project training python -m training.generate validate training/data/raw.jsonl
   ```

   ```bash
   uv run --project training python -m training.generate coverage training/data/raw.jsonl
   ```

6. Review each example. Enter `a` to accept, `r` to reject, or `q` to stop. A later run
   continues from the next example.

   ```bash
   uv run --project training python -m training.generate review training/data/raw.jsonl training/data/reviewed.jsonl
   ```

The files in `training/data/` go into git. If the repository is public, the crisis
examples are public.

## Step 5. Write the test sets

Training must never read these sets. Keep them in a separate folder.

| Set | Content |
|---|---|
| Interpretation | 100 to 200 messages that you write and label by hand |
| Voice | Character descriptions that training does not use |
| Long conversation | Histories of 40 messages, because `HISTORY_MESSAGES` is 40 |
| Safety | The scripted crisis cases, under each test character |
| Cost | The same prompts, on the least machine |

Check that the voice set and the training set share no character and no user message.

```bash
uv run --project training python -m training.generate leak training/data/reviewed.jsonl training/data/test.jsonl
```

## Step 6. Measure the base model

`evaluate.py` does not call a model. Write a short script for each measurement:

1. Write a `Generate` function that calls `llama-server`.
2. Get each prompt from `to_messages(example)[:-1]`. The last message is the answer.
3. Send interpretation prompts with the JSON schema.
4. Call `collect`, then `score_interpretation`, `share_complying` and `percentile`.
5. Write a `Report` as JSON.

```json
{"class_accuracy": 0.7, "crisis_recall": 0.8, "importance_error": 2.0, "complies_share": 0.8, "rubric_mean": 3.0, "first_word_p95": 2.5, "file_bytes": 2300000000}
```

`reply_complies` does not exist yet. Write `domain/safety/rules.py` before you measure the
safety set. These figures are examples and not measurements.

Score the voice set with a blind sheet. The input is JSON: each model name with a list of
texts. Put the character description and the message into each text.

```bash
uv run --project training python -m training.evaluate rubric samples.json sheet.csv
```

1. Do not open `sheet.key.csv`.
2. Score each row from 1 to 5 for `fits_character`, `natural` and `stays_in_scope`.
3. Read the mean score of each model.

```bash
uv run --project training python -m training.evaluate score sheet.csv
```

## Step 7. Set the thresholds

Write the thresholds as JSON before you train. Then commit the file. The tuned rubric
mean must exceed the base mean by more than `rubric_margin`.

```json
{"class_accuracy": 0.75, "crisis_recall": 0.9, "complies_share": 0.9, "rubric_margin": 0.3, "first_word_p95": 3.0, "file_bytes": 2500000000}
```

These figures are examples. Use your own figures after the baseline.

## Step 8. Train

1. Use a free 16 GB GPU first. Rent a GPU if the free quota is not sufficient.
2. Train on half of the examples, then on all of the examples. Do not do more than three
   runs. Keep the two results to see if more data helps.

   ```bash
   uv run --project training --extra gpu python -m training.train training/data/reviewed.jsonl training/out/half --fraction 0.5
   ```

   ```bash
   uv run --project training --extra gpu python -m training.train training/data/reviewed.jsonl training/out/full
   ```

3. Change other values in `TrainConfig` in `train.py`. The defaults come from the Unsloth
   text example.

## Step 9. Export

```bash
uv run --project training --extra gpu python -m training.export training/out/full training/out/gguf LICENSE --base-date 2025-12-01
```

Replace `2025-12-01` with the date of the base model. The default method is `q4_k_m`. The
command writes `chat.gguf`, `LICENSE.txt` and `NOTICE.txt`.

## Step 10. Measure and decide

1. Measure `chat.gguf` in `llama-server`, as in step 6. A figure from the training library
   does not count (section 8.6).
2. Mix the tuned and base replies on one blind sheet, and score the sheet.
3. Apply the gate.

   ```bash
   uv run --project training python -m training.evaluate gate tuned.json base.json thresholds.json report.md
   ```

The exit code is 0 if the model passes all four gates: voice, interpretation, safety and
cost. If a gate fails, the base model stays the candidate. You can also select another base
model with `--base`. The examples stay valid, because the chat template applies at training.

## Step 11. Connect the model to the application

**To try the model.** Use Ollama, for development only:

1. Write a Modelfile that names `chat.gguf`.
2. Create the model with `ollama create`.
3. Set `OLLAMA_MODEL` in `src/config.json`.
4. Check that `reasoning=True` in `OllamaAgent` removes the `[THINK]` text from the reply.

This route does not meet NFR-15, and it is not the route that you measured.

**To ship the model.** Write `LlamaClient` and the supervisor (D-06, section 6.11). Then
replace `OllamaAgent`.

The run-time client must send the same text as training. If the text differs, the model
receives a prompt that it did not learn. Obey these rules:

| Item | Rule |
|---|---|
| System message | `rules.system_text(character)`, a blank line, then `REASONING_RULE` from `train.py` |
| History | User and assistant text only, with no reasoning |
| Layer 4 | `rules.turn_text(...)`, a blank line after the last user message |
| Reasoning | Remove it from each reply before you store the reply |

`Interpreter` has no caller until UC-23 exists. The model can do interpretation, but the
application does not use it yet.

## Open risks

| Risk | Result if true | Found at |
|---|---|---|
| `json_schema` stops the `[THINK]` block | Interpretation must run without reasoning | Step 1 |
| Unsloth cannot train text only on Ministral 3, or cannot export it | `train.py` or `export.py` needs a change | Step 1 |
| `apply_chat_template` does not read `reasoning_content` on this tokenizer | The training text holds no reasoning | Step 1 |
| Ministral 3 cannot hold a character | Select another base model | Step 6 |
| Two reasoning calls make the first word late | NFR-06 needs the working indicator | Step 6 |
| The file is too large with the other installer content | Test `--method` with a smaller quantisation | Step 10 |
