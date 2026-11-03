# SDG Weekly Compass discovery audit and backtest

Review date: 2026-11-03. Scope: the local working tree supplied for this task, including its pre-existing uncommitted changes. This is not a claim about which revision was deployed during September or October.

## Findings and implemented changes

| Observed legacy mechanism | Why it can omit substantive developments | New behavior |
| --- | --- | --- |
| `collect_candidates` only handles configured RSS strategies | No direct UNFCCC/IPCC/calendar/document discovery; ENB has no dedicated configured source | Six initial entry sites, verified feeds, HTML/metadata/sitemap/API discovery, optional targeted search, external-source registry |
| `_collect_rss` uses `entries[:40]` | A busy feed can lose relevant items before relevance assessment | Configurable 500-entry safety bound with explicit skip records |
| Minimum research content, full-text host whitelist | A brief institutional notice can disappear before substantive evaluation | No minimum word-count admission rule; retrieve evidence after preliminary assessment |
| Missing/malformed dates fall back to the run date | Undated older material may appear recent; not an explanation of omission, but a temporal accuracy defect | Unknown publication dates stay unknown; event and modification dates remain separate |
| Research-only semantic prompt asks for arguments/findings; event sources bypass domain assessment | Governance procedure may be undervalued as research, while irrelevant news can survive | Broad policy/governance assessment applies to all discovered candidates |
| CLI applies two-per-source limits before final editing | Strong developments can lose to other items from the same publisher before comparison | Soft diversity preference after assessment; no fixed topic/country/publisher admission quota |
| Generation silently slices pools to 40 per module | Admitted candidates can never reach the editor without a corresponding decision record | No hidden generation slice; explicit configured post-assessment pool |
| URL-only persistent sent history and title-similarity deduplication | Updated pages can be permanently excluded; multiple reports cannot form an evidence trail | Event identity, stages, document/version fingerprints and related evidence; verified updates can re-enter |
| Console aggregate counts only | A missing event cannot be traced to a candidate-level reason | Saved candidate decisions, source failures, unexplored-link reasons, offline URL/event tracing |

The legacy path remains available. Its original collector and sent-article module are unchanged. New scheduling explicitly uses discovery in the local workflow; the bare CLI keeps its original default for compatibility. The initial audit did not deploy or send email. The subsequent release preserves current main-branch features, rebuilds the site from its latest existing archive, and publishes the upgrade without sending email or changing API secrets.

## What the historical evidence supports

The initial local audit copy’s archive ended on August 10; the release was subsequently integrated onto the current main branch, preserving its later issues through November 2. No September–October feed snapshots, crawler responses, generation inputs or execution logs were present. Therefore this audit identifies *mechanisms that can cause omissions*, not a proven stage-by-stage cause for every historical missing event.

Reviewed sources and date handling:

- **IPCC-65 / AR7:** [ENB's meeting report](https://enb.iisd.org/intergovernmental-panel-climate-change-ipcc-65-summary) describes the unresolved timetable/budget and suspension. Its original publication date was not established, so it is not backdated to the meeting. [Japan's environment ministry announcement](https://www.env.go.jp/press/press_05725.html) explicitly displays October 22 and provides a primary-source account. [Carbon Brief's explanation](https://www.carbonbrief.org/qa-why-a-pivotal-ipcc-meeting-in-ethiopia-ended-in-profound-disappointment) was also recovered through live homepage traversal; its page metadata reports October 20 publication and October 21 modification.
- **Sixth UAE just transition dialogue:** The [official meeting page](https://unfccc.int/event/sixth-dialogue-under-the-united-arab-emirates-just-transition-work-programme) dates it September 10–11. The [agenda record](https://unfccc.int/documents/660273) explicitly displays September 4 publication. The agenda can support an upcoming notice, not a claimed negotiated outcome.
- **September–October intersessional discussions:** The [Sydney workshop page](https://unfccc.int/event/informal-intersessional-workshop-on-just-transition) identifies September 30–October 2 and describes informal exchanges about the mechanism's institutional arrangements. Associated [agenda metadata](https://unfccc.int/documents/660690), [concept-note metadata](https://unfccc.int/documents/660775), and [presentation metadata](https://unfccc.int/documents/661097) report September 22, September 28 and October 7 respectively. The presentation catalogue is insufficient to summarize the unread attachment's substantive proposals.
- **2026 Climate Week developments:** The [official overview](https://www.unfccc.int/topics/climate-weeks) establishes the Baku dates. The [Q3 institutional report](https://unfccc.int/about-us/reports-highlights/quarterly-updates/un-climate-change-quarterly-update-q3-2026) describes adaptation implementation and transparency discussions at the event. Its own publication date is unknown; references to October 27 reports cannot be used as its publication date or proof it was available in September.

The regression corpus stores short original paraphrases, URLs, explicit dates, event dates and provenance notes. It does not redistribute full articles or pretend to be archived publisher HTML.

## September–October retrospective replay

Command: `python3 -m sdg_digest.backtest`.

[Machine-readable comparison](backtest-2026-09-10/comparison.json) covers September 1–October 31, with eight Monday issue points and an October 31 closing run. Each issue has its own candidate-level report. Unknown-date records are tested separately at the November 3 observation date and are never inserted into an earlier weekly pool.

| Measure | Legacy configured-domain counterfactual | New curated replay |
| --- | ---: | ---: |
| Target cases represented by explicitly dated records entering discovery | 1 of 4 | 3 of 4 |
| Target cases recovered when all reviewed records are tested at observation time | Not a comparable historical run | 4 of 4 |
| Unknown publication dates invented | Legacy normalizer can infer run date; not used to claim historical coverage | 0 |
| Actual network/model calls during replay | 0 / 0 | 0 / 0 |

**These are corpus-recoverability checks, not real historical recall percentages.** The harness reconstructs metadata-bearing pages and discovery indexes to exercise the production parser and traversal. These indexes are not evidence of historical site links. The legacy counterfactual places reviewed records in a feed only where a configured domain could carry them; it does not assert that the actual feed contained them. In particular, a Carbon Brief article being in a configured source domain does not prove it was available in the feed at the relevant time.

The fourth case lacks an established publication timestamp in the recovered records. Its omission from dated replay is a documented evidence gap, not silently counted as a success. Upcoming agendas are distinguished from news; dates and institutions do not force publication. Metadata-only attachments remain insufficient evidence. The regression suite asserts these decisions, event normalization and cross-week update behavior.

Actual historical important-event recall, irrelevant-candidate volume, duplicate rate, publisher diversity and billed API cost are `null` in the comparison report. They cannot be responsibly calculated from the available records.

## Real discovery check and same-capture comparison

A bounded live run used the six entry sites plus existing configured feeds. It performed **120 HTTP attempts**, downloaded about **15.3 MB**, found **117 candidate records from 10 publishers**, and admitted **22** to a final editorial pool. No generation, academic queries, email or publication followed. The run's [summary](live/summary.json) records failures including 403 responses, access restrictions, malformed/non-feed endpoints, unsupported PDF bodies and request-budget exhaustion. Its full metadata-only diagnostic log is compressed as [JSON gzip](live/2026-11-03.json.gz).

The live run predates final fixes for challenge-page detection, feed/page version consolidation and metadata-only document handling. The final implementation was then replayed against the same successfully captured responses, without network access. That replay omits robots-only sitemap links because robots bodies were not retained; its counts therefore differ from the live run.

| Final-code same-capture measure | Legacy | Discovery |
| --- | ---: | ---: |
| Candidate records | 40 | 79 |
| Distinct publishers | 4 | 6 |
| Records flagged low-substance by the same new rule checker | 35 | 58 |
| Duplicates removed in this replay | 0 | 0 |
| Duplicate rate in this replay | 0% | 0% |
| Candidates passed to final editing | 8 | 16 |
| Evidence/title input characters | 2,985 | 20,467 |
| Target IPCC article in editing pool | No | Yes |
| Replay network calls / AI calls | 0 / 0 | 0 / 0 |

Source: [captured-response comparison](capture-replay/comparison.json), with [all final-code candidate decisions](capture-replay/discovery.json). The windows intentionally retain each pipeline's defaults (legacy 7 days, discovery 21 days), so this is a comparison of configured behavior, not an isolated causal experiment. The broader window and homepage traversal both contribute to the IPCC example. No historical recall claim is inferred from it.

“Low-substance” here is a rule-screening output, not a human-labelled false-positive count. The new system encounters more weak candidates in absolute terms and filters them before model editing; the old system's count is measured retrospectively with that same rule checker. Zero observed duplicates in this capture does not demonstrate general duplicate accuracy; controlled regression tests cover same-URL feed/page versions, corroborating reports and distinct updates.

The final evidence pool is larger, so generation input can cost more. No model request was made for this comparison, and character counts are not token invoices. New discovery itself uses no AI calls. Existing title translation, academic tracing and final generation costs are unchanged in implementation and remain outside these discovery-only measurements. Request/evidence/pool limits are explicit, caching is available, and no paid search provider was added.

## Validation and remaining limits

The complete suite passes **86 tests**, comprising 51 existing tests and 35 new tests. Coverage includes RSS/HTML discovery, malformed feeds, short notices, unknown/conflicting dates, agenda/outcome separation, institutional subdomains, unreviewed external publishers, robots/redirect/cache handling, meaningful URL parameters, event-level evidence merging, substantive updates, cross-week publication fingerprints, optional upcoming output, full editorial-pool delivery and no-side-effect discovery-only CLI behavior.

Validation also includes a real bounded HTTP run, final-code replay of captured responses, and nine dated historical replay reports. No OpenAI generation or email delivery was exercised; those integrations retain their existing tests and code paths.

Initial relevance and event matching remain heuristic. JavaScript challenges and PDF-only evidence are explicit gaps; a reliable search endpoint is optional and was not available as a deployed credential. New publisher reliability needs review, and missing publication dates cannot be repaired by guessing. The original workflow remains selectable if live coverage or editorial review warrants rollback. Full operating details and every new configuration option are documented in [DISCOVERY.md](../../DISCOVERY.md).

## Release integration validation

For the requested GitHub/site publication, the upgrade was integrated onto main at `0f815bd`, whose latest issue is November 2. The newer separate issue titles, citation verification, article deduplication, approved site styling and artwork validation were retained. The integrated release passes **104 tests**. Rebuilding the five-issue public site changes only its About page's editorial-method explanation; all existing issue pages, site artwork and source archives remain unchanged. No newsletter-generation or email job is triggered by this release procedure.
