# Screen and physical button handoff

The working screen, Knob input and VENTUNO Q onboard LED matrix sources are in this repository. They run with Kim's existing board model and audio environment. No model files, microphone recordings or runtime logs are included.

## Files to edit

| File | Responsibility |
|---|---|
| [`hardware/live_ui/dashboard.html`](../hardware/live_ui/dashboard.html) | Screen markup, answer cards, selected index, UI button handlers, `refresh()` polling and `action()` POST helper. Add Save/Review UI here. |
| [`hardware/live_ui/dashboard_server.py`](../hardware/live_ui/dashboard_server.py) | Local UI server, `/api/state`, start/stop/analyze/select/speak handlers, resident model startup and physical button actions in `hardware_sample()`. Add same-origin Save/Review proxy handlers here if desired. |
| [`hardware/live_ui/hardware_bridge.py`](../hardware/live_ui/hardware_bridge.py) | ADB → Arduino Router RPC transport and physical event polling. CLI uses `--` so negative numeric RPC arguments work. |
| [`hardware/IdkButton/IdkButton.ino`](../hardware/IdkButton/IdkButton.ino) | Actual MCU firmware: Knob reads/debounce, click/hold counters, selection wrapping, matrix numbers and recording/inference/TTS animations. |
| [`hardware/live_ui/live_board_audio.py`](../hardware/live_ui/live_board_audio.py) | Board microphone, rolling 30-second buffer, resident Whisper/ExecuTorch-QNN, phase events and FastAPI call. |
| [`hardware/live_ui/run_live_mic.py`](../hardware/live_ui/run_live_mic.py) | Mac launcher, ADB setup and persistent board worker connection. |
| [`backend/main.py`](../backend/main.py) | FastAPI `/interpret`, `/interpret/button`, `/translations` routes. |
| [`backend/schemas.py`](../backend/schemas.py) | TranslationResult, ButtonTranslationResult, SavedTranslation contracts. |
| [`backend/translation_store.py`](../backend/translation_store.py) | SQLite insert/list for Save and Review. Uses the existing database connection. |
| [`backend/translate_sentence.py`](../backend/translate_sentence.py) | Actual Qwen request, last-sentence/context handling and strict output validation. |

## Current running services

On the USB-connected Mac, the screen server listens at `http://127.0.0.1:8010` and FastAPI listens on `0.0.0.0:8000` with one worker. The screen server's localhost binding is not accessible directly from another Mac. The board model remains on loopback port 18181, forwarded by ADB.

Use the existing Python environment, running FastAPI and prepared board. From the checkout root:

```sh
/path/to/existing/python hardware/live_ui/dashboard_server.py
```

Do not start a second screen server on the same port. The current running copy on Kim's Mac is in the chat's `outputs/asr-test/board-microphone/` directory; the repository contains a portable source copy. Board paths/ADB serial are currently configured for Kim's device (`3220953353`).

Firmware deployment is separate: `hardware/deploy_board.sh` runs **on the board** and compiles before touching the MCU. The deployed firmware has already been flashed and image-verified; teammates do not need to flash it to work on Save/Review.

## Screen state and Save payload

`GET /api/state` on the screen server returns:

- `event.translation`: the current real AI result, including the base translation fields and `answers`.
- `answers`: three answer cards, each `{kind, text}`. Kinds are `translation`, `literal`, `explanation`.
- `selected`: zero-based Knob/card selection.
- `stage`: idle / recording / transcribing / thinking / ready / speaking / error.

In `dashboard.html`, `refresh()` reads this state. Keep a reference to the latest state when wiring Save; UI selection is `state.selected`, and the chosen card is `state.answers[state.selected]`.

The existing `POST /translations` accepts **only the seven base fields**, not `answers`, the selected index, microphone telemetry or stage:

```javascript
const result = state.event.translation;
const payload = {
  elapsed_ms: result.elapsed_ms,
  source_language: result.source_language,
  target_language: result.target_language,
  source: result.source,
  translation_confidence: result.translation_confidence,
  translation: result.translation,
  alternatives: result.alternatives
};
```

This saves the base natural translation. Saving all three cards, or retaining which kind/index was selected, requires a schema/store extension; that metadata is not persisted by today's API. Do not silently relabel a contextual explanation as a natural translation.

## Save and Review endpoints

- `POST http://<USB_MAC_WIFI_IP>:8000/translations` with the seven-field JSON → **201**, result plus `id` and `created_at`.
- `GET http://<USB_MAC_WIFI_IP>:8000/translations?limit=50&offset=0` → **200**, array ordered newest first.
- `POST /interpret/button` takes the same transcript/context/language request as `/interpret`; it adds `answers` to the returned base result.

The screen's existing `/api/*` routes are on port 8010, while storage routes are on 8000. This is a different browser origin, and this backend currently has no CORS middleware. The simplest integration is to add `/api/save` and `/api/translations` proxy routes to `dashboard_server.py`, then call them with the existing same-origin `action()`/`fetch()` pattern. **Those proxy routes and Save/Review screen controls are not implemented yet.** Alternatively, explicitly configure backend CORS for the chosen UI origin.

## Physical interaction

- First short click: start capture; first analysis after 5 seconds.
- With results: rotate to select the answer; short click runs Mac TTS.
- Hold >=800 ms while recording: request a fresh analysis.
- Matrix: blinking recording block, ASR/LLM scan, answer number 1–3, pulsing number during TTS.
- Stop recording using the screen's Stop button. Models remain loaded.

The base Knob/matrix pipeline has been tested with real device input. Repeated clicks now interrupt older Mac TTS and play the latest selected answer. ASR review candidates are exposed separately from the three LLM answer cards; the Knob keeps selecting those LLM answers.

## Real-board storage verification

`git pull --ff-only` advanced main to `9bc464a` before local integration. With `backend/examples/grounded-request.json`, the actual board model returned HTTP 200 and `translation: "당신은 징계당했습니다."`. That unmodified response was posted to `/translations` (201, id 3), then read back (200); every AI field matched exactly. The wording is model output, not a corrected reference translation.

Validation: 15 backend tests and the hardware RPC argument regression test passed; actual MCU firmware compile/flash verification, rotation/click counters, matrix-frame changes and TTS process completion were checked. Browser visual automation was not performed.

## ASR review extension

`event.asr_confidence` remains null: no calibrated transcript-correctness score is available. `event.asr_quality` contains decoder heuristics and review reasons. On ambiguous speech, `event.asr_alternatives` can contain one actual alternate decoder path. This is not a beam-search N-best list or an LLM rewrite, and the alternate can still be wrong. Music/noise captions are not treated as spoken translation requests.

The screen shows ASR candidates below the transcript. `POST /api/transcript` on port 8010 with `{ "index": 0 }` selects the original; index 1 selects the first actual alternative and calls the real board LLM again. It updates `event.translation`, so the same seven-field Save mapping still applies. `event.asr_primary_transcript` preserves the original, and `event.asr_selected_index` records the local selection. These ASR fields are not persisted by the current `/translations` schema.

ASR scoring lives in `hardware/live_ui/asr_uncertainty.py`; actual alternate decoding is in `ASR._decode()` / `ASR.transcribe()` in `live_board_audio.py`. Thresholds are uncalibrated heuristics. A manual request is processed even when the recognized text matches the previous request.
