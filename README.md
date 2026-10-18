# IDK Button — Executhon26

A standalone, on-device interpreter: speech → ASR → ambiguity-aware translation, entirely on the
USB-attached Arduino VENTUNO Q's Qualcomm NPU. No cloud calls, no account, no app install — one
shared device anyone can speak to.

- [Backend setup and API](backend/README.md)
- [Hardware integration (GPIO, knob, LEDs)](hardware/README.md)
- [AI/FastAPI teammate handoff](docs/AI_HANDOFF.md)

The model is prepared separately on the board. No model weights, Qualcomm SDK or audio recordings
are distributed in this repository.

## Model architecture

Two models run on the board's Hexagon NPU, nothing leaves the device:

| Stage | Model | Runtime | Evidence |
|---|---|---|---|
| ASR (speech → text) | Whisper, AOT-compiled | **ExecuTorch**, `QnnBackend` (Qualcomm QNN → Hexagon NPU/HTP) | `hardware/live_ui/live_board_audio.py`: loads `qnn/whisper_qnn_fp16.pte` via `_load_for_executorch`, asserts `Runtime.get().backend_registry.is_available('QnnBackend')`, links `libqnn_executorch_backend.so`. Decoding is a hand-rolled greedy+branch token loop (`decoder` method calls), which is also where `asr_alternatives`/`no_speech` quality signals come from. |
| Translation & context resolution | `unsloth/Qwen3.5-2B-GGUF:Q4_0` | **GenieX** server, `--compute npu` | `backend/translate_sentence.py`, `backend/context_resolution.py`; served at `127.0.0.1:18181`, reached from the Mac via `adb forward`. |

**Why confidence is sampled, not self-reported.** A 2B model asked "how confident are you, 0-100%?"
either commits to one answer or invents an unfounded number — this was verified directly against
the board. Instead, `backend/sense_probability.py` resamples the model's own single-letter choice
among a fixed set of candidate meanings at `temperature=1.0`, counts the response frequency as a
vote share, and averages forward/reversed option order to cancel position bias. Only a sufficiently
lopsided, consistent vote (`DEFAULT_THRESHOLD`, 0.85) is treated as real signal; everything else
still asks the user. This is what drives the green "certain" LED and the measured percentages shown
in the "quick meaning check" UI — never a number the model stated about itself.

**Dictionary lookups happen at three different points**, not one shared store:
1. **Before translation** (disambiguation) — a small, hand-reviewed regex lexicon:
   `backend/context_catalog.py` (ground/port/bank/fixed) and `backend/phrasal_lexicon.py` +
   `backend/phrase_context.py` ("make it", "pick up", …). Consulted first, no model call; the
   general LLM resolver and the vote-sampling above are both fallbacks for what this misses.
2. **Right after translation** ("Words worth keeping" panel) — the full Open English Wordnet 2025
   corpus plus the project glossary, in SQLite (`backend/dictionary_store.py`).
3. **On word selection** (rotating the knob to a word) — a small reviewed gloss table
   (`backend/word_meaning.py`), falling back to asking the LLM for a one-word gloss only.

## Restart local servers

Restart FastAPI and the dashboard together so port 8010 is always refreshed with port 8000:

```sh
./tools/restart_local_servers.sh
```

The script uses the repository `.venv`, starts FastAPI on `127.0.0.1:8000`, and starts the
dashboard with its existing command on `127.0.0.1:8010`. FastAPI `/health` is dependency-aware:
it returns 200 only when the ADB-forwarded GenieX model on `127.0.0.1:18181` advertises the
configured Qwen model. Logs are written to `/tmp/exectuthon26-fastapi.log` and
`/tmp/exectuthon26-dashboard.log`.
