# November 9 editorial repair — reviewed November 10, 2026

## Published content prepared for release

Issue title: **COP31 Implementation, Investment Constraints and Unequal Disaster Recovery**.

The corrected issue contains five news briefs, two research signals and two paper interpretations, in English and Chinese. The final edition was reconstructed from retained AI draft material and edited against the retrieved evidence; it is explicitly marked `generation_mode: reviewed`, not represented as an unattended model success.

- News headlines name the development directly and retain uncertainty. Source names remain in their own metadata row; original titles remain available separately.
- Summaries identify actual developments instead of truncating RSS snippets. The COP31 tracker is described as an agenda, not an agreed outcome. Brazil's roadmap is described as voluntary and outside COP30's negotiated outcome. Wildfire health effects remain under study rather than being overstated as established diagnoses.
- The ISDS signal is limited to the policy-space concern supported by the available E3G feed excerpt. Unsupported claims about specific treaty remedies, abusive claims and supply-chain restructuring were removed.
- The disaster study's argument and figures were checked against the Nature page: 132-country microsimulations, 9% of asset damage and 33% of well-being losses for the poorest populations. Its relation to wildfire recovery is explicitly editorial analysis.
- Both agenda sections identify relevant policy processes and distinguish policy implications from a documented formal negotiating role. Neither contains the blanket unclear placeholder.
- Both paper notes are interpretations rather than copies of abstracts. Methods correctly identify sociotechnical MRV analysis and comparative/critical analysis. Statements about missing case-selection detail do not falsely claim that no method is given.
- Title support, introduction/thread references and reading connections all refer to final selected articles.

## Evidence and review boundaries

Rebuilding the original candidate pool recovered 16 candidates, with page text for five and feed evidence for eleven, using 32 HTTP requests. Final selection uses all five page-text candidates plus two feed-supported items (E3G and the UK seas study). Access challenges and HTTP restrictions were respected. No unavailable full text is represented as read. Page updates later than the issue date were excluded by the rebuild path.

The two paper identities and source abstracts were retained from the verified archived issue; the defective old notes were not reused. Current retrieval is a reconstruction, not a claim that an immutable November 9 full-text snapshot exists.

## Pipeline changes

1. Exhausted content validation no longer silently substitutes deterministic source excerpts. Optional fallback remains preview-only. Generation, CLI, archive, email and website checks block it from publication.
2. A failing issue title is repaired against the validated selection; valid articles are retained. Repair receives explicit module membership and the required research coverage count, with at most two title-only attempts.
3. URL references resolve only controlled tracking/fragment variants of supplied candidates. Meaningful query differences remain distinct.
4. Discovery reserves actual HTTP capacity for evidence retrieval, including a per-host allowance. Temporary phase exhaustion does not cache a false robots denial.
5. Checks reject boilerplate headlines, metadata leakage, truncated excerpts, copied abstracts, contradictory method disclaimers and references to unselected articles. Failed drafts remain available for inspection. Error messages identify the fields needing correction.
6. A separate archived-issue preview job has read-only repository permissions, receives no email credentials, and does not publish the site or modify sent history.

## Verification

- 117 tests passed, including regression coverage for validation exhaustion, fallback publication blocking, title-only repair, URL variants, evidence reservation, abstract copying and false method disclaimers.
- A live check of the regular discovery path used 113 of 120 requests and made 27 evidence retrieval attempts. No final-pool item failed because the request budget was exhausted. Remaining limitations were source access restrictions, not budget starvation. This check retained normal sent-history exclusions and is not a recall comparison with the reconstruction.
- Generated site links/assets resolve locally. The issue title, article summaries, research sections and paper notes were inspected in the browser. Other issue pages, styling and artwork were retained.
- Sent-history SHA256 remains `3966159a077a831c822019c8247f238f603e04f6ec2cc24da75aa3b84fc5becd`.
- No email was sent. The original publishing/email job was skipped in all preview runs.

## Retained workflow evidence

- [Initial preview](https://github.com/neoxyz-99/SDG_Daily_News/actions/runs/42781611331): generation completed, including isolated title repair. Review identified additional cross-reference and headline issues.
- [Second preview](https://github.com/neoxyz-99/SDG_Daily_News/actions/runs/42782478649): title coverage failed and correctly stopped the run, preserving the body for review instead of publishing fallback text.
- [Third preview](https://github.com/neoxyz-99/SDG_Daily_News/actions/runs/42783875271): cross-reference/headline checks correctly rejected the unattended draft. The final published issue is the separately reviewed reconstruction described above. These failures are not reported as successful unattended generation.

Future unattended runs may still stop when editorial quality cannot be established. They will retain diagnostics and the existing public edition rather than replace it with an unreviewed fallback.
