"""Reproducible retrospective replay; explicitly not a reconstructed live historical run."""
from __future__ import annotations

import argparse
import html
import json
import tempfile
import time
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from .collect import CollectionStats, collect_candidates, deduplicate_candidates, rank_candidates
from .config import load_sources
from .discovery import DiscoveryPipeline, write_json
from .discovery_config import DiscoveryConfig
from .discovery_http import FetchFailure, FetchResult
from .models import Digest, NewsBrief

ROOT = Path(__file__).resolve().parents[1]


class ReplayFetcher:
    def __init__(self, pages):
        self.pages, self.calls = pages, []
        self.sitemaps = {}

    def get(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise FetchFailure("not_in_replay_corpus")
        return FetchResult(url, self.pages[url])

    def metrics(self):
        return {"replayed_requests": len(self.calls), "http_requests": 0, "cache_hits": 0, "downloaded_bytes": 0}


def page(document):
    metadata = {"@type": "NewsArticle", "headline": document["title"], "datePublished": document["published_date"]}
    event = {"@type": "Event", "name": document["event_name"], "startDate": document["event_date"], "endDate": document.get("event_end_date", "")}
    links = ''.join(f'<a href="{html.escape(url)}">Related policy document</a>' for url in document.get("related_documents", []))
    prose = '' if document.get('metadata_only') else '<p>' + html.escape(document['text']) + '</p>'
    return '<html><head><script type="application/ld+json">' + json.dumps([metadata, event]) + '</script></head><body><main><h1>' + html.escape(document["title"]) + '</h1>' + prose + links + '</main></body></html>'


def replay_documents(documents, run_date, state_dir, sources):
    pages, seeds = {}, []
    for d in documents:
        pages[d["url"]] = page(d)
        origin = f"{urlsplit(d['url']).scheme}://{urlsplit(d['url']).netloc}/"
        if origin not in pages:
            pages[origin] = "<main>Reconstructed discovery index</main>"
            seeds.append({"name": d["publisher"], "url": origin, "reliability": d["reliability"]})
        pages[origin] += f'<a href="{html.escape(d["url"])}">Climate governance policy report</a>'
    cfg = DiscoveryConfig(seeds=seeds, evidence_requests=0, max_depth=1, max_upcoming=2)
    p = DiscoveryPipeline(cfg, run_date, state_dir, ReplayFetcher(pages))
    p.discover([])
    p.evaluate()
    # Deterministic offline editorial preview; no invented bilingual prose and no model call.
    news = [c for c in p.selected if c.layer == "event"][:8]
    digest = Digest(run_date, "Offline backtest selection", "", [], recent_news=[
        NewsBrief(c.title, c.source_org, c.published_date, c.url, "", c.summary_hint) for c in news], upcoming_events=p.upcoming_briefs())
    p.finalize(digest, published=True)
    # Counterfactual source-coverage baseline: place corpus records in a configured
    # publisher's feed only when its domain is already in sources.yml. These are NOT
    # observed historical feed entries; this cannot measure actual historical recall.
    feed_map = {}
    for source in sources:
        if source.strategy != "rss" or not source.url:
            continue
        records = [d for d in documents if any(urlsplit(d["url"]).hostname == host or urlsplit(d["url"]).hostname.endswith('.' + host) for host in source.allowed_domains)]
        feed_map[source.url] = '<rss><channel>' + ''.join(
            '<item><title>' + html.escape(d["title"]) + '</title><link>' + html.escape(d["url"]) + '</link><pubDate>' + d["published_date"] + '</pubDate><description>' + html.escape(d["text"]) + '</description></item>' for d in records) + '</channel></rss>'
    stats = CollectionStats()
    with patch("sdg_digest.collect.fetch_text", side_effect=lambda url: feed_map[url]), patch("sdg_digest.collect.extract_full_text", return_value=""), patch("sdg_digest.collect.time.sleep"):
        old = collect_candidates(sources, run_date, 7, stats)
    old_unique = deduplicate_candidates(old)
    old_ranked = rank_candidates(old_unique, 30, max_per_source=2, fill_to_max=False)
    return p, {"candidate_count": len(old), "deduplicated_count": len(old_unique),
        "generation_pool_size": len(old_ranked), "publishers": sorted({c.source_org for c in old}),
        "urls": [c.url for c in old], "simulated_feed_requests": len(feed_map),
        "http_requests": 0, "ai_calls": 0, "rss_items_fetched": stats.rss_items_fetched}


def run_backtest(corpus_path, output_dir):
    corpus = json.loads(Path(corpus_path).read_text())
    sources = load_sources(ROOT / "sources.yml")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    weeks = [date(2026, 9, 7) + timedelta(days=7 * i) for i in range(8)] + [date(2026, 10, 31)]
    results, recovered, old_recovered = [], set(), set()
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory)
        for day in weeks:
            docs = [d for d in corpus["documents"] if d["published_date"] and d["published_date"] <= day.isoformat()]
            p, old = replay_documents(docs, day, state, sources)
            p.save(out / f"{day}.json")
            urls = {row["url"] for row in p.rows}
            for d in docs:
                if d["url"] in urls:
                    recovered.update(d["case_ids"])
                if d["url"] in old["urls"]:
                    old_recovered.update(d["case_ids"])
            results.append({"week": day.isoformat(), "new": p.report()["metrics"],
                            "new_decisions": p.report()["decisions"], "legacy_counterfactual": old})
        # Unknown dates are inspected at observation time, never injected into a prior week.
        observation, _ = replay_documents(corpus["documents"], date.fromisoformat(corpus["observed_at"]), state / "observation", sources)
        observation.save(out / "undated-observation.json", persist=False)
    all_urls = {row["url"] for row in observation.rows}
    covered = sorted({case for d in corpus["documents"] if d["url"] in all_urls for case in d["case_ids"]})
    decisions = {row["url"]: {"decision": row["decision"], "reason": row["exclusion_reason"],
        "stage": row["development_stage"], "event_id": row["event_id"], "score": row["relevance_assessment"].get("score")}
        for row in observation.rows}
    result = {"period": ["2026-09-01", "2026-10-31"], "kind": "retrospective_curated_replay",
        "limitations": corpus["limitations"], "weeks": results,
        "regression_case_discovery": {"reviewed_corpus": covered, "dated_replay": sorted(recovered),
            "legacy_configured_domain_counterfactual": sorted(old_recovered), "case_count": len(corpus["cases"])},
        "case_decisions": [{"url": d["url"], "cases": d["case_ids"], "publication_date": d["published_date"],
                            **decisions.get(d["url"], {"decision": "not_discovered"})} for d in corpus["documents"]],
        "unmeasurable_historical_metrics": {"production_important_event_recall": None,
            "production_irrelevant_candidate_volume": None, "production_duplicate_rate": None,
            "production_source_diversity": None, "billed_api_cost": None},
        "replay_cost": {"http_requests": 0, "ai_calls": 0, "paid_services": 0,
                        "elapsed_seconds": round(time.perf_counter() - start, 3)}}
    write_json(out / "comparison.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(ROOT / "data/discovery/historical_cases.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "outputs/discovery/backtest-2026-09-10"))
    args = parser.parse_args()
    result = run_backtest(args.corpus, args.output_dir)
    print(json.dumps({"regression_case_discovery": result["regression_case_discovery"], "replay_cost": result["replay_cost"],
                      "output": str(Path(args.output_dir) / "comparison.json")}, indent=2))


if __name__ == "__main__":
    main()
