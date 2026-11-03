"""Opt-in event discovery, verification and comparative editorial selection.

All discovered documents receive an audit row, including failures and duplicates.
This module never sends mail or writes the publication archive.
"""
from __future__ import annotations

import json
import re
from collections import Counter, deque
from dataclasses import asdict, replace
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree as ET

from .discovery_config import DiscoveryConfig
from .discovery_http import FetchFailure, PublicFetcher
from .discovery_parse import canonical_url, fingerprint, normalize, parse_api, parse_feed, parse_html
from .models import Candidate, Digest, NewsBrief, Source

REASONS = {"source_not_monitored", "discovery_or_extraction_failure", "insufficient_evidence",
           "outside_temporal_scope", "deduplication", "low_substantive_relevance",
           "lower_editorial_priority", "selected_for_publication"}
TOPICS = {
    "climate_policy": r"climate|emission|adaptation|mitigation|energy transition|renewable|fossil fuel|carbon|温室|气候|减排",
    "development": r"sustainable development|poverty|inequal|food security|health|education|water|biodiversity|ecosystem|conservation|resilien|发展|贫困|不平等",
    "political_economy": r"trade|debt|tax|finance|investment|value chain|industrial|subsid|融资|债务|贸易",
    "governance": r"governance|multilateral|international|institution|just transition|public policy|治理|多边|公正转型",
}
MECHANISMS = r"polic|negotiat|dialogue|consultation|agreement|decision|reform|regulat|fund|budget|assessment|work programme|workshop|research|evidence|report|implementation|deadline|timeline|mechanism|政策|协商|协议|改革|研究|机制"
IMPLICATIONS = r"implement|mandat|institution|government|minister|parties|accountab|distribution|rights|financ|capacity|assessment|governance|规则|政府|实施|分配"
NOISE = r"\b(match result|celebrity|album release|box office|coupon|sweepstakes|vacancy|job opening)\b"
LINK_CUES = r"news|event|calendar|meeting|document|publication|press|report|decision|dialogue|climate|transition|finance|governance|sustainab|policy|sitemap|feed|rss"


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def assess(candidate, reliability, run_date):
    text = candidate.title + " " + (candidate.full_text or candidate.summary_hint)
    topics = [name for name, pattern in TOPICS.items() if re.search(pattern, text, re.I)]
    mechanism = bool(re.search(MECHANISMS, text, re.I))
    implications = bool(re.search(IMPLICATIONS, text, re.I))
    noise = bool(re.search(NOISE, candidate.title, re.I))
    dimensions = {
        "substantive_significance": 2 if topics and mechanism else 0,
        "institutional_implications": int(implications and bool(topics)),
        "scope_relevance": min(2, len(topics)),
        "novelty_timeliness": int(bool(candidate.published_date or candidate.event_date)),
        "evidence_strength": int(reliability in {"primary", "established_secondary"} and bool(candidate.summary_hint)),
        "future_policy_implications": int(mechanism and implications),
    }
    # Names of institutions and conflict language carry no score by themselves.
    substantive = bool(topics and mechanism and not noise)
    score = sum(dimensions.values()) if substantive else 0
    return {"score": score, "dimensions": dimensions, "themes": topics,
            "substantive": substantive,
            "method": "transparent_rules_v1",
            "reason": "Policy mechanism and thematic evidence" if substantive else "No supported policy mechanism in scope"}


class DiscoveryPipeline:
    def __init__(self, config: DiscoveryConfig, run_date: date, state_dir: Path, fetcher=None):
        self.config, self.run_date, self.state_dir = config, run_date, Path(state_dir)
        self.registry = read_json(self.state_dir / "sources.json", {})
        self.history = read_json(self.state_dir / "events.json", {})
        self.fetcher = fetcher or PublicFetcher(self.state_dir / "cache", max_requests=config.max_requests,
            per_host=config.requests_per_host, delay=config.delay_seconds, timeout=config.timeout_seconds,
            max_bytes=config.max_response_bytes, cache_hours=config.cache_hours)
        self.rows: list[dict] = []
        self.candidates: list[Candidate] = []
        self.selected: list[Candidate] = []
        self.upcoming: list[Candidate] = []
        self.source_events: list[dict] = []
        self.visited: set[str] = set()
        self.new_sources = self.searches = self.evidence_fetches = 0
        self.published_keys: list[str] = []
        self.registry_by_host: dict[str, dict] = {}
        self.report_status = "discovery_complete"

    def _failure(self, url, reason, **extra):
        self.source_events.append({"url": url, "decision": "discovery_or_extraction_failure", "reason": reason, **extra})

    def _register(self, url, source, method, parent, kind, verified=False):
        key = canonical_url(url)
        old = self.registry.get(key, {})
        value = {**old, "url": url, "publisher": source["name"], "source_type": kind,
                 "discovery_method": old.get("discovery_method", method),
                 "provenance": list(dict.fromkeys([*old.get("provenance", []), parent])),
                 "reliability": old.get("reliability", source.get("reliability", "unreviewed")),
                 "themes": source.get("themes", []), "layer": source.get("layer", "event"),
                 "verified": verified or old.get("verified", False),
                 "last_attempt": self.run_date.isoformat()}
        if verified:
            value["last_successful_fetch"] = self.run_date.isoformat()
            value["last_error"] = ""
        self.registry[key] = value
        return value

    def _add(self, candidate, reliability):
        c = normalize(candidate)
        self.candidates.append(c)
        self.rows.append({**asdict(c), "candidate_id": fingerprint(c.url + c.content_fingerprint + str(len(self.rows))),
            "reliability": reliability, "relevance_assessment": {}, "decision": "pending",
            "exclusion_reason": "", "verification_status": "unverified"})

    def _source_for(self, url, parent_source, parent):
        host = urlsplit(url).netloc.lower()
        if host in self.registry_by_host:
            return self.registry_by_host[host]
        for known_host, known_source in list(self.registry_by_host.items()):
            base = known_host.removeprefix("www.")
            if host.removeprefix("www.") == base or host.endswith("." + base):
                self.registry_by_host[host] = known_source
                return known_source
        if self.new_sources >= self.config.max_discovered_sources:
            self.source_events.append({"url": url, "decision": "source_not_monitored",
                "reason": "new_source_budget_exhausted", "provenance": parent})
            return None
        self.new_sources += 1
        # A citation is provenance, not certification. Unreviewed hosts can be discovered
        # and assessed but cannot support publication until corroborated/reviewed.
        source = {"name": host, "url": url, "reliability": "unreviewed", "layer": "event", "themes": []}
        self.registry_by_host[host] = source
        return source

    def discover(self, sources: list[Source], search_results: list[dict] | None = None):
        queue = deque()
        for seed in self.config.seeds:
            source = {**seed, "layer": seed.get("layer", "event")}
            self.registry_by_host[urlsplit(seed["url"]).netloc] = source
            queue.append((seed["url"], source, 0, "seed", seed["url"], "html"))
        for source in sources:
            if source.strategy != "rss" or not source.url:
                continue
            descriptor = {"name": source.name, "url": source.url, "type": source.type,
                "reliability": "primary" if source.type == "international_org" else "established_secondary",
                "layer": source.layer, "themes": source.default_tags}
            self.registry_by_host[urlsplit(source.url).netloc] = descriptor
            for domain in source.allowed_domains:
                self.registry_by_host.setdefault(domain, descriptor)
            queue.append((source.url, descriptor, 0, "configured_feed", "sources.yml", "feed"))
        # Reuse verified endpoints, and recheck tracked event pages for meaningful updates.
        for record in list(self.registry.values()):
            if record.get("verified"):
                source = {"name": record["publisher"], "reliability": record["reliability"],
                          "layer": record.get("layer", "event"), "themes": record.get("themes", [])}
                self.registry_by_host.setdefault(urlsplit(record["url"]).netloc, source)
                queue.append((record["url"], source, 0, "registry", "sources.json", record["source_type"]))
        for entry in self.history.values():
            if entry.get("last_seen", "") >= (self.run_date - timedelta(days=self.config.state_retention_days)).isoformat():
                source = self.registry_by_host.get(urlsplit(entry["url"]).netloc)
                if source:
                    queue.append((entry["url"], source, 0, "continuity", "events.json", "html"))
        for result in search_results or []:
            source = self._source_for(result["url"], {}, result.get("query", "imported_search"))
            if source:
                queue.append((result["url"], source, 0, "search", result.get("query", "imported_search"), "html"))
        self._crawl(queue)
        if self.config.search_url:
            # Meeting/development triggers are derived from the discovered pool, not examples.
            triggers = sorted(self.candidates, key=lambda c: assess(c, "unreviewed", self.run_date)["score"], reverse=True)
            for c in triggers:
                if self.searches >= self.config.max_searches:
                    break
                if c.development_stage != "unknown" and assess(c, "unreviewed", self.run_date)["substantive"]:
                    self._search(c.event_name + " decisions outcomes documents " + str(self.run_date.year))
        else:
            self.source_events.append({"decision": "source_not_monitored", "url": "",
                "reason": "live_search_not_configured", "detail": "Use search-results import or an operator-provided JSON search endpoint"})
        return self.candidates

    def _search(self, query):
        self.searches += 1
        url = self.config.search_url + ("&" if "?" in self.config.search_url else "?") + urlencode({"q": query, "format": "json"})
        try:
            results = json.loads(self.fetcher.get(url).text).get("results", [])
            queue = deque()
            for result in results[:self.config.max_links_per_page]:
                target = result.get("url", "")
                if not target:
                    continue
                source = self._source_for(target, {}, query)
                if source:
                    queue.append((target, source, 0, "targeted_search", query, "html"))
            self._crawl(queue)
        except (FetchFailure, ValueError, TypeError) as exc:
            self._failure(url, str(exc), discovery_method="targeted_search")

    def _crawl(self, queue):
        while queue:
            url, source, depth, method, parent, kind = queue.popleft()
            key = canonical_url(url)
            if key in self.visited:
                continue
            self.visited.add(key)
            record = self._register(url, source, method, parent, kind)
            try:
                response = self.fetcher.get(url)
                # A redirect onto an unknown publisher does not inherit seed credibility.
                if urlsplit(response.url).netloc != urlsplit(url).netloc:
                    source = self._source_for(response.url, source, url)
                    if source is None:
                        continue
                body = response.text
                stripped = body.lstrip()
                if kind == "feed" or re.match(r"(?:<\?xml[^>]*>\s*)?<(?:rss|feed)\b", stripped):
                    items, errors = parse_feed(body, response.url, source, self.run_date, self.config.max_feed_entries)
                    for c in items:
                        article_source = self._source_for(c.url, source, response.url)
                        if article_source:
                            self._add(replace(c, source_org=article_source["name"]), article_source["reliability"])
                        else:
                            self._add(replace(c, source_org=urlsplit(c.url).netloc), "unreviewed")
                    for error in errors:
                        self._failure(error.pop("url"), error.pop("reason"), **error)
                    kind = "feed"
                    links, feeds = [], []
                elif kind == "sitemap" or "<urlset" in stripped[:500] or "<sitemapindex" in stripped[:500]:
                    root = ET.fromstring(body)
                    links = [(n.text, "sitemap" if "sitemapindex" in root.tag else "")
                             for n in root.iter() if n.tag.split("}")[-1] == "loc" and n.text]
                    feeds, kind = [], "sitemap"
                elif "json" in response.content_type and not stripped.startswith("<"):
                    for c in parse_api(body, response.url, source, self.run_date):
                        article_source = self._source_for(c.url, source, response.url)
                        if article_source:
                            self._add(replace(c, source_org=article_source["name"]), article_source["reliability"])
                        else:
                            self._add(replace(c, source_org=urlsplit(c.url).netloc), "unreviewed")
                    feeds, links, kind = [], [], "api"
                else:
                    c, feeds, links = parse_html(body, response.url, source, self.run_date, method, parent)
                    if c:
                        self._add(c, source["reliability"])
                    elif depth > 0:
                        self._failure(url, "no_document_metadata", discovery_method=method)
                self._register(response.url, source, method, parent, kind, verified=True)
                if depth == 0:
                    origin = f"{urlsplit(response.url).scheme}://{urlsplit(response.url).netloc}"
                    links = [(u, "sitemap") for u in getattr(self.fetcher, "sitemaps", {}).get(origin, [])] + links
                # Prioritize machine-readable endpoints and topical paths; budget applies to
                # traversal only. Every extracted article is assessed, without length/source caps.
                outgoing = [(u, "feed", "feed") for u in feeds]
                links.sort(key=lambda pair: -len(re.findall(LINK_CUES, pair[0] + " " + pair[1], re.I)))
                outgoing += [(u, label, "sitemap" if "sitemap" in label or "sitemap" in u else "html")
                             for u, label in links if kind == "sitemap" or re.search(LINK_CUES, u + " " + label, re.I)]
                for i, (target, label, target_kind) in enumerate(outgoing):
                    if canonical_url(target) in self.visited:
                        continue
                    if depth >= self.config.max_depth or i >= self.config.max_links_per_page:
                        self.source_events.append({"url": target, "provenance": url,
                            "decision": "discovery_or_extraction_failure", "reason": "crawl_depth_or_link_budget"})
                        continue
                    target_source = source if urlsplit(target).netloc == urlsplit(response.url).netloc else self._source_for(target, source, url)
                    if target_source:
                        queue.append((target, target_source, depth + 1, target_kind if target_kind != "html" else "html_link", url, target_kind))
            except (FetchFailure, ValueError, TypeError, ET.ParseError) as exc:
                record["last_error"] = str(exc)
                self._failure(url, str(exc), discovery_method=method, publisher=source["name"])

    def _decide(self, row, decision, reason):
        assert decision in REASONS
        row["decision"], row["exclusion_reason"] = decision, reason

    def evaluate(self, sent_record=None):
        sent = set((sent_record or {}).get("sent_urls", []) + (sent_record or {}).get("recent_news_urls", []) + (sent_record or {}).get("research_signal_urls", []))
        assessed = []
        for c, row in zip(self.candidates, self.rows):
            row["relevance_assessment"] = assess(c, row["reliability"], self.run_date)
            assessed.append((c, row))
        # Stage E: spend retrieval budget after initial significance assessment; prefer
        # institutional documents among equal-significance items.
        assessed.sort(key=lambda pair: (pair[1]["relevance_assessment"]["score"], pair[1]["reliability"] == "primary"), reverse=True)
        eligible = []
        for c, row in assessed:
            if not row["relevance_assessment"]["substantive"] or row["relevance_assessment"]["score"] < self.config.relevance_threshold:
                self._decide(row, "low_substantive_relevance", row["relevance_assessment"]["reason"])
                continue
            if (not c.full_text or not c.published_date) and self.evidence_fetches < self.config.evidence_requests:
                self.evidence_fetches += 1
                try:
                    result = self.fetcher.get(c.url)
                    resolved_source = self._source_for(result.url, {}, c.url) if urlsplit(result.url).netloc != urlsplit(c.url).netloc else {"reliability": row["reliability"], "name": c.source_org}
                    if resolved_source and urlsplit(result.url).netloc != urlsplit(c.url).netloc:
                        row["reliability"] = resolved_source["reliability"]
                        c = replace(c, source_org=resolved_source["name"])
                    elif resolved_source is None:
                        self._decide(row, "insufficient_evidence", "redirect_publisher_not_verified")
                        continue
                    source = {"name": c.source_org, "reliability": row["reliability"], "layer": c.layer, "themes": c.tags}
                    extracted, _, _ = parse_html(result.text, result.url, source, self.run_date, c.discovery_method, c.provenance_url)
                    if extracted:
                        if c.published_date and extracted.published_date and c.published_date != extracted.published_date:
                            row["date_conflict"] = {"feed": c.published_date, "page": extracted.published_date}
                            self._decide(row, "insufficient_evidence", "publication_date_conflict")
                            continue
                        c = normalize(replace(c, full_text=extracted.full_text,
                            published_date=extracted.published_date or c.published_date,
                            modified_date=extracted.modified_date or c.modified_date,
                            event_name=extracted.event_name if extracted.event_date else c.event_name,
                            event_date=extracted.event_date or c.event_date, event_end_date=extracted.event_end_date or c.event_end_date,
                            related_documents=list(dict.fromkeys(c.related_documents + extracted.related_documents)),
                            event_id="", development_stage="unknown", text_source=extracted.text_source))
                except (FetchFailure, ValueError, TypeError) as exc:
                    row["retrieval_failure"] = str(exc)
            row.update({k: v for k, v in asdict(c).items() if k not in {"verification_status"}})
            row["relevance_assessment"] = assess(c, row["reliability"], self.run_date)
            if row["relevance_assessment"]["score"] < self.config.relevance_threshold:
                self._decide(row, "low_substantive_relevance", "retrieved_content_does_not_support_relevance")
                continue
            earliest = (self.run_date - timedelta(days=self.config.rolling_days)).isoformat()
            today = self.run_date.isoformat()
            date_key = c.published_date
            previous = self.history.get(canonical_url(c.url), {})
            # A modified timestamp alone is not a new development: require content change
            # against a stored previous snapshot and an explicit substantive-update signal.
            changed = bool(previous and previous.get("published_fingerprint", previous.get("fingerprint")) != c.content_fingerprint
                           and c.development_stage in {"outcome", "subsequent_development"})
            if changed and c.modified_date:
                date_key = c.modified_date
                row["temporal_basis"] = "verified_modified_date_with_content_change"
            else:
                row["temporal_basis"] = "publication_date"
            upcoming = (c.development_stage == "scheduled" and today < c.event_date <=
                        (self.run_date + timedelta(days=self.config.upcoming_days)).isoformat())
            if c.published_date > today or c.modified_date > today:
                self._decide(row, "outside_temporal_scope", "future_publication_or_version")
                continue
            if not date_key and not upcoming:
                self._decide(row, "insufficient_evidence", "publication_date_missing; event_date_is_not_publication_date")
                continue
            if not upcoming and not earliest <= date_key <= today:
                self._decide(row, "outside_temporal_scope", "outside_rolling_publication_window")
                continue
            if row["reliability"] not in {"primary", "established_secondary"}:
                self._decide(row, "insufficient_evidence", "publisher_requires_review_or_independent_corroboration")
                continue
            if c.text_source == "metadata_only" and c.development_stage != "scheduled":
                self._decide(row, "insufficient_evidence", "document_metadata_only; substantive_document_not_retrieved")
                continue
            if not (c.summary_hint or c.full_text):
                self._decide(row, "insufficient_evidence", "no_supporting_text")
                continue
            status = "primary_source_supported" if row["reliability"] == "primary" else "reputable_reporting_supported"
            evidence = [{"url": c.url, "publisher": c.source_org, "publication_date": c.published_date,
                         "supports": c.development_stage, "reliability": row["reliability"]}]
            c = replace(c, verification_status=status, evidence=evidence,
                        semantic_score=row["relevance_assessment"]["score"], semantic_reason=row["relevance_assessment"]["reason"])
            row["verification_status"], row["evidence"] = status, evidence
            summary_key = fingerprint(c.summary_hint or c.full_text)
            prior_event = any(entry.get("event_id") == c.event_id and entry.get("published_stage") == c.development_stage
                and entry.get("published_summary_fingerprint") == summary_key for entry in self.history.values())
            if prior_event:
                self._decide(row, "deduplication", "event_update_already_published_from_another_document")
                continue
            previous_versions = previous.get("published_versions", [])
            if c.content_fingerprint in previous_versions or (c.url in sent and not changed):
                self._decide(row, "deduplication", "previously_published_without_verified_substantive_update")
                continue
            # Scheduled notices stay out of news even when their dates have passed.
            if c.development_stage == "scheduled":
                if upcoming:
                    self.upcoming.append(c)
                    self._decide(row, "lower_editorial_priority", "upcoming_section_pending_or_disabled")
                else:
                    self._decide(row, "insufficient_evidence", "announcement_only; outcome_or_completion_not_verified")
                continue
            eligible.append((c, row))
        # Stage C/F: consolidate supporting reports conservatively; keep distinct updates.
        unique = []
        for c, row in eligible:
            duplicate = None
            for existing, existing_row in unique:
                same_url = canonical_url(c.url) == canonical_url(existing.url)
                same_event = c.event_id == existing.event_id or (
                    c.published_date[:4] == existing.published_date[:4] and
                    re.findall(r"\d+", c.event_name) == re.findall(r"\d+", existing.event_name) and
                    SequenceMatcher(None, c.event_name.lower(), existing.event_name.lower()).ratio() >= .9)
                same_update = c.development_stage == existing.development_stage and c.published_date == existing.published_date and (
                    c.content_fingerprint == existing.content_fingerprint or
                    SequenceMatcher(None, c.summary_hint.lower(), existing.summary_hint.lower()).ratio() >= .9)
                if (same_url and (c.modified_date == existing.modified_date or not c.modified_date or not existing.modified_date)) or (same_event and same_update):
                    duplicate = (existing, existing_row)
                    break
                if same_event:
                    row["event_id"] = existing.event_id
                    c = replace(c, event_id=existing.event_id)
            if duplicate:
                existing, existing_row = duplicate
                existing_row["evidence"] += c.evidence
                existing_row["related_documents"] = list(dict.fromkeys(existing_row["related_documents"] + [c.url] + c.related_documents))
                self._decide(row, "deduplication", "same_url_same_document_version" if canonical_url(c.url) == canonical_url(existing.url) else "same_event_same_substantive_update")
                row["duplicate_of"] = existing_row["candidate_id"]
            else:
                unique.append((c, row))
        # Soft diversity tiebreaks only: a stronger item always wins; no country/topic quotas.
        ranked, counts = [], Counter()
        while unique:
            unique.sort(key=lambda pair: (pair[1]["relevance_assessment"]["score"],
                -counts[pair[0].source_org], pair[0].published_date), reverse=True)
            c, row = unique.pop(0)
            counts[c.source_org] += 1
            ranked.append((replace(c, evidence=row["evidence"], related_documents=row["related_documents"]), row))
        self.selected = [c for c, _ in ranked[:self.config.selection_pool]]
        for index, (_, row) in enumerate(ranked):
            row["editorial_rank"] = index + 1
            self._decide(row, "lower_editorial_priority", "awaiting_final_editorial_selection" if index < self.config.selection_pool else "comparative_rank_exceeds_configured_selection_pool")
        self._remember()
        return self.selected

    def _remember(self):
        for row in self.rows:
            if row["decision"] in {"outside_temporal_scope", "low_substantive_relevance"}:
                continue
            key = canonical_url(row["url"])
            previous = self.history.get(key, {})
            self.history[key] = {**previous, "url": row["url"], "event_id": row["event_id"],
                "fingerprint": row["content_fingerprint"], "stage": row["development_stage"],
                "published_date": row["published_date"], "last_seen": self.run_date.isoformat()}
        oldest = (self.run_date - timedelta(days=self.config.state_retention_days)).isoformat()
        self.history = {k: v for k, v in self.history.items() if v.get("last_seen", "") >= oldest}

    def upcoming_candidates(self):
        result, seen = [], set()
        for c in sorted(self.upcoming, key=lambda c: (-(c.semantic_score or 0), c.event_date)):
            if c.event_id in seen or len(result) >= self.config.max_upcoming:
                continue
            seen.add(c.event_id)
            result.append(c)
        return result

    def upcoming_briefs(self):
        result = []
        for c in self.upcoming_candidates():
            result.append(NewsBrief(title_en=c.title_en or c.title, source_org=c.source_org,
                published_date=c.event_date, url=c.url,
                one_sentence_zh=f"预定于 {c.event_date} 举行；现有资料仅支持会议安排，不代表已产生成果。",
                one_sentence_en=f"Scheduled for {c.event_date}; available evidence confirms the plan, not an outcome."))
        return result

    def finalize(self, digest: Digest, *, published=False):
        urls = {c.url for c in [*digest.recent_news, *digest.research_signals, *digest.items, *digest.upcoming_events]}
        self.report_status = "published" if published else "draft_selected"
        for row in self.rows:
            if row["decision"] in {"lower_editorial_priority", "selected_for_publication"}:
                if row["url"] in urls:
                    self._decide(row, "selected_for_publication", "")
                    if published:
                        key = canonical_url(row["url"])
                        entry = self.history[key]
                        entry["published_fingerprint"] = row["content_fingerprint"]
                        entry["published_summary_fingerprint"] = fingerprint(row["summary_hint"] or row["full_text"])
                        entry["published_stage"] = row["development_stage"]
                        entry["published_versions"] = list(dict.fromkeys(entry.get("published_versions", []) + [row["content_fingerprint"]]))[-10:]
                elif row["exclusion_reason"] == "awaiting_final_editorial_selection":
                    self._decide(row, "lower_editorial_priority", "not_chosen_by_final_comparative_editorial_selection")

    def report(self):
        # Public diagnostics contain metadata and decisions, not reproduced article bodies.
        report_rows = [{k: v for k, v in row.items() if k not in {"full_text", "summary_hint"}} for row in self.rows]
        return {"schema_version": 1, "run_date": self.run_date.isoformat(), "status": self.report_status,
            "config": asdict(self.config), "decisions": dict(Counter(row["decision"] for row in self.rows)),
            "metrics": {**self.fetcher.metrics(), "candidate_count": len(self.rows),
                "distinct_publishers": len({c.source_org for c in self.candidates}),
                "evidence_retrieval_attempts": self.evidence_fetches, "search_queries": self.searches,
                "discovery_ai_calls": 0, "generation_pool_size": len(self.selected),
                "generation_input_characters": sum(len(c.title + c.summary_hint + c.full_text) for c in self.selected)},
            "sources": list(self.registry.values()), "source_events": self.source_events, "candidates": report_rows}

    def save(self, report_path, *, persist=True):
        write_json(report_path, self.report())
        if persist:
            write_json(self.state_dir / "sources.json", self.registry)
            write_json(self.state_dir / "events.json", self.history)

    def trace(self, url="", query=""):
        matches = [row for row in self.rows if (url and canonical_url(row["url"]) == canonical_url(url))
                   or (query and query.lower() in json.dumps(row, ensure_ascii=False).lower())]
        if matches:
            return matches
        failures = [row for row in self.source_events if (url and canonical_url(row["url"]) == canonical_url(url))
                    or (query and query.lower() in json.dumps(row).lower())]
        if failures:
            return failures
        host = urlsplit(url).netloc
        monitored = any(urlsplit(row["url"]).netloc == host for row in self.registry.values()) if host else False
        return [{"url": url, "query": query, "decision": "discovery_or_extraction_failure" if monitored else "source_not_monitored",
                 "reason": "not_found_in_bounded_discovery; historical_cause_unknown" if monitored else "no_registered_source_for_query"}]
