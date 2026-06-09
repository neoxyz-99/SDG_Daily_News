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
    why_now_zh: str = ""
    agenda_position_zh: str = ""
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
