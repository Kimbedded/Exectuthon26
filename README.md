# IDK Button — Executhon26

FastAPI backend connected to Qwen inference on the USB-attached VENTUNO Q's Qualcomm NPU.

- [Backend setup and API](backend/README.md)
- [AI/FastAPI teammate handoff](docs/AI_HANDOFF.md)

The model is prepared separately on the board. No model weights, Qualcomm SDK or audio recordings
are distributed in this repository.

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
