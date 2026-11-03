"""Source-independent extraction; unknown dates are never replaced by today's date."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .collect import _clean_text, _entry_link, _entry_summary, _xml_text
from .models import Candidate


def canonical_url(url):
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "trk"}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(sorted(query)), ""))


def iso_date(value):
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    for fmt in ("%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y", "%d %b. %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def fingerprint(text):
    return hashlib.sha256(re.sub(r"\s+", " ", text.lower()).strip().encode()).hexdigest()[:24]


def event_identity(name, event_date="", url=""):
    # General session designators, not a list of favoured institutions or events.
    match = re.search(r"\b([A-Z]{2,8})[-– ](\d{1,3})\b", name)
    if match:
        return f"{match[1].lower()}-{match[2]}:{event_date[:4]}"
    name = re.sub(r"^(?:concept note and |concept note |agenda (?:of|for) (?:the )?|summary (?:of|report on) )+", "", name.lower())
    name = re.sub(r"[^\w]+", " ", name).strip()
    return "event:" + fingerprint((name or canonical_url(url)) + ":" + event_date[:4])


def normalize(candidate):
    published = iso_date(candidate.published_date)
    event_day = iso_date(candidate.event_date)
    text = candidate.title + " " + (candidate.full_text or candidate.summary_hint)
    stage = candidate.development_stage
    if stage == "unknown":
        lowered = text.lower()
        # Claims must be explicit; passing the scheduled date proves no outcome.
        if re.search(r"^(concept note|agenda\b|registration\b)|\b(dialogue|workshop|meeting) agenda\b", candidate.title, re.I) or (
            re.search(r"\b(will take place|will be held|scheduled|upcoming)\b", lowered)
            and not re.search(r"\b(was held|were held|concluded|took place)\b", lowered)):
            stage = "scheduled"
        elif re.search(r"\b(adopted|agreed|approved|decided|suspended|failed to agree|no agreement|reached agreement)\b", lowered):
            stage = "outcome"
        elif re.search(r"\b(was held|were held|concluded|convened|took place)\b", lowered):
            stage = "completed"
        elif re.search(r"\b(agenda|will take place|will be held|scheduled|upcoming|registration)\b", lowered):
            stage = "scheduled"
        elif re.search(r"\b(update|follow.up|implementation|revised)\b", lowered):
            stage = "subsequent_development"
    event_name = candidate.event_name or candidate.title
    if not candidate.event_id and event_name == candidate.title:
        session = re.search(r"\b[A-Z]{2,8}[-–]\d{1,3}\b", text[:1500])
        if session:
            event_name = session[0]
    layer = candidate.layer
    if re.search(r"\b(meeting|dialogue|session|negotiations?|workshop|summit)\b", candidate.title, re.I):
        layer = "event"
    elif re.search(r"\b(analysis|research|study|findings|explained|policy brief)\b", candidate.title, re.I):
        layer = "research"
    return replace(candidate, published_date=published, event_date=event_day, layer=layer,
                   publication_date_status="source_reported" if published else "missing",
                   event_id=candidate.event_id or event_identity(event_name, event_day or published, candidate.url),
                   event_name=event_name, development_stage=stage,
                   content_fingerprint=fingerprint(text))


def _candidate(title, url, summary, published, source, run_date, method, parent, **kwargs):
    return normalize(Candidate(title=_clean_text(title), url=url, source_org=source["name"],
        source_type=source.get("type", "international_org" if source.get("reliability") == "primary" else "think_tank"),
        published_date=published, summary_hint=_clean_text(summary)[:2400], tags=source.get("themes", []),
        discovered_date=run_date.isoformat(), discovery_method=method, provenance_url=parent,
        layer=source.get("layer", "event"), **kwargs))


def parse_feed(text, url, source, run_date, limit):
    root = ET.fromstring(text)
    if root.tag.split("}")[-1].lower() not in {"rss", "feed", "rdf"}:
        raise ValueError("not_a_feed")
    entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    entries = entries or root.findall(".//{http://purl.org/rss/1.0/}item")
    candidates, errors = [], []
    for index, entry in enumerate(entries):
        raw_link = _entry_link(entry) or _xml_text(entry, ["{http://purl.org/rss/1.0/}link"])
        link = urljoin(url, raw_link)
        title = _xml_text(entry, ["title", "{http://www.w3.org/2005/Atom}title", "{http://purl.org/rss/1.0/}title"])
        if index >= limit:
            errors.append({"url": link, "reason": "feed_entry_budget_exhausted", "title": title})
            continue
        published = _xml_text(entry, ["pubDate", "published", "{http://www.w3.org/2005/Atom}published",
                                     "{http://purl.org/dc/elements/1.1/}date"])
        updated = _xml_text(entry, ["updated", "{http://www.w3.org/2005/Atom}updated"])
        if not title or not raw_link:
            errors.append({"url": link, "reason": "feed_entry_missing_title_or_link"})
            continue
        c = _candidate(title, link, _entry_summary(entry), iso_date(published), source, run_date, "feed", url,
                       modified_date=iso_date(updated))
        candidates.append(c)
    return candidates, errors


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def parse_html(text, url, source, run_date, method="html", parent=""):
    soup = BeautifulSoup(text, "html.parser")
    metadata = {}
    for meta in soup.find_all("meta"):
        key = meta.get("property") or meta.get("name") or meta.get("itemprop")
        if key:
            metadata[key.lower()] = meta.get("content", "")
    structured = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            structured.extend(_nodes(json.loads(script.get_text())))
        except (ValueError, TypeError):
            pass
    article = next((n for n in structured if any(t in str(n.get("@type", ""))
                   for t in ("Article", "Report", "Event"))), {})
    event = next((n for n in structured if "Event" in str(n.get("@type", ""))), {})
    heading = soup.find("h1") or soup.find("h2") or soup.find("h5") or soup.title
    title = article.get("headline") or article.get("name") or metadata.get("og:title") or (heading.get_text(" ", strip=True) if heading else "")
    published_raw = article.get("datePublished") or metadata.get("article:published_time") or metadata.get("datepublished") or ""
    published = iso_date(published_raw)
    visible = soup.get_text(" ", strip=True)
    if not published:
        match = re.search(r"Publication date\s+(\d{1,2}\s+\w+\.?\s+\d{4})", visible, re.I)
        if match:
            published = iso_date(match[1])
    if not published:
        match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", visible)
        if match and "/press/" in url:
            try:
                published = date(*map(int, match.groups())).isoformat()
            except ValueError:
                pass
    if not published:
        time_tag = soup.find("time", attrs={"itemprop": "datePublished"})
        if time_tag:
            published = iso_date(time_tag.get("datetime", time_tag.get_text()))
    modified = iso_date(article.get("dateModified") or metadata.get("article:modified_time"))
    event_date = iso_date(event.get("startDate") or metadata.get("startdate"))
    event_end = iso_date(event.get("endDate") or metadata.get("enddate"))
    # Drupal event pages often expose datetime attributes without JSON-LD.
    times = [iso_date(t.get("datetime")) for t in soup.select('[datetime]')]
    if "/event/" in url and not event_date:
        times = [t for t in times if t]
        event_date = times[0] if times else ""
        event_end = times[-1] if times else ""
    if "/event/" in url and not event_date:
        match = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\.?\s+(20\d{2})", visible)
        if match:
            event_date = iso_date(f"{match[1]} {match[3]} {match[4]}")
            event_end = iso_date(f"{match[2]} {match[3]} {match[4]}")
        else:
            match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\.?\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\.?\s+(20\d{2})", visible)
            if match:
                event_date = iso_date(f"{match[1]} {match[2]} {match[5]}")
                event_end = iso_date(f"{match[3]} {match[4]} {match[5]}")
    links, feeds, related = [], [], []
    nofollow = "nofollow" in metadata.get("robots", "").lower()
    for link in ([] if nofollow else soup.find_all(["a", "link"], href=True)):
        if "nofollow" in link.get("rel", []):
            continue
        target = urljoin(url, link["href"])
        if urlsplit(target).scheme not in {"http", "https"}:
            continue
        label = link.get_text(" ", strip=True)
        kind = link.get("type", "")
        if "rss" in kind or "atom" in kind:
            feeds.append(target)
        elif link.name == "a":
            links.append((target, label))
            if re.search(r"document|agenda|decision|report|concept|\.pdf|/event/", target + " " + label, re.I):
                related.append(target)
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    body = _clean_text(container.get_text(" ", strip=True))
    prose = [p.get_text(" ", strip=True) for p in container.find_all("p")
             if not re.search(r"shareable version|printing onto paper|copyright", p.get_text(), re.I)]
    metadata_only = (body.strip() == str(title).strip() or ("/documents/" in url and not any(prose))) and not article.get("description") and not metadata.get("description")
    summary = article.get("description") or metadata.get("description") or metadata.get("og:description") or body
    is_content = bool(article or published or event_date or re.search(r"/(?:event|news|documents|press|publication|analysis|story|stories)/", url))
    candidate = None
    if title and is_content:
        candidate = _candidate(str(title), url, str(summary), published, source, run_date, method, parent or url,
            full_text=" ".join(body.split()[:600]), text_source="metadata_only" if metadata_only else "html", event_name=str(event.get("name", "")),
            event_date=event_date, event_end_date=event_end, modified_date=modified,
            related_documents=list(dict.fromkeys(related))[:20])
    return candidate, feeds, links


def parse_api(text, url, source, run_date):
    """Explicit JSON Feed / schema.org APIs only; no invented API paths."""
    raw = json.loads(text)
    rows = raw.get("items", []) if isinstance(raw, dict) else []
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("url") or not row.get("title"):
            continue
        candidates.append(_candidate(row["title"], urljoin(url, row["url"]),
            row.get("summary") or row.get("content_text") or row.get("content_html", ""),
            iso_date(row.get("date_published")), source, run_date, "api", url,
            modified_date=iso_date(row.get("date_modified"))))
    return candidates
