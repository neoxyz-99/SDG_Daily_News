# The Governance Brief

Daily bilingual governance digest for climate policy, sustainable development, development finance, and global governance updates. The pipeline collects RSS/Atom feed entries from approved institutional sources, screens candidates with an AI relevance check, summarizes 3-5 selected news items, pairs them with approved journal-article deep reads, sends an email through Resend, and stores Markdown, HTML, and JSON archives.

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

## Output

Each run writes:

- `archive/YYYY-MM-DD/digest.json`
- `archive/YYYY-MM-DD/digest.md`
- `archive/YYYY-MM-DD/digest.html`
- `archive/index.json`
- `archive/index.html`

## Pipeline Logic

- `sources.yml` defines the RSS/Atom source whitelist and allowed item domains.
- Feed entries with fewer than 50 words in their official summary/description are skipped instead of falling back to webpage crawling.
- Keyword filters are not used as admission gates. Candidate relevance is checked by the model with a yes/no policy-substance question.
- Tags are assigned after selection for archive classification only.
- `bibliography.yml` defines approved deep reads from selected journals. The model may select from this file and write a short "why it matters today" sentence, but it does not rewrite the human-written prose brief, methodology note, or further-reading entries.
- The newsletter header uses a model-written Chinese theme sentence of at most 40 characters when news items are present.

## Notes

- If fewer than ten candidates pass relevance screening, the workflow logs a warning and continues with what is available.
- If the candidate pool is still below ten items after a seven-day lookback window, the workflow logs source-expansion suggestions instead of adding sources automatically.
- If fewer than five high-quality items are found, the digest is shorter rather than padded.
- Deep reads are linked through DOI metadata and selected only from the approved bibliography. Missing `further_reading` entries are logged for manual follow-up.
- GitHub Actions may occasionally delay scheduled runs during high-load windows; the workflow uses a non-hour time to reduce that risk.
