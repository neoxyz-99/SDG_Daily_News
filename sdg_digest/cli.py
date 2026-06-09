from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .archive import write_archive
from .collect import collect_candidates, deduplicate_candidates, rank_candidates
from .config import load_bibliography, load_sources
from .emailer import send_email
from .generate import filter_relevant_candidates, generate_digest
from .render import render_html

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
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-openai", action="store_true")
    args = parser.parse_args()

    run_date = date.fromisoformat(args.date)
    sources = load_sources(Path(args.sources))
    bibliography = load_bibliography(Path(args.bibliography))

    candidates = collect_candidates(sources, run_date, args.lookback_days)
    candidates = deduplicate_candidates(candidates)
    print(f"Collected {len(candidates)} candidate(s) after source and deduplication checks")
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
    archive_dir = write_archive(digest, args.output_dir)
    print(f"Archived digest to {archive_dir}")
    print(f"Selected {len(digest.items)} item(s)")

    if args.send_email and not args.dry_run:
        response = send_email(digest, render_html(digest))
        print(f"Sent email through Resend: {response.get('id', 'ok')}")
    else:
        print("Email sending skipped")


if __name__ == "__main__":
    main()
