"""Same-origin dictionary files and a fixed localhost FastAPI proxy."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

BACKEND = "http://127.0.0.1:8000"


def serve_dictionary(handler, root):
    """Return True only when this request belongs to the dictionary panel."""
    path = urlsplit(handler.path)
    assets = {
        "/dictionary.js": ("dictionary.js", "text/javascript; charset=utf-8"),
        "/dictionary.css": ("dictionary.css", "text/css; charset=utf-8"),
    }
    if path.path in assets:
        name, content_type = assets[path.path]
        handler.reply(200, (root / name).read_bytes(), content_type)
        return True
    if path.path not in {"/api/dictionary/search", "/api/dictionary/stats"}:
        return False
    if len(handler.path) > 2048:
        handler.reply(422, {"error": "Search request is too long."})
        return True
    target = BACKEND + path.path.removeprefix("/api")
    if path.path.endswith("/search"):
        try:
            values = parse_qs(path.query, keep_blank_values=True, max_num_fields=6)
            if any(len(items) != 1 for items in values.values()):
                raise ValueError("Use one search query.")
        except ValueError:
            handler.reply(422, {"error": "Invalid search query."})
            return True
        target += "?" + urlencode({
            "q": values.get("q", [""])[0],
            "limit": values.get("limit", ["5"])[0],
            "language": values.get("language", ["en"])[0],
        })
    try:
        with urlopen(target, timeout=10) as response:
            result = json.load(response)
        handler.reply(200, result)
    except HTTPError as error:
        if error.code == 422:
            handler.reply(422, {"error": "Enter a word or phrase of 1–100 characters."})
        elif error.code == 404:
            handler.reply(502, {"error": "Dictionary API is unavailable. Restart FastAPI after connecting the dictionary."})
        else:
            handler.reply(502, {"error": "Dictionary request failed. Try again."})
        error.close()
    except (URLError, TimeoutError, OSError, ValueError):
        handler.reply(502, {"error": "Could not reach the dictionary. Check that FastAPI is running on port 8000."})
    return True


def serve_dictionary_post(handler):
    if urlsplit(handler.path).path != "/api/dictionary/suggestions":
        return False
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        if not 0 < length <= 65536:
            raise ValueError("Invalid request size")
        body = handler.rfile.read(length)
        if not isinstance(json.loads(body), dict):
            raise ValueError("Expected a JSON object")
    except (ValueError, UnicodeError):
        handler.reply(400, {"error": "Could not read this translation result."})
        return True
    request = Request(BACKEND + "/dictionary/suggestions", data=body,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
        handler.reply(200, result)
    except HTTPError as error:
        handler.reply(422 if error.code == 422 else 502, {
            "error": "Word options are unavailable for this result. Check that the updated FastAPI is running."
        })
        error.close()
    except (URLError, TimeoutError, OSError, ValueError):
        handler.reply(502, {"error": "Could not load word options. Check that FastAPI is running on port 8000."})
    return True
