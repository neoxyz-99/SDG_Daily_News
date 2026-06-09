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


@dataclass(frozen=True)
class DeepRead:
    title: str
    authors: str
    year: int
    url: str
    note_zh: str = ""
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
    deep_reads: list[DeepRead] = field(default_factory=list)


@dataclass(frozen=True)
class Digest:
    digest_date: date
    subject: str
    overview_zh: str
    items: list[DigestItem]
    readings: list[DeepRead] = field(default_factory=list)
