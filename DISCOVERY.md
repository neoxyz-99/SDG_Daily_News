# Event discovery and editorial diagnostics

The weekly workflow now explicitly chooses `discovery`; its manual selector also offers `legacy` for rollback. The bare CLI still defaults to `legacy` for compatibility with existing scripts. The release integrates this upgrade with the current main branch, preserving newer issue-title validation, citation verification, artwork checks and published issues. Existing academic tracing, bilingual generation, email, archives, sent history, and website generation remain in place. Default output remains at most 8 recent-news items, 5 research signals, and the existing 2 academic readings. Upcoming notices are disabled unless configured.

## Run and inspect

```sh
# No AI generation, academic queries, archive writes or email. Reports and HTTP cache are written.
python3 -m sdg_digest.cli --pipeline discovery --discovery-only --dry-run --date 2026-11-03

# Full bilingual draft using the existing OpenAI configuration; no archive/email writes.
python3 -m sdg_digest.cli --pipeline discovery --dry-run

# Existing publication command, explicitly choosing the upgraded pipeline.
python3 -m sdg_digest.cli --pipeline discovery --send-email

# Rollback: original source collection, filtering, caps and sent-URL behavior.
python3 -m sdg_digest.cli --pipeline legacy --dry-run

# Inspect saved decisions without making network requests.
python3 -m sdg_digest.diagnostics --report outputs/discovery/capture-replay/discovery.json --query IPCC

# Reproduce September–October retrospective metadata replay (offline, no secrets).
python3 -m sdg_digest.backtest

# Re-evaluate a locally retained capture with both pipelines (offline).
python3 -m sdg_digest.capture_replay --cache-dir data/discovery/live-state/cache --date 2026-11-03

python3 -m unittest discover -q
```

`--discovery-only` stops before title translation, academic collection, generation, archive writes and email. Without `--dry-run`, it saves source and event state but does not mark anything published. `--dry-run` writes a diagnostic report and disposable HTTP cache; it does not persist source/event state. As in the original CLI, a non-dry run without `--send-email` creates an archive. Archive publication marks event versions covered; email delivery still updates the existing sent-articles record only after successful sending.

Additional CLI flags:

| Flag | Default / purpose |
| --- | --- |
| `--pipeline` | `legacy` for bare CLI; workflow explicitly passes `discovery` |
| `--discovery-config` | Project-root `discovery.yml` (JSON-compatible YAML) |
| `--discovery-state` | Project-root `data/discovery/state` |
| `--diagnostics` | Project-root `outputs/discovery`; report filename is run date |
| `--search-results` | Optional JSON array containing `url` and `query`; snippets are never accepted as evidence |
| `--discovery-only` | Stop after candidate assessment |
| `--trace-url` | Explain a URL after the current live run; use the offline diagnostics module to avoid another crawl |

Legacy `--candidate-pool`, per-source caps and `--lookback-days` affect only legacy collection. Discovery uses its configuration below. Existing output maxima, academic lookback, model settings, and delivery flags retain their meanings. All defaults resolve against the project root, independently of working directory.

## Stages and evidence rules

1. **Ingest and discover.** Keep configured feeds and revisit verified registry endpoints and tracked developments. Start from institutional/secondary homepages, inspect advertised RSS/Atom, robots-declared sitemaps, structured metadata and topical HTML links. JSON Feed-compatible APIs are supported when supplied or discovered; API paths are not guessed. Endpoints become verified only after successful parsing. Empty valid feeds are valid sources; HTML returned by a supposed RSS endpoint is not.
2. **Normalize.** Keep original publisher publication dates, event dates and modified dates separate. Unknown publication dates remain blank. `sitemap lastmod`, search crawl times, discovery dates and event dates never become publication dates. Recognize metadata, JSON-LD, Atom/RSS dates, labelled document publication dates, and common event-date ranges.
3. **Assess all extracted candidates.** No per-publisher admission quota or minimum word count. Transparent rules score policy/governance mechanisms, topical scope, institutional implications, timing, source support and future implications. Institution names and conflict language receive no special bonus. This inexpensive first pass has explicit limitations below.
4. **Retrieve evidence.** Spend an explicit retrieval budget after assessment, prioritizing higher significance and primary sources. Prefer a page's source-reported date; contradictory feed/page dates are held for review. Publisher reliability and substantive evidence are separate checks. An attachment catalogue is not the attachment's content. PDF-only evidence is retained as a pointer and held when HTML does not substantiate the development.
5. **Consolidate events.** General session identifiers, structured event names/dates and conservative name matching associate sources. Canonical URLs preserve meaningful query parameters and path case. Merge duplicate document versions and reports of the same substantive update while retaining corroborating URLs. Different updates, dates or stages remain candidates. Previous publication fingerprints suppress repeated coverage across weeks and publishers. Changed content plus a source-reported modified date and a substantive update/outcome signal can reopen an already-sent URL.
6. **Compare the entire assessed pool.** Rank on significance; source diversity breaks ties without fixed country, topic or publisher quotas. A configured pool limit applies only after assessment, verification and duplicate handling. The existing AI editor sees the whole resulting pool (the old hidden 40-item slice is removed) and compares its evidence against prior issue context. The discovery path does not use legacy research-only AI screening or legacy two-per-source validation caps.
7. **Generate and account.** Retain bilingual news, research and reading modules. Optional upcoming notices are separate in Markdown, HTML, archive JSON and the website. Final decisions are reconciled with the actual generated issue, rather than treating an AI input candidate as published.

A scheduled notice never proves completion just because its date has passed. Upcoming notices may use a verified event date without a publication date, but are explicitly labelled as plans. A completed event with an unknown publication date is held rather than backdated. Late-published reports are timed by their publication date, even when the event occurred earlier.

## Configuration reference

All fields in `discovery.yml` are optional in code; the checked-in file sets these defaults. Unknown field names fail validation.

| Field | Default | Meaning |
| --- | ---: | --- |
| `rolling_days` | 21 | Inclusive rolling publication window; output length stays unchanged |
| `upcoming_days` | 14 | Future event horizon |
| `max_upcoming` | 0 | Optional separate notices; zero disables them |
| `max_requests` | 120 | Total actual HTTP attempts, including robots, redirects and evidence requests |
| `requests_per_host` | 30 | Host-level HTTP limit |
| `delay_seconds` | 1.5 | Minimum host interval; longer robots crawl-delay/request-rate wins |
| `timeout_seconds` | 15 | Timeout per network operation |
| `max_response_bytes` | 2000000 | Maximum streamed response body |
| `cache_hours` | 12 | Positive response reuse; robots are checked again each run |
| `max_depth` | 2 | Maximum link traversal depth after each root |
| `max_links_per_page` | 25 | Topical links/endpoints queued per page; skips are logged |
| `max_discovered_sources` | 12 | New external hosts per run; known institutional subdomains inherit reviewed publisher provenance |
| `max_feed_entries` | 500 | RSS/Atom safety bound, with skipped entries logged; no silent first-40 truncation |
| `evidence_requests` | 30 | Additional candidate-page retrieval attempts after relevance assessment, within HTTP budget |
| `selection_pool` | 60 | Maximum final editorial input after all candidates have been assessed |
| `relevance_threshold` | 4 | Minimum transparent rule score; supported scope and mechanism are also required |
| `state_retention_days` | 120 | Retention of tracked event pages and publication fingerprints |
| `search_url` | empty | Optional operator-provided SearXNG-compatible JSON endpoint; no service is provisioned |
| `max_searches` | 4 | Maximum targeted queries derived from discovered meetings/developments |
| `seeds` | Six requested entry sites | Objects with `name`, `url`, `reliability`, `themes`, optional `layer` |

Relevance weights are explicit in `assess()` rather than a learned score. Crawl, response, source, evidence and final-selection limits have distinct diagnostics. There is no automatic retry after 401/403/429 and no login/paywall/challenge bypass. Redirects receive their own public-address, robots and rate checks. Unavailable robots fail closed except an explicit 404. A required host wait longer than 60 seconds is deferred with a diagnostic instead of blocking the run. Meta/link `nofollow` is respected. Unsupported binary downloads are recorded, not silently read as text.

## Registry, search and continuity

`data/discovery/state/sources.json` records URL, publisher, source type, discovery method, provenance, reviewed reliability, themes, verification, last attempt, last successful fetch and last error. Verified means the endpoint parsed successfully, not that every claim is true. Previously successful endpoints retain their history when a later attempt fails.

A new external publisher is discoverable even if absent from `sources.yml`. A trusted site's outgoing link establishes provenance, not automatic reliability: new unrelated hosts are marked `unreviewed` and held at the evidence stage. Review publisher identity/editorial practice, then set its registry reliability to `primary` or `established_secondary`, or add a reviewed seed. This is a source review, not an event publication override. Links onto known institutional subdomains retain the institutional publisher. Do not add historical cases to production selection rules.

Search is optional. A connected search service was used interactively to locate historical evidence for this change; that connection is not a credential available to GitHub Actions. Runtime search can use an existing compatible endpoint via `search_url`, or import a JSON array:

```json
[{"url": "https://institution.example/event-page", "query": "institutional meeting policy outcomes"}]
```

Imported search results still undergo page retrieval, source review, temporal checks and relevance assessment. Search text alone never verifies an outcome. With no search endpoint, diagnostics explicitly report `live_search_not_configured`; homepage/feed/sitemap discovery still runs. No new paid service or deployment secret is required.

`events.json` retains event identity, document fingerprints, last-seen dates and versions actually published. Drafts do not mark candidates sent. Changed fingerprints alone do not prove a substantive update; an explicit update/outcome signal and source-reported modification date are also required. State is cached by the workflow using a new key per run; exact keys are not reused for writes. Raw publisher responses stay in ignored local cache directories and are not part of shareable diagnostics. Cache files are disposable and may be deleted to reclaim disk space.

## Diagnostics and interpretation

Each candidate records publisher/URL, discovery method and parent, original publication/event dates, event identity, stage, related document pointers, assessment dimensions/reason, verification status, selection decision and exclusion reason. Related pointers without an evidence record are not claimed to have been read. Diagnostic JSON omits reproduced article text; the extractor uses bounded text internally.

Decision categories are `source_not_monitored`, `discovery_or_extraction_failure`, `insufficient_evidence`, `outside_temporal_scope`, `deduplication`, `low_substantive_relevance`, `lower_editorial_priority`, and `selected_for_publication`. Source failures and unexplored links live in `source_events`, because a failed endpoint may yield no identifiable candidate. `status` distinguishes discovery-only, draft selection and publication. Lower editorial priority includes an explicit distinction between final-editor input and actual rejection. Final AI rejection records the fact that the editor did not choose an item; it does not invent a private model rationale.

An absent URL on a monitored host is a bounded-discovery miss, not proof that the event was irrelevant. A host not registered is a monitoring gap. Neither proves the cause of a historical omission without historical logs.

## Known limitations and rollout

- Rule-based initial relevance and event association are conservative heuristics, principally English with limited Chinese terms. They can miss implied relevance, multilingual paraphrases, or split/merge complex event identities incorrectly. Final AI judgment and review remain necessary. The score is an explainable screening aid, not a measured probability.
- A 21-day window captures delayed discovery and late reports, but cannot recover every old item or unobserved update on an undated page. HTML extraction lacks JavaScript execution. Binary/PDF document text, arbitrary proprietary APIs, compressed sitemap files and authentication are not implemented.
- New publisher review is intentional. Independent sources are preserved as evidence when duplicate reports merge, but the system does not automatically certify a newly encountered publisher by link count.
- The initial audit copy contained no historical RSS/HTTP snapshots or September–October run logs. The retrospective replay tests recoverability from a reviewed corpus, not real-world recall. Unknown dates are held, and historical facts are never forced into publication. See the audit report.
- The final AI model was not invoked during validation, and no email was sent. Existing model configuration/secrets are unchanged. Discovery AI cost is zero; a larger final evidence pool can increase generation cost. Character counts in diagnostics are workload proxies, not token invoices. Academic tracing and title translation retain their existing costs.
- After deployment, inspect source failures and several issues' final decisions. Choose `legacy` in a manual run or change the explicit workflow pipeline argument to roll back. The legacy path retains its original collector behavior, including its existing HTTP implementation.
