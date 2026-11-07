"""CVF parser and deterministic selection ported from the A1 handoff."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .common import PARSER_VERSION, canonical_cvf_url
from src.clean.text import normalize as clean_text, sha256 as digest

# This parser emits the original raw observation shape; export.py converts it to v2.
SCHEMA_VERSION = "1.0.0"


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

