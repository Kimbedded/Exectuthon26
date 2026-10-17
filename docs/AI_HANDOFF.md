# IDK Button AI ↔ FastAPI handoff

AI integration code was pushed to `main` in commit
[`a32b0d95578c0f810be18d0706ebe9e163888cb6`](https://github.com/Kimbedded/Exectuthon26/commit/a32b0d95578c0f810be18d0706ebe9e163888cb6).
The FastAPI `/interpret` route now calls the real model instead of echoing its input.

## 1. Where the AI runs

```text
Mac microphone / transcript
  → Mac FastAPI POST /interpret
  → Mac 127.0.0.1:18181 (ADB-forwarded)
  → USB → VENTUNO Q Linux/Qualcomm side
  → Qwen3.5-2B Q4_0 / GenieX / NPU
```

The Mac runs the API/client and microphone capture. LLM inference runs on the board's NPU,
not on the Mac or the Modulino Knob microcontroller. When audio is used, Whisper tiny
ExecuTorch/QNN HTP FP16 ASR also runs on the board. `/interpret` accepts text, so this endpoint
does not itself perform recording or ASR.

## 2. Working setup and commands

### Reproduce from this repository

On the Mac connected by USB, with Python 3.12+, ADB and the already prepared board model:

```sh
git clone https://github.com/Kimbedded/Exectuthon26.git
cd Exectuthon26
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
adb -s 3220953353 forward tcp:18181 tcp:18181
cd backend
IDK_MODEL_ENDPOINT=http://127.0.0.1:18181/v1 ../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

For an existing clone, use `git pull --ff-only` instead of cloning again.
The board model and server must already be installed. This Git change deploys the backend client;
it does not distribute the GGUF, ASR .pte, Qualcomm SDK or QNN runtime.

The tested server startup command **on the board**, if it is stopped, is:

```sh
/home/arduino/.local/bin/geniex serve --host 127.0.0.1:18181 --keepalive 86400 --compute npu --skip-update --log info
```

The cached model is `unsloth/Qwen3.5-2B-GGUF:Q4_0`. Do not start another listener if that server is
already running. Server startup and ADB forwarding are not installed as automatic reboot services.

### Exact checkout verified on Kim's Mac

Working repository:
`/Users/kims/Documents/Codex/2026-10-17/referenced-chatgpt-conversation-this-is-an/work/Exectuthon26`

Python environment with the repository requirements installed:
`/Users/kims/Documents/Codex/2026-10-17/referenced-chatgpt-conversation-this-is-an/work/backend-test-venv`

The FastAPI process was started from that checkout's `backend/` directory with this environment,
`--host 127.0.0.1 --port 8000 --workers 1`, and the model base URL above. It was left running for
local use. This temporary process is not a managed production deployment.

### Call FastAPI

With the server running, from the backend directory:

```sh
curl -fsS http://127.0.0.1:8000/interpret -H 'Content-Type: application/json' --data-binary @examples/grounded-request.json
```

### Call the Python client directly

From the backend directory, in the same environment:

```python
from idk_client import interpret

result = interpret(
    transcript="You're grounded.",
    context="A parent is punishing a teenager who came home after midnight. "
            "The teenager is not allowed to go out this weekend.",
    target_language="Korean",
)
```

`backend/idk_client.py:interpret()` normalizes common language names and calls the existing
`backend/translate_sentence.py:translate()` implementation. The lower-level function returns
metrics/validation plus the app JSON under `result`; the adapter returns the app JSON directly.
The model client itself uses only Python's standard library. The FastAPI server dependencies
are in the existing requirements.txt.

Use one backend worker: a process-local lock serializes requests to the shared board model.
It does not coordinate independent clients or multiple backend processes.

## 3. Complete actual input/output

Request:

```json
{
  "transcript": "You're grounded.",
  "context": "A parent is punishing a teenager who came home after midnight. The teenager is not allowed to go out this weekend.",
  "target_language": "Korean"
}
```

Actual response through **FastAPI → ADB → board model**, HTTP 200, measured 1.566 seconds:

```json
{
  "elapsed_ms": null,
  "source_language": "en",
  "target_language": "ko",
  "source": "You're grounded.",
  "translation_confidence": null,
  "translation": "당신은 징계당했습니다.",
  "alternatives": []
}
```

This is the unedited model translation. It conveys punishment but misses the specific prohibition
on going out; the earlier `너는 외출 금지야.` example was an ideal/reference translation.
Format validity is not semantic accuracy. Confidence remains null until calibrated; elapsed_ms
is null when the caller does not supply an actual conversation duration.

A second live HTTP test used Korean source, English target and elapsed_ms=32000. It returned HTTP
200 in 1.643 seconds, selected only the last source sentence, and preserved the supplied languages
and elapsed time. Its translation was `Let's try putting our recent chat into this JSON format.`
These are single-call measurements, not a new multi-run benchmark.

## 4. APIs, request format and same-Wi-Fi access

| Service | Address | Scope verified here |
|---|---|---|
| FastAPI health | GET http://127.0.0.1:8000/health | USB-connected Mac |
| App translation | POST http://127.0.0.1:8000/interpret | USB-connected Mac |
| FastAPI schema/UI | GET http://127.0.0.1:8000/openapi.json and /docs | Local routes provided by FastAPI |
| Raw model API | POST http://127.0.0.1:18181/v1/chat/completions | Board loopback; USB Mac via ADB |
| Model inventory | GET http://127.0.0.1:18181/v1/models | Verified through ADB |

No Authorization header was required for the tested local model calls.
`/interpret` uses the three-field request above, with optional source_language and elapsed_ms.
The raw model API instead uses an OpenAI-style request:

```json
{
  "model": "unsloth/Qwen3.5-2B-GGUF:Q4_0",
  "messages": [
    {"role": "system", "content": "Your translation instructions and output schema"},
    {"role": "user", "content": "The source sentence and previous context"}
  ],
  "enable_think": false,
  "temperature": 0,
  "top_k": 1,
  "max_tokens": 256,
  "stream": false
}
```

The placeholder contents above illustrate the raw request shape. The exact working translation
instructions and user payload construction are in translate_sentence.py. That client uses
`stream=true`, assembles SSE delta.content chunks and validates the generated JSON. A direct
non-streaming raw request was also verified before integration. For non-streaming, model content
is a JSON string at `choices[0].message.content`, not the seven-field app response. The adapter
adds the source/language/time fields and null confidence.

**Another Mac cannot reach either current listener just by joining the same Wi-Fi.** Both FastAPI
and the ADB-forwarded model port are bound to 127.0.0.1 on the USB Mac. On Satyam's Mac, localhost
refers to Satyam's Mac, not the USB-connected one.

For a later LAN setup, run FastAPI on the USB Mac with `--host 0.0.0.0` and call
`http://<USB_MAC_LAN_IP>:8000/interpret` from Satyam's Mac. The actual LAN IP, incoming permissions
and Wi-Fi client reachability still require checking. This has not been enabled or tested from
another Mac. If FastAPI must run on Satyam's Mac, provide a reachable model URL/tunnel instead;
`IDK_MODEL_ENDPOINT=http://127.0.0.1:18181/v1` only works where the forward/tunnel exists.

## 5. Field mapping and custom instructions

| FastAPI field | Model mapping |
|---|---|
| transcript | Last sentence → SOURCE; earlier sentences → CONTEXT.preceding_sentences |
| context | CONTEXT.previous_turns |
| target_language | Normalize supported names (Korean→ko, Spanish→es) → TARGET_LANGUAGE |
| source_language, optional | Normalize name/code → SOURCE_LANGUAGE; default en |
| elapsed_ms, optional | Caller-supplied elapsed conversation time → response only; default null |

The original request default target **Spanish** is intentionally preserved for compatibility.
Send Korean/ko explicitly for Korean. The adapter maps a small list of full language names;
otherwise send a code such as ko/en/es. ASR language is not automatically discovered by FastAPI:
pass the ASR language using source_language for multilingual audio.

The last sentence is selected by punctuation with some abbreviation handling. This is not VAD,
word timing or speaker diarization. An unfinished final fragment is preserved and marked in
internal diagnostics. It does not automatically expand the previous context window or store chat
history; send context on each request.

The raw model API accepts custom system instructions. The current translate() helper has a fixed
SYSTEM constant, not a per-request instructions argument. Changing the prompt requires maintaining
the expected translation/alternatives output shape. The lower-level model may still ignore an
instruction; schema checks do not establish semantic correctness.

`backend/prompts.py` and the old `InterpretationResult` schema describe an earlier
expression/meaning/example/clarification flow. They are retained but are **not used by the current
/interpret route**. Current output validation uses TranslationResult. `/expressions` storage and
its required expression/meaning/example fields are unchanged and are a separate API.

## Verification and remaining details

Completed before the integration commit was pushed:

- Installed the repository's pinned requirements into an isolated Mac Python environment.
- Ran 8 tests: request/metadata mapping, existing default compatibility, validation, model/network
  errors, SSE assembly/context, language normalization and SQLite expression-storage regression.
- Started real FastAPI and called /health and /interpret against the live board model.
- Verified English→Korean and Korean→English with last-sentence selection and elapsed-time metadata.

Failures return 422 for invalid inputs, 502 for model/network/format failures, and 504 for timeouts.
No probability-calibrated confidence or physical button-event wiring is implemented in this backend
change. The physical IDK source must provide transcript/context and optionally language/elapsed_ms.
No GGUF/.pte/SDK/audio recordings were committed. Translation quality remains the measured limitation;
this Git deployment connects the existing AI rather than improving its weights.

Remaining deployment work is the teammate's actual network path, agreed conversation/session source,
and any desired managed service/autostart. The local backend currently works while its temporary
Mac process, board model server and ADB connection remain alive.
