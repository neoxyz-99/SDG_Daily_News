from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .archive import write_archive
from .collect import CollectionStats, collect_candidates, deduplicate_candidates, rank_candidates
from .config import load_bibliography, load_sources
from .emailer import send_email
from .generate import filter_relevant_candidates, generate_digest
from .render import render_html, render_markdown
from .sent_articles import filter_sent_candidates, load_sent_articles, update_sent_articles

SOURCE_SUGGESTIONS = [
    "World Resources Institute RSS (institutional policy research; climate and development)",
    "World Bank Blogs RSS (international organization; development finance and climate policy)",
    "Brookings RSS by topic (registered policy research center; global development and governance)",
    "Nature Climate Change RSS (academic journal; peer review; climate policy and science)",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate The Governance Brief")
    parser.add_argument("--date", default=date.today().isoformat(), help="Run date in YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--candidate-pool", type=int, default=30)
    parser.add_argument("--sources", default="sources.yml")
    parser.add_argument("--bibliography", default="bibliography.yml")
    parser.add_argument("--output-dir", default="archive")
    parser.add_argument("--sent-articles", default="sent_articles.json")
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-openai", action="store_true")
    args = parser.parse_args()

    run_date = date.fromisoformat(args.date)
    sources = load_sources(Path(args.sources))
    bibliography = load_bibliography(Path(args.bibliography))
    sent_record = load_sent_articles(Path(args.sent_articles))

    stats = CollectionStats()
    candidates = collect_candidates(sources, run_date, args.lookback_days, stats=stats)
    candidates = deduplicate_candidates(candidates)
    before_sent_filter = len(candidates)
    candidates, filtered_by_sent = filter_sent_candidates(candidates, sent_record)
    print(f"Collected {len(candidates)} candidate(s) after source, run-level deduplication, and sent-history checks")
    candidates = filter_relevant_candidates(candidates, use_openai=not args.skip_openai)
    print(f"{len(candidates)} candidate(s) passed AI relevance check")
    if args.lookback_days >= 7 and len(candidates) < 10:
        print("Source expansion suggestion: fewer than 10 relevant candidates after a 7-day window.")
        print("Consider adding RSS/Atom feeds that meet the source policy criteria:")
        for suggestion in SOURCE_SUGGESTIONS:
            print(f"- {suggestion}")
    selected = rank_candidates(candidates, args.candidate_pool)
    digest = generate_digest(
        selected,
        bibliography,
        run_date,
        max_items=args.max_items,
        use_openai=not args.skip_openai,
    )
    if args.dry_run:
        print(render_markdown(digest))
    else:
        archive_dir = write_archive(digest, args.output_dir)
        print(f"Archived digest to {archive_dir}")
    print(f"Selected {len(digest.items)} item(s)")

    if args.send_email and not args.dry_run:
        response = send_email(digest, render_html(digest))
        print(f"Sent email through Resend: {response.get('id', 'ok')}")
        update_sent_articles(digest, run_date, Path(args.sent_articles))
        print(f"Updated sent articles record: {args.sent_articles}")
    else:
        print("Email sending skipped")
    _print_dry_run_summary(
        stats=stats,
        filtered_by_sent=filtered_by_sent,
        before_sent_filter=before_sent_filter,
        passed_to_ai=len(selected),
    )


def _print_dry_run_summary(
    stats: CollectionStats,
    filtered_by_sent: int,
    before_sent_filter: int,
    passed_to_ai: int,
) -> None:
    print("")
    print("Dry run summary")
    print(f"- Number of RSS items fetched: {stats.rss_items_fetched}")
    print(f"- Number filtered by persistent deduplication: {filtered_by_sent} of {before_sent_filter}")
    print(f"- Number passed to AI: {passed_to_ai}")
    print(f"- Sources using full-text extraction: {', '.join(sorted(stats.full_text_sources)) or 'none'}")
    print(f"- Sources using RSS fallback: {', '.join(sorted(stats.rss_fallback_sources)) or 'none'}")
    if stats.full_text_failures:
        print("- Full-text extraction failures:")
        for failure in stats.full_text_failures:
            print(f"  - {failure}")


# CHANGE 1 DONE: CLI loads sent history, filters old URLs, and updates it only after successful email sends.
# CHANGE 2 DONE: CLI reports full-text extraction vs RSS fallback sources in the run summary.


if __name__ == "__main__":
    main()
