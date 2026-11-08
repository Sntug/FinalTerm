"""Conservative metadata formatting; external identifiers are never inferred."""
import html
import re
from urllib.parse import unquote, urlsplit, urlunsplit

from .text import normalize


def clean_text(value):
    if value is None:
        return None
    # Preserve punctuation/diacritics and meaningful Unicode format characters.
    return normalize(html.unescape(value).replace('\ufeff', '').replace('\x00', ''))


def clean_url(value):
    if not value:
        return None
    parts = urlsplit(clean_text(value))
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Invalid public source URL')
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ''))


def doi(value):
    value = clean_text(value or '')
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value, flags=re.I)
    value = unquote(value).lower()
    return value if re.fullmatch(r'10\.\d{4,9}/\S+', value) else None


def openalex(value, kind):
    value = clean_text(value or '')
    match = re.fullmatch(r'(?:https?://(?:api\.)?openalex\.org/(?:works/|authors/|institutions/)?)?(' + kind + r'\d+)', value)
    return 'https://openalex.org/' + match[1] if match else None


def arxiv(value):
    if not value:
        return None
    parts = urlsplit(clean_url(value))
    if parts.hostname not in ('arxiv.org', 'www.arxiv.org'):
        return None
    match = re.fullmatch(r'/(?:abs|pdf)/((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7}))(?:v\d+)?(?:\.pdf)?', parts.path)
    return match[1] if match else None


def orcid(value):
    value = re.sub(r'^https?://orcid\.org/', '', clean_text(value or ''), flags=re.I).upper()
    if not re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', value):
        return None
    digits = value.replace('-', '')
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return value if digits[-1] == ('X' if check == 10 else str(check)) else None


def ror(value):
    value = re.sub(r'^https?://ror\.org/', '', clean_text(value or ''), flags=re.I).lower()
    if not re.fullmatch(r'0[0-9a-hjkmnp-tv-z]{6}\d{2}', value):
        return None
    alphabet = '0123456789abcdefghjkmnpqrstvwxyz'
    number = 0
    for char in value[:7]:
        number = number * 32 + alphabet.index(char)
    return value if int(value[-2:]) == 98 - (number * 100) % 97 else None
