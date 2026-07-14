from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Source:
    name: str
    type: str
    strategy: str
    allowed_domains: list[str]
    default_tags: list[str]
    url: str | None = None
    issn: list[str] = field(default_factory=list)
    layer: str = "research"


@dataclass(frozen=True)
class Candidate:
    title: str
    source_org: str
    source_type: str
    published_date: str
    url: str
    summary_hint: str
    tags: list[str]
    discovered_date: str
    doi: str | None = None
    full_text: str = ""
    text_source: str = "rss"
    semantic_score: int | None = None
    semantic_domain: str = ""
    semantic_reason: str = ""
    layer: str = "research"


@dataclass(frozen=True)
class NewsBrief:
    title_en: str
    source_org: str
    published_date: str
    url: str
    one_sentence_zh: str
    one_sentence_en: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FurtherReading:
    title: str
    authors: str
    year: int
    description_zh: str
    url: str = ""


@dataclass(frozen=True)
class ResearchDirection:
    question_zh: str
    keywords: list[str]
    question_en: str = ""


@dataclass(frozen=True)
class DeepRead:
    title: str
    authors: str
    year: int
    url: str
    note_zh: str = ""
    note_en: str = ""
    journal: str = ""
    doi: str = ""
    methodology_zh: str = ""
    further_reading: list[FurtherReading] = field(default_factory=list)
    argument_zh: str = ""
    argument_en: str = ""
    method_zh: str = ""
    method_en: str = ""
    evidence_zh: str = ""
    evidence_en: str = ""
    relevance_zh: str = ""
    relevance_en: str = ""
    today_relevance_en: str = ""
    today_connection_zh: str = ""
    today_connection_en: str = ""
    research_directions: list[ResearchDirection] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    kind: str = "reading"


@dataclass(frozen=True)
class DigestTerm:
    term_en: str
    term_zh: str
    explanation_zh: str


@dataclass(frozen=True)
class DigestItem:
    title_en: str
    source_org: str
    published_date: str
    summary_zh: str
    terms: list[DigestTerm]
    tags: list[str]
    url: str
    core_argument_zh: str = ""
    core_argument_en: str = ""
    why_now_zh: str = ""
    why_now_en: str = ""
    agenda_position_zh: str = ""
    agenda_position_en: str = ""
    summary_en: str = ""
    why_it_matters_zh: str = ""
    why_it_matters_en: str = ""
    sdg_links: list[str] = field(default_factory=list)
    deep_reads: list[DeepRead] = field(default_factory=list)


@dataclass(frozen=True)
class Digest:
    digest_date: date
    subject: str
    overview_zh: str
    items: list[DigestItem]
    readings: list[DeepRead] = field(default_factory=list)
    overview_en: str = ""
    weekly_thread_zh: str = ""
    weekly_thread_en: str = ""
    recent_news: list[NewsBrief] = field(default_factory=list)
    research_signals: list[DigestItem] = field(default_factory=list)
    classic_readings: list[DeepRead] = field(default_factory=list)
