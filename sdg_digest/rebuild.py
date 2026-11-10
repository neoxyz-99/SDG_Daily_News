"""Regenerate an archived issue into a separate preview; never imports the emailer."""
from __future__ import annotations

import argparse
from dataclasses import asdict, fields, replace
from datetime import date
import json
import os
from pathlib import Path

from .archive import write_archive
from .discovery_http import PublicFetcher, FetchFailure
from .discovery_parse import canonical_url, parse_html, parse_feed, normalize
from .editorial import load_editorial_history
from .generate import generate_digest
from .models import Candidate, DeepRead
from .quality import clean_source_text, validate_publication


def rebuild(run_date: date, seed_path: Path, output: Path):
    old = json.loads((Path("archive") / run_date.isoformat() / "digest.json").read_text())
    seeds = json.loads(seed_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    os.environ["GENERATION_DIAGNOSTICS_DIR"] = str(output / "drafts")
    fetcher = PublicFetcher(output / "http-cache", max_requests=120, per_host=30)
    candidates, failures, feed_cache = [], [], {}
    names = {f.name for f in fields(Candidate)}
    for seed in seeds:
        source = {"name": seed["source_org"], "type": seed["source_type"],
                  "layer": seed["layer"], "themes": seed["tags"], "reliability": "established_secondary"}
        base = Candidate(**{**{k:v for k,v in seed.items() if k in names}, "summary_hint": ""})
        candidate = None
        try:
            response = fetcher.get(seed["url"])
            parsed, _, _ = parse_html(response.text, response.url, source, run_date, "rebuild", seed["url"])
            if parsed and parsed.full_text:
                if parsed.modified_date > run_date.isoformat() or parsed.published_date > run_date.isoformat():
                    failures.append({"url": base.url, "reason": "page_updated_after_issue_date"})
                    continue
                candidate = replace(base, full_text=parsed.full_text, summary_hint=clean_source_text(parsed.summary_hint),
                                    text_source="html", modified_date=parsed.modified_date)
        except (FetchFailure, ValueError) as exc:
            failures.append({"url": base.url, "reason": str(exc)})
        if candidate is None and seed.get("discovery_method") == "feed":
            feed_url = seed["provenance_url"]
            if feed_url not in feed_cache:
                try:
                    entries, _ = parse_feed(fetcher.get(feed_url).text, feed_url, source, run_date, 500)
                    feed_cache[feed_url] = {canonical_url(c.url):c for c in entries}
                except (FetchFailure, ValueError):
                    feed_cache[feed_url] = {}
            entry = feed_cache[feed_url].get(canonical_url(base.url))
            if entry and entry.published_date <= run_date.isoformat():
                candidate = replace(base, summary_hint=clean_source_text(entry.summary_hint), text_source="rss")
        if candidate and (candidate.full_text or candidate.summary_hint):
            candidates.append(normalize(candidate))
    # Preserve verified paper identities and source abstracts, never the defective old notes.
    readings = [DeepRead(**{key: row[key] for key in (
        "title", "authors", "year", "url", "journal", "doi", "published_date", "kind", "tags", "abstract_en") if key in row})
        for row in old.get("classic_readings") or old.get("readings") or []]
    evidence = {"date": run_date.isoformat(), "candidates": [asdict(c) for c in candidates],
                "readings": [asdict(r) for r in readings], "failures": failures, "metrics": fetcher.metrics()}
    (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(f"Rebuild evidence: {len(candidates)} candidates, {sum(bool(c.full_text) for c in candidates)} with page text", flush=True)
    digest = generate_digest(candidates, {"pool": readings}, run_date, 5,
                             editorial_history=load_editorial_history("archive", run_date))
    validate_publication(digest)
    write_archive(digest, output / "archive")
    (output / "quality.json").write_text(json.dumps({"date": run_date.isoformat(), "status": "passed",
        "news": len(digest.recent_news), "signals": len(digest.research_signals),
        "readings": len(digest.readings), "email_sent": False}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--seeds", required=True, type=Path)
    parser.add_argument("--output", default="outputs/rebuild", type=Path)
    args = parser.parse_args()
    rebuild(date.fromisoformat(args.date), args.seeds, args.output)
