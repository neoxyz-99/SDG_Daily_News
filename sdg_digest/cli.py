from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import json
from datetime import date
from pathlib import Path

from .academic import collect_academic_readings, combine_academic_pool, verify_curated_readings
from .archive import write_archive
from .collect import CollectionStats, collect_candidates, deduplicate_candidates, rank_candidates
from .config import load_bibliography, load_sources
from .emailer import send_email
from .editorial import load_editorial_history
from .generate import filter_relevant_candidates, generate_digest, is_recent_news_candidate
from .render import render_html, render_markdown
from .sent_articles import filter_sent_candidates, load_sent_articles, update_sent_articles
from .titles import translate_candidate_titles

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_SUGGESTIONS = [
    "World Resources Institute RSS (institutional policy research; climate and development)",
    "World Bank Blogs RSS (international organization; development finance and climate policy)",
    "Brookings RSS by topic (registered policy research center; global development and governance)",
    "Nature Climate Change RSS (academic journal; peer review; climate policy and science)",
    "E3G RSS (institutional policy research; climate diplomacy and energy transition)",
    "Center for Global Development RSS (registered policy research center; development finance)",
    "VoxDev RSS (academic policy platform; development economics)",
    "CEPR RSS (academic policy research network; political economy and development)",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SDG Weekly Compass")
    parser.add_argument("--date", default=date.today().isoformat(), help="Run date in YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument(
        "--academic-lookback-days",
        type=int,
        default=90,
        help="Recent-publication window for journal tracing; older matches remain eligible as classics",
    )
    parser.add_argument("--max-items", type=int, default=5, help="Backward-compatible alias for research signals")
    parser.add_argument("--max-recent-news", type=int, default=8)
    parser.add_argument("--max-research-signals", type=int, default=None)
    parser.add_argument("--max-per-source-recent", type=int, default=2)
    parser.add_argument("--max-per-source-research", type=int, default=2)
    parser.add_argument("--candidate-pool", type=int, default=30)
    parser.add_argument("--sources", default=str(PROJECT_ROOT / "sources.yml"))
    parser.add_argument("--bibliography", default=str(PROJECT_ROOT / "bibliography.yml"))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "archive"))
    parser.add_argument("--sent-articles", default=str(PROJECT_ROOT / "sent_articles.json"))
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-openai", action="store_true")
    parser.add_argument("--pipeline", choices=("legacy", "discovery"), default="legacy")
    parser.add_argument("--discovery-config", default=str(PROJECT_ROOT / "discovery.yml"))
    parser.add_argument("--discovery-state", default=str(PROJECT_ROOT / "data/discovery/state"))
    parser.add_argument("--diagnostics", default=str(PROJECT_ROOT / "outputs/discovery"))
    parser.add_argument("--search-results", help="JSON array of search results: url and query; page evidence is fetched independently")
    parser.add_argument("--discovery-only", action="store_true", help="Collect and assess without AI, archive or email")
    parser.add_argument("--trace-url", default="", help="Explain why a known URL was omitted")
    args = parser.parse_args()
    if args.discovery_only and args.pipeline != "discovery":
        parser.error("--discovery-only requires --pipeline discovery")

    run_date = date.fromisoformat(args.date)
    sources = load_sources(Path(args.sources))
    sample_readings = load_bibliography(Path(args.bibliography))
    sent_record = load_sent_articles(Path(args.sent_articles))

    stats = CollectionStats()
    discovery = None
    if args.pipeline == "discovery":
        from .discovery import DiscoveryPipeline
        from .discovery_config import DiscoveryConfig
        discovery = DiscoveryPipeline(DiscoveryConfig.load(args.discovery_config), run_date, Path(args.discovery_state))
        imported = json.loads(Path(args.search_results).read_text()) if args.search_results else []
        discovery.discover(sources, imported)
        selected = discovery.evaluate(sent_record)
        candidates = selected
        before_sent_filter, filtered_by_sent = len(discovery.rows), 0
        selected_recent = [c for c in selected if is_recent_news_candidate(c)]
        selected_research = [c for c in selected if not is_recent_news_candidate(c)]
        report_path = Path(args.diagnostics) / f"{run_date.isoformat()}.json"
        discovery.save(report_path, persist=not args.dry_run)
        print(f"Discovery assessed {len(discovery.rows)} documents; {len(selected)} passed to editorial selection. Report: {report_path}")
        if args.trace_url:
            print(json.dumps(discovery.trace(url=args.trace_url), ensure_ascii=False, indent=2))
        if args.discovery_only:
            return
    else:
        candidates = collect_candidates(sources, run_date, args.lookback_days, stats=stats)
        candidates = deduplicate_candidates(candidates)
        before_sent_filter = len(candidates)
        candidates, filtered_by_sent = filter_sent_candidates(candidates, sent_record)
        print(f"Collected {len(candidates)} candidate(s) after source, run-level deduplication, and sent-history checks")
        candidates = filter_relevant_candidates(candidates, use_openai=not args.skip_openai)
        recent_candidates = [candidate for candidate in candidates if is_recent_news_candidate(candidate)]
        research_candidates = [candidate for candidate in candidates if not is_recent_news_candidate(candidate)]
        print(
            f"{len(recent_candidates)} recent-news candidate(s) and "
            f"{len(research_candidates)} research candidate(s) remain after filtering"
        )
        if args.lookback_days >= 7 and len(candidates) < 10:
            print("Source expansion suggestion: fewer than 10 relevant candidates after a 7-day window.")
            print("Consider adding RSS/Atom feeds that meet the source policy criteria:")
            for suggestion in SOURCE_SUGGESTIONS:
                print(f"- {suggestion}")
        selected_recent = rank_candidates(
            recent_candidates,
            max(args.candidate_pool, args.max_recent_news),
            max_per_source=args.max_per_source_recent,
            fill_to_max=False,
        )
        selected_research = rank_candidates(
            research_candidates,
            args.candidate_pool,
            max_per_source=args.max_per_source_research,
            fill_to_max=False,
        )
        selected = selected_recent + selected_research
    if not args.skip_openai:
        selected = translate_candidate_titles(selected)
    tracked_readings = collect_academic_readings(
        sources,
        selected,
        run_date,
        lookback_days=args.academic_lookback_days,
    )
    if not (args.skip_openai and args.dry_run):
        sample_readings = verify_curated_readings(sample_readings)
    academic_pool = combine_academic_pool(tracked_readings, sample_readings)
    digest = generate_digest(
        selected,
        academic_pool,
        run_date,
        max_items=args.max_items,
        use_openai=not args.skip_openai,
        max_recent_news=args.max_recent_news,
        max_research_signals=args.max_research_signals or args.max_items,
        classic_reading_history=sent_record.get("classic_reading_history", []),
        sent_reading_dois=sent_record.get("classic_reading_dois", []),
        editorial_history=load_editorial_history(args.output_dir, run_date),
    )
    if discovery:
        if not args.skip_openai and discovery.config.max_upcoming:
            discovery.upcoming = translate_candidate_titles(discovery.upcoming_candidates())
        digest = replace(digest, upcoming_events=discovery.upcoming_briefs())
        discovery.finalize(digest)
        discovery.save(report_path, persist=not args.dry_run)
    if args.dry_run:
        print(render_markdown(digest))
    else:
        archive_dir = write_archive(digest, args.output_dir)
        print(f"Archived digest to {archive_dir}")
    print(
        f"Selected {len(digest.recent_news)} recent-news item(s), "
        f"{len(digest.research_signals or digest.items)} research signal(s), "
        f"and {len(digest.classic_readings or digest.readings)} research reading(s)"
    )

    if args.send_email and not args.dry_run:
        response = send_email(digest, render_html(digest))
        print(f"Sent email through Resend: {response.get('id', 'ok')}")
        update_sent_articles(digest, run_date, Path(args.sent_articles))
        print(f"Updated sent articles record: {args.sent_articles}")
    else:
        print("Email sending skipped")
    if discovery:
        discovery.finalize(digest, published=not args.dry_run)
        discovery.save(report_path, persist=not args.dry_run)
    if not discovery:
        _print_pipeline_report(
            stats=stats,
            filtered_by_sent=filtered_by_sent,
            before_sent_filter=before_sent_filter,
            passed_to_ai=len(selected),
            recent_candidates=len(selected_recent),
            research_candidates=len(selected_research),
            selected_recent_sources=_source_counts(selected_recent),
            selected_research_sources=_source_counts(selected_research),
        )


def _print_pipeline_report(
    stats: CollectionStats,
    filtered_by_sent: int,
    before_sent_filter: int,
    passed_to_ai: int,
    recent_candidates: int,
    research_candidates: int,
    selected_recent_sources: Counter[str],
    selected_research_sources: Counter[str],
) -> None:
    print("")
    print("Pipeline diagnostic report")
    print(f"- Number of RSS items fetched: {stats.rss_items_fetched}")
    print(f"- Number after text availability check: {stats.rss_items_after_text_check}")
    print(f"- Number after date/domain check: {stats.rss_items_after_date_domain_check}")
    print(f"- Number skipped for too little text: {stats.short_text_skips}")
    print(f"- Number filtered by persistent deduplication: {filtered_by_sent} of {before_sent_filter}")
    print(f"- Number passed to AI: {passed_to_ai}")
    print(f"- Recent-news candidates passed to AI: {recent_candidates}")
    print(f"- Research candidates passed to AI: {research_candidates}")
    print(f"- Selected recent-news source mix: {_format_source_counts(selected_recent_sources)}")
    print(f"- Selected research source mix: {_format_source_counts(selected_research_sources)}")
    print(f"- Sources using full-text extraction: {', '.join(sorted(stats.full_text_sources)) or 'none'}")
    print(f"- Sources using RSS fallback: {', '.join(sorted(stats.rss_fallback_sources)) or 'none'}")
    if stats.source_items_fetched:
        print("- Source breakdown:")
        for source_name in sorted(stats.source_items_fetched):
            fetched = stats.source_items_fetched[source_name]
            after_text = stats.source_items_after_text_check.get(source_name, 0)
            print(f"  - {source_name}: fetched {fetched}, after text check {after_text}")
    if stats.full_text_failures:
        print("- Full-text extraction failures:")
        for failure in stats.full_text_failures:
            print(f"  - {failure}")


def _source_counts(candidates) -> Counter[str]:
    return Counter(candidate.source_org for candidate in candidates)


def _format_source_counts(counts: Counter[str]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{source}={count}" for source, count in counts.most_common())


# CHANGE 1 DONE: CLI loads sent history, filters old URLs, and updates it only after successful email sends.
# CHANGE 2 DONE: CLI reports full-text extraction vs RSS fallback sources in the run summary.
# WEEKLY MODULE ROUTING DONE: CLI now defaults to a 7-day window and sends separate recent-news/research pools to generation.
# PIPELINE LOGGING DONE: CLI prints a source-level diagnostic report for every run.
# SOURCE DIVERSITY DONE: CLI applies per-source caps before passing candidates to the AI selector.


if __name__ == "__main__":
    main()
