"""CVF cache/retry component ported from A1 with explicit corpus paths.

CVF and OpenAlex snapshots retain original response bytes and UTC observation times.
"""
from __future__ import annotations

import gzip
import json
import time
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from src.clean.text import identifier, sha256
from .common import REPO_ROOT, atomic_json, json_bytes, now_utc, publish, within


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward an Authorization header to another destination.
        raise HTTPError(req.full_url, code, "Redirect refused", headers, fp)


def urlopen(request, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


def retry_after(value):
    if not value:
        return 0
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError):
            return 0


class SourceFailure(RuntimeError):
    def __init__(self, reason, retry_at=None):
        super().__init__(reason)
        self.retry_at = retry_at


def api_key(root=None):
    """Nonempty environment wins; otherwise read only the root .env key.

    Supports plain/quoted single-line values and comments, without expanding
    variables, executing shell expressions or modifying os.environ.
    """
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    path = (REPO_ROOT if root is None else Path(root).resolve()) / ".env"
    if not key and path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            name, sep, value = line.partition("=")
            if sep and name.strip() == "OPENALEX_API_KEY":
                value = value.strip()
                if value.startswith(('"', "'")):
                    end = value.find(value[0], 1)
                    if end < 0 or (value[end+1:].strip() and not value[end+1:].lstrip().startswith('#')):
                        raise ValueError("Invalid OPENALEX_API_KEY assignment syntax")
                    key = value[1:end].strip()
                else:
                    import re
                    key = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    if any(ch.isspace() for ch in key):
        raise ValueError("Invalid OPENALEX_API_KEY format")
    return key


class OpenAlexCache:
    def __init__(self, root, config, offline=False):
        self.root, self.config, self.offline = root.resolve(), config, offline
        self.directory = within(root, config["raw_dir"] + "/openalex")
        self.network_requests = 0
        self.last_request = 0
        self.key = "" if offline else api_key(self.root)

    def get(self, url):
        from urllib.parse import parse_qs
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "api.openalex.org" or any(k.lower() in {"api_key", "key", "token"} for k in parse_qs(parts.query)):
            raise ValueError("Use a credential-free official OpenAlex URL")
        path = self.directory / (sha256(url.encode()) + ".json")
        if path.exists():
            meta = json.loads(path.read_text(encoding="utf-8"))
            raw = within(self.root, meta["raw_path"])
            if meta["url"] != url or meta["http_status"] != 200 or not raw.is_relative_to(self.directory):
                raise ValueError("OpenAlex cache URL/status/path mismatch")
            body = gzip.decompress(raw.read_bytes())
            if sha256(body) != meta["content_sha256"]:
                raise ValueError("Corrupt OpenAlex cache; refusing refetch")
            return json.loads(body), meta
        if self.offline:
            raise SourceFailure("OpenAlex offline cache miss")
        gate = self.directory / "rate_limit.json"
        if gate.exists():
            until = json.loads(gate.read_text())["retry_at"]
            if time.time() < until:
                raise SourceFailure("OpenAlex quota/backoff checkpoint is still active", until)
        for attempt in range(self.config["retries"] + 1):
            time.sleep(max(0, self.config["openalex_delay_seconds"] - (time.monotonic() - self.last_request)))
            headers = {"User-Agent": "AcademicCollector/2 (metadata research)", "Accept": "application/json"}
            if self.key:
                headers["Authorization"] = "Bearer " + self.key
            self.last_request = time.monotonic()
            self.network_requests += 1
            try:
                with urlopen(Request(url, headers=headers), timeout=self.config["timeout_seconds"]) as response:
                    if response.status != 200 or response.geturl() != url:
                        raise SourceFailure("OpenAlex unexpected redirect/status")
                    body = response.read()
                    if self.key and self.key.encode() in body:
                        raise SourceFailure("Response echoed credentials; snapshot refused")
                    value = json.loads(body)
                    meta = {"url": url, "fetched_at": now_utc(), "http_status": 200,
                            "content_sha256": sha256(body), "content_type": response.headers.get("Content-Type", "application/json"),
                            "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
                break
            except HTTPError as exc:
                wait = max(2 ** attempt, retry_after(exc.headers.get("Retry-After")))
                if exc.code in {401, 403}:
                    raise SourceFailure(f"OpenAlex HTTP {exc.code}: authentication/access unavailable") from None
                if exc.code == 429:
                    # An unspecified 429 may be daily exhaustion. Preserve a
                    # conservative gate instead of repeatedly probing quota.
                    if not exc.headers.get("Retry-After"):
                        wait = max(wait, 86400)
                    until = time.time() + wait
                    atomic_json(gate, {"retry_at": until, "http_status": 429})
                    if wait > self.config["max_retry_wait_seconds"] or attempt == self.config["retries"]:
                        raise SourceFailure("OpenAlex rate/quota limit; checkpoint saved", until) from None
                elif exc.code < 500 or attempt == self.config["retries"]:
                    raise SourceFailure(f"OpenAlex HTTP {exc.code}; request unfinished") from None
                if wait > self.config["max_retry_wait_seconds"]:
                    atomic_json(gate, {"retry_at": time.time() + wait, "http_status": exc.code})
                    raise SourceFailure("OpenAlex long Retry-After; checkpoint saved", time.time() + wait) from None
                time.sleep(wait)
            except (URLError, TimeoutError, ConnectionError):
                if attempt == self.config["retries"]:
                    raise SourceFailure("OpenAlex network error after retries") from None
                time.sleep(2 ** attempt)
        raw = self.directory / (meta["content_sha256"] + ".json.gz")
        meta["raw_path"] = raw.relative_to(self.root).as_posix()
        publish({raw: gzip.compress(body, mtime=0), path: json_bytes(meta)})
        return value, meta


def openalex_source(meta, paper_id, kind):
    return {"schema_version": "2.0.0", "source_record_id": identifier("source:openalex", meta["url"], meta["content_sha256"]),
            "paper_id": paper_id, "source": "OpenAlex", "source_kind": kind,
            "source_id": meta["url"], "source_version": None, **meta}


class HTTPBlocked(SourceFailure):
    """Stop immediately on CVF 403/429."""


class HTTPCache:
    def __init__(self, root: Path, raw_dir: str, offline: bool = True,
                 delay: float = 1.0, retries: int = 2, timeout: float = 30, max_retry_wait: float = 30):
        self.root = root.resolve()
        self.raw_dir, self.offline = raw_dir, offline
        self.cache_dir = within(root, raw_dir + "/http")
        if not self.cache_dir.is_relative_to(within(root, "data/raw")):
            raise ValueError("Cache must be inside data/raw")
        if delay < 0 or retries < 0:
            raise ValueError("Delay/retries must be nonnegative")
        self.delay, self.retries, self.timeout = delay, retries, timeout
        self.max_retry_wait = max_retry_wait
        self.last_request = 0.0
        self.network_requests = 0

    def get(self, url: str) -> tuple[bytes, dict]:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "openaccess.thecvf.com":
            raise ValueError("Collector only fetches official HTTPS CVF URLs")
        meta_path = self.cache_dir / (sha256(url.encode()) + ".json")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["url"] != url or meta["http_status"] != 200:
                raise ValueError("Cache URL/status mismatch")
            raw_path = within(self.root, meta["raw_path"])
            if not raw_path.is_relative_to(self.cache_dir):
                raise ValueError("Cache body must stay inside its corpus cache")
            body = gzip.decompress(raw_path.read_bytes())
            if sha256(body) != meta["content_sha256"]:
                raise ValueError(f"Corrupt cache for {url}; do not silently refetch")
            return body, meta
        if self.offline:
            raise FileNotFoundError(f"Offline cache miss: {url}; run src.collect.bootstrap first")
        gate = self.cache_dir / "cvf_rate_limit.json"
        if gate.exists():
            until = json.loads(gate.read_text())["retry_at"]
            if time.time() < until:
                raise HTTPBlocked("CVF Retry-After checkpoint is still active", until)
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            request = Request(url, headers={"User-Agent": "AcademicPilotCollector/1.0 (student metadata project)"})
            self.last_request = time.monotonic()
            self.network_requests += 1
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    if response.geturl() != url or response.status != 200:
                        raise ValueError(f"Unexpected redirect/status for {url}")
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "")
                    if "html" not in content_type.lower():
                        raise ValueError(f"Expected HTML for {url}")
                    meta = {"url": url, "fetched_at": now_utc(), "http_status": 200,
                            "content_sha256": sha256(body), "content_type": content_type,
                            "etag": response.headers.get("ETag"),
                            "last_modified": response.headers.get("Last-Modified")}
                break
            except HTTPError as exc:
                if exc.code in {403, 429}:
                    until = None
                    if exc.code == 429:
                        until = time.time() + (retry_after(exc.headers.get("Retry-After")) or 86400)
                        atomic_json(gate, {"retry_at": until, "http_status": 429})
                    raise HTTPBlocked(f"CVF returned {exc.code}; stopped without retrying", until) from None
                if exc.code < 500 or attempt == self.retries:
                    raise
                wait = max(2 ** attempt, retry_after(exc.headers.get("Retry-After")))
                if wait > self.max_retry_wait:
                    until = time.time() + wait
                    atomic_json(gate, {"retry_at": until, "http_status": exc.code})
                    raise HTTPBlocked("CVF long Retry-After; checkpoint saved", until) from None
                time.sleep(wait)
            except (URLError, TimeoutError) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"Network failed for {url}") from exc
                time.sleep(2 ** attempt)
        raw_path = self.cache_dir / (meta["content_sha256"] + ".html.gz")
        meta["raw_path"] = raw_path.relative_to(self.root).as_posix()
        publish({raw_path: gzip.compress(body, mtime=0), meta_path: json_bytes(meta)})
        return body, meta


def source_record(meta: dict, paper_id: str | None, source_kind: str) -> dict:
    return {"schema_version": "2.0.0",
            "source_record_id": identifier("source:cvf", meta["url"], meta["content_sha256"]),
            "paper_id": paper_id, "source": "CVF", "source_kind": source_kind,
            "source_id": meta["url"], "source_version": None, **meta}
