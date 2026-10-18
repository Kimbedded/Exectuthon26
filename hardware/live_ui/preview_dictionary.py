"""Preview dictionary and saved translations on a Mac without an Arduino."""
from http.server import ThreadingHTTPServer

import dashboard_server as dashboard


if __name__ == "__main__":
    # A clearly labeled static result lets a Mac without the board test the UI.
    # This is not recorded speech or new AI output, and cannot be saved here.
    dashboard.STATE.update(
        status="preview", stage="Example preview", model_status="disconnected",
        preview_mode=True, answers=[],
        event={
            "transcript": "This electrical circuit has intermittent voltage. Check the ground.",
            "translation": {
                "source": "Check the ground.", "translation": "접지를 확인하세요.",
                "source_language": "en", "target_language": "ko",
            },
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 8010), dashboard.Handler)
    print("Dictionary preview: http://127.0.0.1:8010", flush=True)
    print("Keep FastAPI running on port 8000. Press Control+C to stop this preview.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
