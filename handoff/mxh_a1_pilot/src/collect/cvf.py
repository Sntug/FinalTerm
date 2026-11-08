"""CVF parsing, deterministic selection and cached HTTP, without third-party dependencies."""
from __future__ import annotations

import gzip
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from src.common import (
    PARSER_VERSION, SCHEMA_VERSION, canonical_cvf_url, clean_text, digest, now_utc,
    stable_id, write_json,
)


class CVFHTML(HTMLParser):
    """Collect repeated citation meta tags, links and selected div text.

    CVF has some unbalanced dd tags. Capture div depth instead of assuming XHTML.
    """

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.links: list[str] = []
        self.blocks: dict[str, str] = {}
        self._depth = 0
        self._active: list[tuple[str, int, list[str]]] = []
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta" and a.get("name") and a.get("content"):
            self.meta.setdefault(a["name"].lower(), []).append(a["content"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "div":
            self._depth += 1
            key = a.get("id")
            if key in {"papertitle", "abstract", "authors"}:
                self._active.append((key, self._depth, []))
            elif "bibref" in (a.get("class") or "").split():
                self._active.append(("bibtex", self._depth, []))
        if tag == "br":
            for _, _, text in self._active:
                text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "div":
            remaining = []
            for key, depth, text in self._active:
                if depth == self._depth:
                    self.blocks[key] = "".join(text).strip()
                else:
                    remaining.append((key, depth, text))
            self._active = remaining
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        for _, _, text in self._active:
            text.append(data)


def parse_listing(body: bytes, conference: str, year: int) -> list[str]:
    parsed = CVFHTML(body.decode("utf-8-sig"))
    expected = f"/content/{conference}{year}/html/"
    result = set()
    for link in parsed.links:
        url = urljoin("https://openaccess.thecvf.com/", link)
        if urlsplit(url).path.startswith(expected):
            try:
                result.add(canonical_cvf_url(url))
            except ValueError:
                pass
    if not result:
        raise ValueError(f"No main-conference papers found for {conference}{year}")
    return sorted(result)


def rank_urls(urls: list[str], seed: int) -> list[str]:
    # Hash ranking is reproducible across Python versions and independent of page order.
    return sorted(set(urls), key=lambda url: (digest(f"{seed}\n{url}".encode()), url))


MONTHS = {name.lower(): index for index, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def parse_detail(body: bytes, url: str, conference: str, year: int) -> dict:
    parsed = CVFHTML(body.decode("utf-8-sig"))
    meta = parsed.meta
    title_raw = (meta.get("citation_title") or [parsed.blocks.get("papertitle", "")])[0]
    visible_title = clean_text(parsed.blocks.get("papertitle", ""))
    title = clean_text(title_raw)
    if not title or not visible_title or title != visible_title:
        raise ValueError("Missing title or disagreement between citation_title and papertitle")
    source_year = (meta.get("citation_publication_date") or [""])[0]
    conference_title = clean_text((meta.get("citation_conference_title") or [""])[0])
    expected_title = {"CVPR": "Conference on Computer Vision and Pattern Recognition", "ICCV": "International Conference on Computer Vision"}[conference]
    if source_year[:4] != str(year) or expected_title.lower() not in conference_title.lower():
        raise ValueError("Conference/year metadata do not match the registry")
    names = meta.get("citation_author", [])
    if not names or any(not clean_text(name) for name in names):
        raise ValueError("No usable ordered citation_author metadata")
    authors = []
    for order, raw in enumerate(names, 1):
        # This is display formatting, never author disambiguation.
        name = clean_text(raw)
        if "," in name:
            family, given = name.split(",", 1)
            name = clean_text(given + " " + family)
        authors.append({"name": name, "name_raw": raw, "author_order": order})
    bibtex = parsed.blocks.get("bibtex", "")
    month_match = re.search(r"\bmonth\s*=\s*[{\"]([A-Za-z]+)[}\"]", bibtex, re.I)
    month = MONTHS.get(month_match.group(1).lower()) if month_match else None
    # Preserve available precision. Never turn a year/month into an invented day.
    if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", source_year):
        publication_date, precision = source_year.replace("/", "-"), "day"
    elif re.fullmatch(r"\d{4}[-/]\d{2}", source_year):
        publication_date, precision = source_year.replace("/", "-"), "month"
    elif month:
        publication_date, precision = f"{year}-{month:02d}", "month"
    else:
        publication_date, precision = str(year), "year"
    doi = (meta.get("citation_doi") or [None])[0]
    if not doi:
        match = re.search(r"\bdoi\s*=\s*[{\"]([^}\"]+)", bibtex, re.I)
        doi = match.group(1).strip() if match else None
    if doi:
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I).strip().lower()
        if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
            raise ValueError("Invalid DOI in CVF metadata")
    arxiv = sorted({urljoin(url, link).replace("http://arxiv.org/", "https://arxiv.org/") for link in parsed.links if re.match(r"https?://arxiv\.org/abs/", link)})
    if len(arxiv) > 1:
        raise ValueError("Multiple arXiv links need manual review")
    pdf = (meta.get("citation_pdf_url") or [None])[0]
    abstract_raw = parsed.blocks.get("abstract", "")
    return {
        "schema_version": SCHEMA_VERSION, "parser_version": PARSER_VERSION,
        "title_raw": title_raw, "title": title, "abstract_raw": abstract_raw,
        "abstract": clean_text(abstract_raw) or None, "authors": authors,
        "doi": doi, "cvf_url": url, "pdf_url": urljoin(url, pdf) if pdf else None,
        "arxiv_url": arxiv[0] if arxiv else None,
        "publication_date": publication_date, "date_precision": precision,
        "conference_title_raw": conference_title,
        "citation_publication_date_raw": source_year, "bibtex_raw": bibtex,
        "openalex_id": None, "citation_count": None,
        "affiliations": None, "referenced_works": None,
        "openalex_status": "not_collected", "affiliation_status": "not_collected",
        "references_status": "not_collected",
    }


class HTTPBlocked(RuntimeError):
    """Stop on 403/429. No proxy, alternate-host or user-agent evasion."""


class HTTPCache:
    def __init__(self, root: Path, offline: bool = False, delay: float = 1.0, retries: int = 2):
        self.root, self.offline = root, offline
        self.delay, self.retries = delay, retries
        self.last_request = 0.0
        self.network_requests = 0

    def get(self, url: str) -> tuple[bytes, dict]:
        if urlsplit(url).scheme != "https" or urlsplit(url).netloc != "openaccess.thecvf.com":
            raise ValueError("Collector only fetches official HTTPS CVF URLs")
        key = digest(url.encode())
        meta_path = self.root / "data" / "raw" / "http" / (key + ".json")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["url"] != url:
                raise ValueError("Cache URL mismatch")
            body = gzip.decompress((self.root / meta["raw_path"]).read_bytes())
            if digest(body) != meta["content_sha256"]:
                raise ValueError(f"Corrupt cache for {url}; do not silently refetch")
            return body, meta
        if self.offline:
            raise FileNotFoundError(f"Offline cache miss: {url}")
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            request = Request(url, headers={"User-Agent": "AcademicPilotCollector/1.0 (student metadata project)"})
            self.last_request = time.monotonic()
            self.network_requests += 1
            try:
                with urlopen(request, timeout=30) as response:
                    if response.geturl() != url or response.status != 200:
                        raise ValueError(f"Unexpected redirect/status for {url}")
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "")
                    if "html" not in content_type.lower():
                        raise ValueError(f"Expected HTML for {url}")
                    metadata = {
                        "url": url, "fetched_at": now_utc(), "http_status": response.status,
                        "content_sha256": digest(body), "content_type": content_type,
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified"),
                    }
                break
            except HTTPError as exc:
                if exc.code in {403, 429}:
                    raise HTTPBlocked(f"CVF returned {exc.code}; stopped without retrying") from exc
                if exc.code < 500 or attempt == self.retries:
                    raise
                time.sleep(2 ** attempt)
            except (URLError, TimeoutError) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"Network failed for {url}") from exc
                time.sleep(2 ** attempt)
        raw_path = Path("data/raw/http") / (metadata["content_sha256"] + ".html.gz")
        metadata["raw_path"] = raw_path.as_posix()
        (self.root / raw_path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / raw_path).write_bytes(gzip.compress(body, mtime=0))
        write_json(meta_path, metadata)
        return body, metadata


def source_record(meta: dict, paper_id: str | None, source_kind: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_record_id": stable_id("source:cvf", meta["url"], meta["content_sha256"]),
        "paper_id": paper_id, "source": "CVF", "source_kind": source_kind,
        "source_id": meta["url"], "source_version": None, **meta,
    }
