"""One credential-safe OpenAlex connectivity check, without cache or retries."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .cache import api_key, urlopen

URL = "https://api.openalex.org/works?per_page=1"


def check(root=None):
    result = {"key_loaded": False, "success": False, "http_status": None, "error_category": None}
    try:
        key = api_key(root)
    except (OSError, ValueError):
        return {**result, "error_category": "configuration"}
    result["key_loaded"] = bool(key)
    if not key:
        return {**result, "error_category": "missing_key"}
    try:
        request = Request(URL, headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
        with urlopen(request, timeout=30) as response:
            result["http_status"] = response.status
            result["success"] = response.status == 200 and response.geturl() == URL
            if not result["success"]:
                result["error_category"] = "unexpected_response"
            # Do not print or save response bodies, request/response headers,
            # credentials or exception strings. No retry and no redirect.
    except HTTPError as exc:
        result["http_status"] = exc.code
        result["error_category"] = ("authentication" if exc.code in {401, 403} else
                                    "rate_limit" if exc.code == 429 else "http")
    except (URLError, TimeoutError, ConnectionError, OSError):
        result["error_category"] = "network"
    except ValueError:
        result["error_category"] = "configuration"
    return result


def main():
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["success"] else 2)


if __name__ == "__main__":
    main()
