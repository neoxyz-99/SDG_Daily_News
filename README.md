# SDG / ESG / Climate Finance Daily Digest

Daily automated digest for SDG, ESG, and climate finance updates. The pipeline gathers trusted-source candidates, ranks 5-8 items, generates Chinese summaries with English titles, sends an email through Resend, and stores Markdown, HTML, and JSON archives.

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

## Configuration

- `sources.yml` defines trusted sources, allowed domains, tags, and fetch strategy.
- `bibliography.yml` defines approved classic readings by topic tag. Deep reads are selected from this file, not invented by the model.

## Notes

- If fewer than five high-quality items are found, the digest is shorter rather than padded.
- Paywalled academic content is linked through DOI or publisher metadata when full text is unavailable.
- GitHub Actions may occasionally delay scheduled runs during high-load windows; the workflow uses a non-hour time to reduce that risk.
