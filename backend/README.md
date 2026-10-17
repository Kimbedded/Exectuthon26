# IDK Button backend

`POST /interpret` calls the Qwen model on the connected VENTUNO Q through the GenieX HTTP API.
The Mac runs FastAPI and records audio; model inference stays on the board's Qualcomm NPU.

## Run on the Mac connected to the board

From this repository root, with Python 3.12+ and the board model already installed/running:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
adb -s 3220953353 forward tcp:18181 tcp:18181
cd backend
IDK_MODEL_ENDPOINT=http://127.0.0.1:18181/v1 ../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

If the board model server is stopped, run on the board in a persistent terminal:

```sh
/home/arduino/.local/bin/geniex serve --host 127.0.0.1:18181 --keepalive 86400 --compute npu --skip-update --log info
```

Model `unsloth/Qwen3.5-2B-GGUF:Q4_0` must already be cached there. These client files require only
Python's standard library; FastAPI's dependencies are in requirements.txt. ADB authorization and
port forwarding must be re-established after disconnect/reboot as needed.

## Request and response

From the backend directory, with FastAPI running:

```sh
curl -fsS http://127.0.0.1:8000/interpret -H 'Content-Type: application/json' --data-binary @examples/grounded-request.json
```

Existing fields remain `transcript`, `context`, `target_language`. Optional `source_language`
(default `en`) and `elapsed_ms` (default null) are also accepted. The original default target
`Spanish` is preserved; send `ko` or `Korean` explicitly for Korean. Common language names are
normalized by idk_client.py; other languages should use their language code.

The response uses the agreed seven fields: elapsed_ms, source_language, target_language, source,
translation_confidence, translation, alternatives. `translation_confidence` remains null until
calibrated. It is not a self-reported model probability. elapsed_ms is an actual caller-supplied
conversation duration, never inference time. See examples/ for the real model result, which is
not necessarily semantically perfect.

`translate_sentence.py` selects the last sentence as SOURCE. Earlier transcript sentences and the
supplied context are passed to the model. Previous context must be sent with each request; it is
not persisted automatically. The current SYSTEM prompt is fixed in that file. The raw GenieX
endpoint supports other system instructions, but our response parser requires this contract.

The old InterpretationResult schema and prompts.py remain available for the previous expression
explanation flow. They are not used by /interpret, and the /expressions persistence API is unchanged.
Model/network/format failures return 502, timeouts 504, invalid caller inputs 422.

Use one FastAPI worker: a process-local lock serializes access to the shared board model session.
This does not coordinate other independent clients or multiple backend processes.

## Network access

The model API is `POST http://127.0.0.1:18181/v1/chat/completions` on the board, mirrored on the USB
Mac through ADB. Both listeners are loopback-only. Another Mac on the same Wi-Fi cannot call them
directly. If desired, run FastAPI on the USB Mac with `--host 0.0.0.0` and have the teammate call
`http://<USB_MAC_LAN_IP>:8000/interpret`; LAN IP, firewall and client reachability need to be checked.
This LAN configuration is not automatically enabled by the setup above.

## Tests

From the repository root:

```sh
.venv/bin/python -m unittest discover -s backend/tests -v
```

These tests use mocked model responses, exercise input/context mapping, SSE assembly, error codes
and SQLite regression behavior. Live board verification is described in the deployment handoff.
