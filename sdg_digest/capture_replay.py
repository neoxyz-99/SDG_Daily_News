"""Compare both collectors on previously captured responses, with no network or AI."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from .collect import (CollectionStats, _clean_text, _find_summary_element_text, _first_words,
                      collect_candidates, deduplicate_candidates, rank_candidates)
from .config import load_sources
from .discovery import DiscoveryPipeline, assess, write_json
from .discovery_config import DiscoveryConfig
from .discovery_http import FetchFailure, FetchResult
from .generate import filter_relevant_candidates, is_recent_news_candidate

ROOT = Path(__file__).resolve().parents[1]


class CaptureFetcher:
    def __init__(self, cache_dir):
        self.cache_dir, self.calls = Path(cache_dir), []
        self.sitemaps = {}

    def get(self, url):
        self.calls.append(url)
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache_dir / (key + ".json")
        if not path.exists():
            raise FetchFailure("response_not_captured")
        data = json.loads(path.read_text())
        if any(m in data["text"].lower() for m in ("_incapsula_resource", "cf-chl-", "captcha")):
            raise FetchFailure("access_challenge")
        return FetchResult(**data)

    def metrics(self):
        return {"http_requests": 0, "captured_response_lookups": len(self.calls), "cache_hits": 0, "downloaded_bytes": 0}


def replay(cache_dir, run_date, output_dir):
    sources = load_sources(ROOT / "sources.yml")
    fetcher = CaptureFetcher(cache_dir)
    out = Path(output_dir)
    p = DiscoveryPipeline(DiscoveryConfig.load(ROOT / "discovery.yml"), run_date, out / "isolated-state", fetcher)
    p.discover(sources)
    p.evaluate()
    p.save(out / "discovery.json", persist=False)
    def old_extract(url):
        soup = BeautifulSoup(fetcher.get(url).text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        summary = _find_summary_element_text(soup)
        container = soup.find("article") or soup.find("main")
        return summary or (_first_words(_clean_text(container.get_text(" ")), 400) if container else "")
    stats = CollectionStats()
    with contextlib.redirect_stdout(io.StringIO()), patch("sdg_digest.collect.fetch_text", side_effect=lambda url: fetcher.get(url).text), patch("sdg_digest.collect.extract_full_text", side_effect=old_extract), patch("sdg_digest.collect.time.sleep"):
        old_raw = collect_candidates(sources, run_date, 7, stats)
        old_unique = deduplicate_candidates(old_raw)
        old_relevant = filter_relevant_candidates(old_unique, use_openai=False)
    old_selected = []
    for recent in (True, False):
        old_selected += rank_candidates([c for c in old_relevant if is_recent_news_candidate(c) == recent], 30, max_per_source=2, fill_to_max=False)
    new_unique = [r for r in p.rows if r["decision"] != "deduplication"]
    result = {
        "kind": "current_captured_response_comparison", "run_date": run_date.isoformat(),
        "limitations": ["This is a November capture comparison, not historical September/October recall.",
            "Missing captures are failures, not evidence of no articles. Raw responses remain local disposable cache.",
            "Legacy uses its existing seven-day window and new uses 21 days; both compare discovery-only pools, without AI generation.",
            "Low-substance counts are rule-screening measurements, not human-labelled false positives or precision.",
            "Sitemaps supplied only by robots.txt are absent from this offline replay; the live report records their traversal."],
        "legacy": {"candidate_count": len(old_raw), "distinct_publishers": len({c.source_org for c in old_raw}),
            "duplicates_removed": len(old_raw) - len(old_unique),
            "duplicate_rate": (len(old_raw) - len(old_unique)) / len(old_raw) if old_raw else None,
            "rule_flagged_low_substance": sum(not assess(c, "established_secondary", run_date)["substantive"] for c in old_raw),
            "generation_pool_size": len(old_selected), "generation_input_characters": sum(len(c.title+c.summary_hint+c.full_text) for c in old_selected),
            "generation_pool_urls": [c.url for c in old_selected]},
        "discovery": {"candidate_count": len(p.rows), "distinct_publishers": len({r["source_org"] for r in p.rows}),
            "duplicates_removed": len(p.rows) - len(new_unique),
            "duplicate_rate": (len(p.rows) - len(new_unique)) / len(p.rows) if p.rows else None,
            "rule_flagged_low_substance": sum(r["decision"] == "low_substantive_relevance" for r in p.rows),
            "generation_pool_size": len(p.selected), "generation_input_characters": sum(len(c.title+c.summary_hint+c.full_text) for c in p.selected),
            "generation_pool_urls": [c.url for c in p.selected], "decisions": p.report()["decisions"]},
        "cost": {"network_requests": 0, "ai_calls": 0, "billed_api_cost": 0,
                 "note": "Replay only; original live HTTP costs are in live/summary.json. Character counts are workload proxies, not token bills."},
    }
    write_json(out / "comparison.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output-dir", default=str(ROOT / "outputs/discovery/capture-replay"))
    args = parser.parse_args()
    result = replay(args.cache_dir, date.fromisoformat(args.date), args.output_dir)
    print(json.dumps({k: {key: value for key, value in v.items() if key != "generation_pool_urls"} for k, v in result.items() if k in {"legacy", "discovery", "cost"}}, indent=2))


if __name__ == "__main__":
    main()
