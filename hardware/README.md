See [Screen/Button handoff](../docs/SCREEN_BUTTON_HANDOFF.md) for the file map and Save/Review integration points.

# IDK Button hardware integration

Device: VENTUNO Q, ADB serial `3220953353`. Knob: Qwiic/MCU I2C, address `0x3A` detected. Display: **VENTUNO Q built-in 8×13 LED matrix**, no external Pixels module required.

## Use

Open http://127.0.0.1:8010 on the USB-connected Mac. The server prepares Qwen and Whisper/QNN before enabling input. Models remain loaded across recording start/stop.

- Short click with no result: start recording; the first analysis occurs after 5 seconds. A subsequent short click with no result requests analysis.
- Rotate with a result: choose 1, 2 or 3. The MCU changes the matrix immediately, and the dashboard follows.
- Short click with a result: speak the selected answer through **MacBook TTS**.
- Hold at least 800 ms during recording: analyze the current rolling context again.
- Hold when stopped: start recording.
- Stop recording using the UI's Stop button. Closing the page does not stop capture.

The first successful response is held for selection; the next analysis is explicit. Audio capture continues into a bounded 30-second ring while selecting a result. ASR and LLM inference remain sequential. The model is not reloaded per click.

Three answers are generated in **one Qwen inference**: natural translation, literal translation, brief contextual explanation. These are three views of the same context, not fabricated confidence levels or alternate meanings. The small model can repeat wording or make semantic errors. Generated text is never replaced with an ideal translation.

## Matrix state table

| State | Display |
|---|---|
| Idle | Dim center pixel |
| Recording | Blinking central block |
| ASR | Scanning column |
| LLM | Faster scan plus bottom line |
| Ready | Selected answer number 1–3 and position dots |
| Speaking | Pulsing selected number |
| Error | Blinking X |

A corner pixel indicates a physically pressed button. The MCU polls the knob independently of LLM execution and maintains cumulative rotation/click/hold counters so host polling does not lose complete button events.

## Architecture

Mac dashboard controls a persistent board audio process through ADB stdin. That process uses Whisper tiny `.pte` / ExecuTorch QNN for transcription, then calls the Mac FastAPI via ADB reverse TCP 8000. FastAPI calls the existing board Qwen3.5-2B / GenieX NPU server through ADB-forwarded TCP 18181.

A separate host thread polls `arduino-router-cli idk.read` through ADB and calls `idk.set` on state transitions. The MCU drives the matrix. Recording/ASR/LLM/ready phase events come from the actual audio worker.

## Firmware

Source: `IdkButton/IdkButton.ino`. Board target verified as `arduino:zephyr:ventunoq`, installed core 1.0.0. Build and flash were actually performed, with OpenOCD image verification. The prior running demo source and compiled image are preserved in `backup/`.

Board working paths:

- `/home/arduino/idk-button/IdkButton/IdkButton.ino`
- `/home/arduino/idk-button/build/IdkButton.ino.elf-zsk.bin`
- `/home/arduino/idk-button/flash.cfg`

Firmware RPC:

- `idk.read`: JSON string with firmware version, knob health, position, cumulative rotations/clicks/holds, selected zero-based index, state, frame counter and frame hash.
- `idk.set <state> <selected> <count>`: sets display; selected `-1` preserves the physical selection. Returns a JSON **string**, avoiding an installed router CLI integer-result printing bug.

Counter checks prove sensor input and rendered-frame changes. They do not replace human visual confirmation of LEDs or audible confirmation of TTS.

## FastAPI

Existing `/interpret`, `/interpret/enriched`, `/translations` and `/expressions` remain available. Added `POST /interpret/button` accepts the same transcript/context/language request and returns the base translation JSON plus:

```json
"answers": [
  {"kind": "translation", "text": "model-generated natural translation"},
  {"kind": "literal", "text": "model-generated literal translation"},
  {"kind": "explanation", "text": "model-generated contextual explanation"}
]
```

The ordinary `/interpret` response is the seven-field storage contract accepted directly by `/translations`. The button response has the extra `answers` field; store only the base fields with the current `/translations` API. The live UI does not automatically store every rolling microphone result.

## Runtime

The running dashboard uses files in `outputs/asr-test/board-microphone/`. Reviewable source copies were added to the local Git checkout under `hardware/`. Use the existing Python environment and prepared board assets; this repository does not contain the model weights, Qualcomm runtime, or ASR bundle.

Only this project's FastAPI/dashboard were restarted; the existing GenieX model server was kept running. No model size change was made.

Sources used to verify the Bridge/matrix approach: [Arduino's VENTUNO Q local assistant guide](https://docs.arduino.cc/tutorials/ventuno-q/local-ai-assistant), installed Arduino RouterBridge/LED Matrix/Modulino headers, and the existing working board demo.

## Repeated playback and uncertain ASR

Repeated short clicks during TTS interrupt the previous utterance and play the latest selected answer. Older player completion cannot reset the new player's state.

Uncertain speech can show an original and an actual alternate ASR decoding beneath the transcript. Choose a candidate on the screen to retranslate it; the physical Knob still selects the three LLM answers. No correctness percentage is fabricated. Native Mac playback replacement and real-board ASR/candidate-to-LLM tests were executed. The alternate is not guaranteed to correct the original recognition.
