#!/usr/bin/env python3
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URL = 'https://openaccess.thecvf.com/ICCV2023?day=all'
ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'ICCV2023_all_papers.html'
OUT = ROOT / 'ICCV2023_catalog.json'
MANIFEST = ROOT / 'manifest.json'

was_cached = RAW.exists()
previous_manifest = json.loads(MANIFEST.read_text(encoding='utf-8')) if was_cached and MANIFEST.exists() else {}
if not was_cached:
    request = Request(URL, headers={'User-Agent': 'FinalTerm ICCV catalog metadata/1.0'})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'CVF returned HTTP {response.status}')
        RAW.write_bytes(response.read())
    retrieved_at = datetime.now(timezone.utc).isoformat()
else:
    retrieved_at = previous_manifest.get('retrieved_at_utc')
source = RAW.read_bytes()
page = source.decode('utf-8')
blocks = re.findall(r'<dt class="ptitle"><br><a href="([^"]+)">(.*?)</a></dt>\s*<dd>(.*?)</dd>', page, re.S)
records = []
for path, title, author_block in blocks:
    match = re.fullmatch(r'/content/ICCV2023/html/([^/]+_paper\.html)', path)
    if not match:
        continue
    slug = match.group(1)[:-len('_paper.html')]
    authors = [html.unescape(name) for name in re.findall(r'name="query_author" value="([^"]+)"', author_block)]
    records.append({
        'paper_id': f'cvf:ICCV2023:{slug}',
        'title': html.unescape(re.sub(r'<[^>]+>', '', title)).strip(),
        'authors': authors,
        'cvf_url': f'https://openaccess.thecvf.com{path}',
        'conference': 'ICCV',
        'conference_year': 2023,
    })
records.sort(key=lambda row: row['paper_id'])
ids = [row['paper_id'] for row in records]
if not records or len(ids) != len(set(ids)) or any(not row['title'] or not row['authors'] for row in records):
    raise RuntimeError('Catalog validation failed: empty, duplicate ID, or missing title/authors')
OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
MANIFEST.write_text(json.dumps({
    'source_url': URL,
    'retrieved_at_utc': retrieved_at,
    'raw_html_file': RAW.name,
    'raw_html_sha256': hashlib.sha256(source).hexdigest(),
    'parsed_json_file': OUT.name,
    'parsed_json_sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
    'paper_count': len(records),
    'parser': 'Python standard library regex for CVF dt.ptitle records and hidden query_author values; only /content/ICCV2023/html/*_paper.html records included.',
    'selection_status': 'unselected complete catalog input; no 350-paper cohort sampled',
    'id_status': 'provisional CVF slug scheme; shared ID contract owner A',
    'retrieval_note': 'On cached reparse, preserve the original retrieval timestamp and do not fetch the source again.',
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'{len(records)} records; raw SHA-256 {hashlib.sha256(source).hexdigest()}')
