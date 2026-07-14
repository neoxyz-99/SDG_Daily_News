# SDG Weekly Compass

Daily editorial brief for climate policy, sustainable development, development finance, and global governance updates. The pipeline collects RSS/Atom feed entries from approved institutional sources, screens candidates with an AI relevance check, selects 3-5 policy-relevant news items, writes analytical editorial fields, pairs them with approved journal-article deep reads, sends an email through Resend, and stores Markdown, HTML, and JSON archives.

## Quick Start

1. Create a GitHub repository from this folder.
2. Add repository secrets:
   - `OPENAI_API_KEY`
   - `RESEND_API_KEY`
   - `DIGEST_TO_EMAIL`
   - `DIGEST_FROM_EMAIL`
3. Push to the default branch.
4. Run the workflow manually once from GitHub Actions with `send_email=false`.
5. After reviewing the generated archive, run again with `send_email=true`.

The scheduled workflow covers both Pacific daylight and standard time by registering 14:30 UTC and 15:30 UTC schedules, then running only the one that corresponds to 07:30 Pacific.

## Local Use

Dry run without email:

```powershell
python -m sdg_digest.cli --dry-run --lookback-days 3
```

Generate archives and send email:

```powershell
$env:OPENAI_API_KEY="..."
$env:RESEND_API_KEY="..."
$env:DIGEST_TO_EMAIL="you@example.com"
$env:DIGEST_FROM_EMAIL="Digest <digest@example.com>"
python -m sdg_digest.cli --send-email
```

Dry run that prints the generated brief without sending email or updating the sent-article record:

```powershell
python -m sdg_digest.cli --dry-run --skip-openai
```

## Output

Each run writes:

- `archive/YYYY-MM-DD/digest.json`
- `archive/YYYY-MM-DD/digest.md`
- `archive/YYYY-MM-DD/digest.html`
- `archive/index.json`
- `archive/index.html`

## Pipeline Logic

- `sources.yml` defines both the RSS/Atom source whitelist and the approved academic-journal list. Journal metadata is traced through Crossref by ISSN.
- Feed entries with fewer than 50 words in their official summary/description are skipped.
- Whitelisted institutional domains attempt full-text or executive-summary extraction before generation; HTTP 403, timeouts, or extraction failures fall back to the RSS summary.
- `sent_articles.json` stores previously sent URLs and paper-reading DOI history. News and research URLs are deduplicated across runs; paper readings use a five-issue cooldown so the same DOI is not repeatedly pushed.
- Keyword filters are not used as admission gates. Stage 1 only removes obvious structural noise, such as sports results, entertainment, celebrity items, product launches, or purely domestic election mechanics. An item is removed only when its title matches at least two exclusion patterns.
- Stage 2 uses semantic relevance scoring, not lexical topic matching. The filter model returns `score`, `domain`, and `reason`; items with score `2` pass, and score `1` items are kept if fewer than five items pass at score `2`.
- The semantic `domain` becomes an article classification tag, such as `#国际治理与多边主义`, `#发展与不平等`, `#环境治理与气候`, `#可持续金融与ESG`, or `#地缘政治与治理`.
- Tags are assigned after selection for archive classification only.
- News items are generated as editorial analysis: core argument, why now, agenda position, and post-selection tags.
- The daily editorial note is generated only when at least two news items are selected. It raises a core tension or open question rather than summarizing the issue.
- A weekly thread is generated only when at least two selected news items share a related agenda line.
- The paper-reading section uses one open candidate pool. Each run searches approved journals twice: a recent-publication window finds new work, while a topic query across older issues finds relevant classics. Both are screened against that week's agenda and enter the same selection process.
- `bibliography.yml` contains seven human-checked seed examples. They improve fallback quality and demonstrate the desired editorial depth, but they are not the boundary of the search and receive no automatic preference over dynamically traced papers.

## Notes

- If fewer than ten candidates pass relevance screening, the workflow logs a warning and continues with what is available.
- If the candidate pool is still below ten items after a seven-day lookback window, the workflow logs source-expansion suggestions instead of adding sources automatically.
- If fewer than five high-quality items are found, the digest is shorter rather than padded.
- Paper readings are linked through DOI metadata and selected only from results returned for the approved journal list or from the seven seed examples. New and historical papers are both eligible; the generated research directions provide search keywords rather than invented reading lists.
- GitHub Actions may occasionally delay scheduled runs during high-load windows; the workflow uses a non-hour time to reduce that risk.
