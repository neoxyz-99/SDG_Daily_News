import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sdg_digest.discovery import DiscoveryPipeline, assess
from sdg_digest.discovery_config import DiscoveryConfig
from sdg_digest.discovery_http import FetchFailure, FetchResult, PublicFetcher
from sdg_digest.discovery_parse import canonical_url, normalize, parse_feed, parse_html
from sdg_digest.models import Candidate, Digest, NewsBrief, Source


class FixtureFetcher:
    def __init__(self, pages=None):
        self.pages = pages or {}
        self.calls = []
        self.sitemaps = {}

    def get(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise FetchFailure("fixture_missing")
        body = self.pages[url]
        return FetchResult(url, body, "application/json" if body.startswith("{") else "text/html")

    def metrics(self):
        return {"http_requests": len(self.calls), "cache_hits": 0, "downloaded_bytes": 0}


def candidate(**kwargs):
    values = dict(title="Government approves climate adaptation finance reform", source_org="Government",
        source_type="international_org", published_date="2026-10-12", url="https://agency.int/news/1",
        summary_hint="The government approved a climate finance policy reform to implement adaptation investment rules.",
        full_text="The government approved a climate finance policy reform to implement adaptation investment rules.",
        tags=[], discovered_date="2026-10-19", layer="event")
    values.update(kwargs)
    return normalize(Candidate(**values))


def html(title, body, published="2026-10-12", extra=""):
    return f'<html><head><meta property="article:published_time" content="{published}"></head><body><main><h1>{title}</h1><p>{body}</p>{extra}</main></body></html>'


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def pipeline(self, **config):
        return DiscoveryPipeline(DiscoveryConfig(evidence_requests=0, **config), date(2026, 10, 19), self.path, FixtureFetcher())

    def test_short_substantive_evidence_survives_without_source_cap(self):
        p = self.pipeline()
        for n in range(6):
            p._add(candidate(title=f"Adaptation policy reform {n}", url=f"https://agency.int/{n}",
                summary_hint=f"Government approves climate finance policy reform {n}.", full_text=""), "primary")
        self.assertEqual(len(p.evaluate()), 6)
        self.assertTrue(all(row["relevance_assessment"]["substantive"] for row in p.rows))

    def test_institution_names_and_negative_language_do_not_earn_priority(self):
        c = candidate(title="IPCC UNFCCC COP disappointing controversy", summary_hint="Famous people attended.", full_text="Famous people attended.")
        self.assertEqual(assess(c, "primary", date(2026, 10, 19))["score"], 0)
        positive = candidate(summary_hint="Government agreed climate finance policy reform.", full_text="Government agreed climate finance policy reform.")
        negative = replace(positive, summary_hint=positive.summary_hint.replace("agreed", "rejected"), full_text=positive.full_text.replace("agreed", "rejected"))
        self.assertEqual(assess(positive, "primary", date.today())["score"], assess(negative, "primary", date.today())["score"])

    def test_missing_publication_date_is_not_replaced_by_event_date(self):
        p = self.pipeline()
        p._add(candidate(published_date="", event_date="2026-10-12"), "primary")
        self.assertEqual(p.evaluate(), [])
        self.assertEqual(p.rows[0]["decision"], "insufficient_evidence")
        self.assertEqual(p.rows[0]["published_date"], "")

    def test_announcement_does_not_turn_into_outcome_after_event(self):
        p = self.pipeline()
        c = candidate(title="Agenda for climate finance dialogue", event_date="2026-10-12",
            summary_hint="Governments will discuss policy implementation under a previously adopted decision.",
            full_text="Governments will discuss policy implementation under a previously adopted decision.")
        self.assertEqual(c.development_stage, "scheduled")
        p._add(c, "primary")
        self.assertEqual(p.evaluate(), [])
        self.assertIn("announcement_only", p.rows[0]["exclusion_reason"])

    def test_upcoming_is_separate_optional_and_unknown_publication_allowed(self):
        p = self.pipeline(max_upcoming=1)
        p._add(candidate(title="Climate finance policy dialogue agenda", published_date="", event_date="2026-10-24",
                         full_text="Governments will discuss policy implementation.", summary_hint="Governments will discuss policy implementation."), "primary")
        self.assertEqual(p.evaluate(), [])
        self.assertEqual(len(p.upcoming_briefs()), 1)
        self.assertIn("not an outcome", p.upcoming_briefs()[0].one_sentence_en)

    def test_same_event_multiple_evidence_and_distinct_update_preserved(self):
        p = self.pipeline()
        first = candidate(event_name="International adaptation finance dialogue", event_date="2026-10-12")
        second = replace(first, url="https://journal.org/report", source_org="Journal")
        later = candidate(url="https://agency.int/update", published_date="2026-10-15", event_name=first.event_name,
            event_date=first.event_date, title="New implementation rules for climate adaptation fund",
            summary_hint="Government revised adaptation finance policy implementation rules.",
            full_text="Government revised adaptation finance policy implementation rules.")
        for c in (first, second, later):
            p._add(c, "primary")
        selected = p.evaluate()
        self.assertEqual(len(selected), 2)
        self.assertEqual(len({c.event_id for c in selected}), 1)
        self.assertTrue(any(len(c.evidence) == 2 for c in selected))
        self.assertEqual(sum(r["decision"] == "deduplication" for r in p.rows), 1)

    def test_canonical_urls_keep_meaningful_query_and_path_case(self):
        self.assertNotEqual(canonical_url("https://x.org/doc?id=1"), canonical_url("https://x.org/doc?id=2"))
        self.assertEqual(canonical_url("https://x.org/A?utm_source=mail&id=1#p"), "https://x.org/A?id=1")

    def test_late_report_and_future_version(self):
        p = self.pipeline()
        p._add(candidate(event_date="2026-09-10", published_date="2026-10-12"), "primary")
        p._add(candidate(url="https://agency.int/2", modified_date="2026-10-20"), "primary")
        self.assertEqual(len(p.evaluate()), 1)
        self.assertEqual(p.rows[1]["decision"], "outside_temporal_scope")

    def test_sent_url_can_return_only_with_verified_update(self):
        old = candidate(published_date="2026-09-01")
        p = self.pipeline()
        p.history[canonical_url(old.url)] = {"url": old.url, "fingerprint": old.content_fingerprint,
            "published_fingerprint": old.content_fingerprint, "published_versions": [old.content_fingerprint]}
        p._add(replace(old, title="Government revised climate finance policy implementation",
                       modified_date="2026-10-17", development_stage="subsequent_development"), "primary")
        self.assertEqual(len(p.evaluate({"sent_urls": [old.url]})), 1)
        self.assertEqual(p.rows[0]["temporal_basis"], "verified_modified_date_with_content_change")

    def test_no_date_conflicts_silently_resolved(self):
        p = DiscoveryPipeline(DiscoveryConfig(evidence_requests=1), date(2026, 10, 19), self.path,
            FixtureFetcher({"https://agency.int/news/1": html("Climate finance policy", "Government adopted a policy reform.", "2026-10-13")}))
        p._add(candidate(full_text=""), "primary")
        self.assertEqual(p.evaluate(), [])
        self.assertEqual(p.rows[0]["exclusion_reason"], "publication_date_conflict")

    def test_registry_validates_feed_and_expands_outside_seeds(self):
        root = "https://agency.int/"
        pages = {root: '<link rel="alternate" type="application/rss+xml" href="/feed"><a href="https://new.gov/news/policy">Climate policy report</a>',
                 root + "feed": "<html>not an RSS feed</html>",
                 "https://new.gov/news/policy": html("Climate finance policy reform", "Government adopted adaptation investment policy.")}
        p = DiscoveryPipeline(DiscoveryConfig(seeds=[{"name": "Agency", "url": root, "reliability": "primary"}]), date(2026, 10, 19), self.path, FixtureFetcher(pages))
        p.discover([])
        p.evaluate()
        self.assertFalse(p.registry[canonical_url(root + "feed")]["verified"])
        self.assertTrue(any(r["url"].startswith("https://new.gov") for r in p.rows))
        self.assertEqual(p.rows[0]["decision"], "insufficient_evidence")
        self.assertEqual(p.registry["https://new.gov/news/policy"]["reliability"], "unreviewed")

    def test_feed_parse_retains_undated_and_short_entries_and_audits_limit(self):
        feed = '<rss><channel>' + ''.join(f'<item><title>Climate policy {i}</title><link>https://agency.int/{i}</link><description>Policy adopted.</description></item>' for i in range(45)) + '</channel></rss>'
        rows, errors = parse_feed(feed, "https://agency.int/feed", {"name": "Agency"}, date.today(), 44)
        self.assertEqual(len(rows), 44)
        self.assertEqual(rows[0].published_date, "")
        self.assertEqual(len(errors), 1)

    def test_json_ld_and_cross_month_event_dates(self):
        page = '<main><h1>Climate policy dialogue</h1><p>30 Sep. - 02 Oct. 2026</p><p>The workshop was held to discuss climate governance policy.</p></main>'
        c, _, _ = parse_html(page, "https://agency.int/event/1", {"name": "Agency"}, date.today())
        self.assertEqual((c.event_date, c.event_end_date), ("2026-09-30", "2026-10-02"))
        self.assertEqual(c.published_date, "")
        self.assertEqual(c.development_stage, "completed")

    def test_final_diagnostics_reflect_actual_digest_and_draft_does_not_mark_sent(self):
        p = self.pipeline()
        p._add(candidate(), "primary")
        selected = p.evaluate()
        c = selected[0]
        d = Digest(date(2026, 10, 19), "Test", "", [], recent_news=[NewsBrief(c.title, c.source_org, c.published_date, c.url, "测试")])
        p.finalize(d)
        self.assertEqual(p.rows[0]["decision"], "selected_for_publication")
        self.assertNotIn("published_versions", p.history[canonical_url(c.url)])
        p.finalize(d, published=True)
        self.assertIn(c.content_fingerprint, p.history[canonical_url(c.url)]["published_versions"])
        p.save(self.path / "report.json")
        self.assertEqual(json.loads((self.path / "report.json").read_text())["status"], "published")

    def test_trace_distinguishes_unmonitored_and_bounded_miss(self):
        p = self.pipeline()
        self.assertEqual(p.trace(url="https://unknown.org/event")[0]["decision"], "source_not_monitored")
        p.registry["https://agency.int"] = {"url": "https://agency.int"}
        self.assertEqual(p.trace(url="https://agency.int/missed")[0]["decision"], "discovery_or_extraction_failure")

    def test_targeted_search_triggers_from_meetings_not_named_regressions(self):
        class SearchFetcher(FixtureFetcher):
            def get(self, url):
                if url.startswith("https://search.example/search?"):
                    self.calls.append(url)
                    return FetchResult(url, json.dumps({"results": [{"url": "https://agency.int/news/outcome"}]}), "application/json")
                return super().get(url)
        root = "https://agency.int/"
        pages = {root: '<a href="/news/meeting">Climate finance dialogue</a>',
                 root + "news/meeting": html("Climate finance policy dialogue", "Government convened a policy implementation dialogue."),
                 root + "news/outcome": html("Climate finance regulation adopted", "Government approved adaptation investment regulations.")}
        p = DiscoveryPipeline(DiscoveryConfig(seeds=[{"name": "Agency", "url": root, "reliability": "primary"}], search_url="https://search.example/search", max_searches=1), date(2026, 10, 19), self.path, SearchFetcher(pages))
        p.discover([])
        self.assertEqual(p.searches, 1)
        self.assertTrue(any(c.discovery_method == "targeted_search" for c in p.candidates))


class TransportTests(unittest.TestCase):
    def test_robots_denial_and_budget_include_policy_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            f = PublicFetcher(Path(directory))
            with patch.object(f, "_request", return_value=(200, "User-agent: *\nDisallow: /private", "text/plain")) as request:
                with self.assertRaisesRegex(FetchFailure, "robots_disallowed"):
                    f.get("https://agency.int/private/document")
                self.assertEqual(request.call_count, 1)

    def test_redirect_checks_target_robots_and_no_retry_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            f = PublicFetcher(Path(directory))
            def response(url, delay=None):
                return {
                    "https://agency.int/robots.txt": (200, "User-agent: *\nAllow: /", "text/plain"),
                    "https://agency.int/go": (302, "https://other.int/private", ""),
                    "https://other.int/robots.txt": (200, "User-agent: *\nDisallow: /", "text/plain"),
                }[url]
            with patch.object(f, "_request", side_effect=response) as request:
                with self.assertRaises(FetchFailure):
                    f.get("https://agency.int/go")
                self.assertEqual(request.call_count, 3)

    def test_private_network_and_credentials_rejected(self):
        with self.assertRaises(FetchFailure):
            PublicFetcher.validate_url("http://user:pass@example.org/")
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
            with self.assertRaises(FetchFailure):
                PublicFetcher.validate_url("http://internal.example/")

    def test_cache_does_not_bypass_robots_and_avoids_duplicate_network(self):
        with tempfile.TemporaryDirectory() as directory:
            f = PublicFetcher(Path(directory))
            with patch.object(f, "_request", side_effect=[(200, "User-agent: *\nAllow: /", "text/plain"), (200, "<main>Policy</main>", "text/html")]) as request:
                f.get("https://agency.int/page")
                self.assertTrue(f.get("https://agency.int/page").cached)
                self.assertEqual(request.call_count, 2)


class AdditionalEvidenceTests(unittest.TestCase):
    def test_feed_does_not_certify_unrelated_publisher(self):
        with tempfile.TemporaryDirectory() as directory:
            feed = '<rss><channel><item><title>Climate finance policy reform</title><link>https://unreviewed.org/news/1</link><pubDate>12 Oct 2026</pubDate><description>Government approved adaptation finance policy.</description></item></channel></rss>'
            p = DiscoveryPipeline(DiscoveryConfig(evidence_requests=0), date(2026, 10, 19), Path(directory), FixtureFetcher({"https://agency.int/feed": feed}))
            p.discover([Source("Agency", "international_org", "rss", ["agency.int"], [], "https://agency.int/feed", layer="event")])
            self.assertEqual(p.evaluate(), [])
            self.assertEqual(p.rows[0]["reliability"], "unreviewed")

    def test_institutional_subdomain_inherits_reviewed_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            p = DiscoveryPipeline(DiscoveryConfig(), date.today(), Path(directory), FixtureFetcher())
            p.registry_by_host["www.agency.int"] = {"name": "Agency", "reliability": "primary"}
            self.assertEqual(p._source_for("https://documents.agency.int/report", {}, "")['reliability'], "primary")
            self.assertEqual(p._source_for("https://agency.int.attacker.org/report", {}, "")['reliability'], "unreviewed")

    def test_meta_nofollow_and_link_nofollow_are_respected(self):
        page = '<head><meta name="robots" content="nofollow"></head><main><a href="/news/policy">Climate policy report</a></main>'
        self.assertEqual(parse_html(page, "https://agency.int/", {"name": "Agency"}, date.today())[2], [])
        page = '<main><a rel="nofollow" href="/news/policy">Climate policy report</a></main>'
        self.assertEqual(parse_html(page, "https://agency.int/", {"name": "Agency"}, date.today())[2], [])

    def test_metadata_only_document_does_not_support_substantive_outcomes(self):
        page = '<main><h5>Climate policy implementation report</h5><div>Publication date 12 Oct 2026</div><a href="/report.pdf">Open</a></main>'
        c, _, _ = parse_html(page, "https://agency.int/documents/1", {"name": "Agency", "reliability": "primary"}, date.today())
        self.assertEqual(c.text_source, "metadata_only")
        with tempfile.TemporaryDirectory() as directory:
            p = DiscoveryPipeline(DiscoveryConfig(evidence_requests=0), date(2026, 10, 19), Path(directory), FixtureFetcher())
            p._add(c, "primary")
            self.assertEqual(p.evaluate(), [])
            self.assertEqual(p.rows[0]["decision"], "insufficient_evidence")

    def test_invalid_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"selection_pool": 0}')
            with self.assertRaises(ValueError):
                DiscoveryConfig.load(path)

    def test_search_snippet_does_not_substitute_for_page_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            p = DiscoveryPipeline(DiscoveryConfig(), date.today(), Path(directory), FixtureFetcher())
            p.discover([], [{"url": "https://agency.int/news", "query": "climate finance reform", "snippet": "Government approved policy."}])
            self.assertEqual(p.evaluate(), [])
            self.assertTrue(any(e.get("reason") == "fixture_missing" for e in p.source_events))


class FinalBoundaryTests(unittest.TestCase):
    def test_cached_challenge_is_not_a_successful_page(self):
        import hashlib
        import time
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            url = "https://agency.int/news"
            (path / (hashlib.sha256(url.encode()).hexdigest() + ".json")).write_text(json.dumps({"url": url, "text": "<script src='/_Incapsula_Resource'></script>", "content_type": "text/html", "fetched_at": time.time(), "cached": False}))
            f = PublicFetcher(path)
            with patch.object(f, "_policy", return_value=0):
                with self.assertRaisesRegex(FetchFailure, "access_challenge"):
                    f.get(url)

    def test_headline_only_page_is_metadata_not_evidence(self):
        page = '<meta property="article:published_time" content="2026-10-12"><main><h1>Climate finance policy reform</h1></main>'
        c, _, _ = parse_html(page, "https://agency.int/news/1", {"name": "Agency"}, date(2026, 10, 19))
        self.assertEqual(c.text_source, "metadata_only")


if __name__ == "__main__":
    unittest.main()
