"""Publication checks shared by generation, archive, email and the public site."""
from dataclasses import asdict
from types import SimpleNamespace
import re


def clean_source_text(text: str) -> str:
    text = re.sub(r"^\s*(?:Abstract|Summary)\s*[:.\-]?\s+", "", text or "", flags=re.I)
    text = re.sub(r"^.*?Published online:\s*[^;]+;\s*doi:\S+\s*", "", text, flags=re.I)
    return text.strip()


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Publication requires {field}")
    if re.search(r"reports a relevant development|published a new item related to|"
                 r"agenda background is unclear|议程背景不明确|"
                 r"timing should be interpreted alongside|发布或转发的这条要闻显示|"
                 r"Published online:|\bdoi:\s*10\.|^\s*Abstract\b", value, re.I):
        raise ValueError(f"Placeholder or source metadata in {field}")
    if value.rstrip().endswith(("…", "...")):
        raise ValueError(f"Truncated source excerpt in {field}")


def validate_publication(digest, *, check_title=True):
    raw = digest if isinstance(digest, dict) else asdict(digest)
    if raw.get("generation_mode") not in {"ai", "reviewed"}:
        raise ValueError("Only validated editorial drafts can be published; preview/fallback blocked")
    news = raw.get("recent_news") or []
    signals = raw.get("research_signals") or raw.get("items") or []
    if not news and not signals:
        raise ValueError("Refusing to publish an empty edition")
    if check_title and len(news) + len(signals) >= 2:
        for field in ("issue_title_en", "issue_title_zh"):
            _text(raw.get(field), field)
        from .editorial import validate_issue_title
        validate_issue_title(raw, [SimpleNamespace(**r) for r in news], [SimpleNamespace(**r) for r in signals])
    selected_urls = {row["url"] for row in news + signals}
    if not set(raw.get("editorial_context_urls", [])) <= selected_urls:
        raise ValueError(f"Introduction or weekly thread cites an unselected article: {sorted(set(raw.get('editorial_context_urls', [])) - selected_urls)}. Rewrite these fields around the final selected articles and return only their URLs.")
    for item in news + signals:
        _text(item.get("title_en"), "article title")
        words = re.sub(r"^the\s+", "", item.get("source_org", ""), flags=re.I).split()
        names = {" ".join(words), " ".join(words[:2]), "".join(w[0] for w in words[:3])}
        names |= {re.sub(r"\s+(?:Environment|Climate|News)$", "", n, flags=re.I) for n in names}
        headline = re.sub(r"^the\s+", "", item["title_en"], flags=re.I)
        if any(n and re.match(re.escape(n) + r"\s+(?:says|reports|argues|frames|guide frames)\b", headline, re.I) for n in names):
            raise ValueError(f"Headline must name the development, not use a publisher-says formula: {item['title_en']!r}. Rewrite this specific headline while preserving uncertainty; source attribution is displayed separately.")
        if re.search(r"[–—-]\s*report\s*$", item["title_en"], re.I):
            raise ValueError("Use an informative editorial headline, without a trailing report label")
    for item in news:
        for field in ("one_sentence_en", "one_sentence_zh"):
            _text(item.get(field), field)
    for item in signals:
        for field in ("core_argument_en", "core_argument_zh", "why_now_en", "why_now_zh",
                      "agenda_position_en", "agenda_position_zh"):
            _text(item.get(field), field)
    for reading in raw.get("classic_readings") or raw.get("readings") or []:
        for field in ("note_en", "note_zh", "method_en", "methodology_zh"):
            _text(reading.get(field), field)
        if not set(reading.get("related_article_urls", [])) <= selected_urls:
            raise ValueError(f"Reading connection cites an unselected article: {reading.get('title')}. Reconnect it to an actually selected article and update related_article_urls.")
        abstract = clean_source_text(reading.get("abstract_en", ""))
        note = clean_source_text(reading["note_en"])
        words = re.findall(r"\w+", abstract.lower())
        note_words = re.findall(r"\w+", note.lower())
        if len(words) >= 20:
            # A long verbatim span is an excerpt, not an editorial interpretation.
            source = " ".join(words)
            if any(" ".join(note_words[i:i+25]) in source for i in range(max(0, len(note_words)-24))):
                raise ValueError("Reading note copies the source abstract; write a concise interpretation")
        if re.search(r"comparative.*method|sociotechnical analysis|regression|interviews|randomi[sz]ed", abstract, re.I) and re.search(
                r"does not (?:provide|specify|identify)[^.]{0,60}\bmethod|\bno [^.]{0,40}\bmethod|\bmethod[^.]{0,30}(?:not specified|not provided)", reading["method_en"], re.I):
            raise ValueError("Method disclaimer contradicts explicit method evidence in the abstract")
