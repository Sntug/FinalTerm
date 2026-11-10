"""Bounded supplemental lookups using A2's transport, backoff and immutable cache policy."""
import gzip
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request

from src.collect.cache import urlopen, retry_after, SourceFailure
from src.collect.common import within, publish, json_bytes, now_utc, atomic_json
from src.clean.text import sha256, identifier
from src.collect.cvf import CVFHTML
from src.clean.normalize import arxiv, doi, clean_text


def arxiv_metadata(body):
    parsed = CVFHTML(body.decode("utf-8-sig"))
    meta = parsed.meta
    one = lambda key: (meta.get(key) or [None])[0]
    aid = one("citation_arxiv_id")
    def display_name(value):
        value = clean_text(value)
        if "," in value:
            family, given = value.split(",", 1)
            value = clean_text(given + " " + family)
        return value
    return dict(title=clean_text(one("citation_title")), authors=[display_name(a) for a in meta.get("citation_author", [])],
                authors_raw=meta.get("citation_author", []),
                arxiv_id=arxiv("https://arxiv.org/abs/" + aid) if aid else None, declared_identifier=aid,
                version=aid if aid and re.search(r"v\d+$", aid) else None,
                doi=doi(one("citation_doi")), publication_date=one("citation_date"))


class SupplementalCache:
    def __init__(self, root, cfg, offline=True):
        self.root, self.cfg, self.offline = root, cfg, offline
        self.directory = within(root, cfg["raw_dir"])
        if not self.directory.is_relative_to(within(root, "data/raw")):
            raise ValueError("Supplemental cache must be under data/raw")
        self.network_requests, self.last_request = 0, 0

    def fetch(self, request):
        source, url, pid = request["source"], request["url"], request["paper_id"]
        parts = urlsplit(url)
        allowed = source == "arXiv" and parts.netloc == "arxiv.org" and arxiv(url) or source == "Crossref" and parts.netloc == "api.crossref.org" and parts.path.startswith("/works/")
        if parts.scheme != "https" or not allowed or parts.query or parts.fragment or parts.username:
            raise ValueError("Unsupported supplemental URL")
        key = identifier("lookup", pid, source, url).split(":", 1)[1]
        receipt = self.directory / (key + ".json")
        if receipt.exists():
            result = json.loads(receipt.read_text(encoding="utf-8"))
            if any(result[k] != request[k] for k in ("paper_id", "source", "url")):
                raise ValueError("Lookup receipt binding mismatch")
            if result["status"] == "fetched":
                self.body(result["source_record"])
            return result
        if self.offline:
            return {**request, "status": "unverified", "reason": "offline_cache_miss", "network_requests": 0, "source_record": None}
        gate = self.directory / (source.lower() + "_rate_limit.json")
        if gate.exists() and json.loads(gate.read_text())["retry_at"] > time.time():
            return {**request, "status": "unavailable", "reason": "active_source_backoff", "network_requests": 0, "source_record": None}
        start_count, reason, meta, body = self.network_requests, "", None, None
        for attempt in range(self.cfg["retries"] + 1):
            time.sleep(max(0, self.cfg["delay_seconds"] - (time.monotonic() - self.last_request)))
            self.network_requests += 1
            self.last_request = time.monotonic()
            try:
                with urlopen(Request(url, headers={"User-Agent": "AcademicCollector/2 A5 selected metadata verification", "Accept": "application/json" if source == "Crossref" else "text/html"}), timeout=self.cfg["timeout_seconds"]) as response:
                    if response.status != 200 or response.geturl() != url:
                        raise SourceFailure("unexpected_redirect_or_status")
                    body = response.read()
                    if source == "Crossref":
                        value = json.loads(body)
                        if not isinstance(value.get("message"), dict):
                            raise ValueError("invalid_crossref_response")
                    elif not arxiv_metadata(body)["title"] or not arxiv_metadata(body)["arxiv_id"]:
                        raise ValueError("invalid_arxiv_metadata")
                    meta = dict(content_type=response.headers.get("Content-Type", "application/octet-stream"),
                                etag=response.headers.get("ETag"), last_modified=response.headers.get("Last-Modified"))
                break
            except HTTPError as exc:
                reason = f"HTTP_{exc.code}"
                wait = max(2 ** attempt, retry_after(exc.headers.get("Retry-After")))
                if exc.code == 429:
                    wait = max(wait, 86400 if not exc.headers.get("Retry-After") else 0)
                    atomic_json(gate, {"retry_at": time.time() + wait, "http_status": exc.code})
                if exc.code < 500 and exc.code != 429 or attempt == self.cfg["retries"] or wait > self.cfg["max_retry_wait_seconds"]:
                    break
                time.sleep(wait)
            except (URLError, TimeoutError, ConnectionError):
                reason = "network_unavailable"
                if attempt == self.cfg["retries"]:
                    break
                time.sleep(2 ** attempt)
            except (ValueError, SourceFailure):
                reason = "invalid_source_response"
                break
        record = None
        if meta is not None:
            digest = sha256(body)
            path = self.directory / (digest + ".raw.gz")
            observed_version = arxiv_metadata(body)["version"] if source == "arXiv" else None
            version = observed_version if observed_version and re.search(r"v\d+$", observed_version) else None
            record = dict(schema_version="2.0.0", source_record_id=identifier("source:" + source.lower(), url, digest),
                paper_id=pid, source=source, source_kind="preprint_metadata" if source == "arXiv" else "doi_metadata",
                source_id=url, source_version=version, url=url, fetched_at=now_utc(), http_status=200,
                content_sha256=digest, raw_path=path.relative_to(self.root).as_posix(), **meta)
            publish({path: gzip.compress(body, mtime=0)})
        result = {**request, "status": "fetched" if record else "unavailable", "reason": "" if record else reason,
                  "network_requests": self.network_requests - start_count, "source_record": record}
        publish({receipt: json_bytes(result)})
        return result

    def body(self, source):
        path = within(self.root, source["raw_path"])
        if not path.is_relative_to(self.directory):
            raise ValueError("Supplemental raw path outside configured cache")
        body = gzip.decompress(path.read_bytes())
        if sha256(body) != source["content_sha256"] or source["http_status"] != 200:
            raise ValueError("Supplemental source hash/status mismatch")
        return body
