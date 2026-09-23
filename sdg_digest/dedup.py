"""Keep the more detailed signal when an article appears in both modules."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit


def article_key(url: str) -> str:
    parts = urlsplit(url.strip())
    query = sorted((k, v) for k, v in parse_qsl(parts.query)
                   if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"})
    return parts.netloc.lower().removeprefix("www.") + parts.path.rstrip("/") + ("?" + urlencode(query) if query else "")


def unique_articles(items, excluded=()):
    seen = {article_key(item.url) for item in excluded if item.url}
    result = []
    for item in items:
        key = article_key(item.url)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(item)
    return result
