"""Reliable access to the single shared GenieX model endpoint."""
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


RETRYABLE_STATUS = {502, 503, 504}


def open_model_request(request_factory, *, timeout=180, attempts=2, opener=urlopen):
    """Open a model request, retrying transient upstream gateway failures."""
    last_error = None
    for attempt in range(attempts):
        try:
            return opener(request_factory(), timeout=timeout)
        except HTTPError as error:
            last_error = error
            if error.code not in RETRYABLE_STATUS or attempt + 1 >= attempts:
                raise
            error.close()
            time.sleep(0.25 * (attempt + 1))
    raise last_error


def model_endpoint_ready(endpoint, model):
    """Return whether the endpoint advertises the model used by this app."""
    request = Request(endpoint.rstrip("/") + "/models")
    with urlopen(request, timeout=3) as response:
        body = response.read()
    import json
    models = json.loads(body).get("data", [])
    return any(item.get("id") == model for item in models if isinstance(item, dict))
