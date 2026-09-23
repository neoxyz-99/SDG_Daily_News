# September 22 publication corrections

## Citation mismatch

The pairing of “Climate change and the global south” with DOI `10.1080/14693062.2004.9685516` was already present in bibliography import commit `898158c` (June 8). That DOI belongs to Dudek, Golub and Strukova, “Economics of the Kyoto Protocol for Russia”, not Huq and Reid. The available repository history shows when the incorrect pairing entered the library, but does not establish how the original contributor produced it.

The generator validated against that local library as a trusted allowlist and copied its seed interpretation verbatim. This checked provenance within the application, not whether the citation matched the DOI registry. Pool merging also allowed a seed with a matching DOI to override a traced paper's metadata even when their titles differed.

The unsupported seed has been replaced with Huq, Reid, Konate, Rahman, Sokona and Crick (2004), “Mainstreaming adaptation to climate change in Least Developed Countries (LDCs)”, DOI `10.1080/14693062.2004.9685508`. This is a replacement reading, not a claim that the unsupported old title was another name for this paper. Both languages' reading notes and research questions are grounded in the replacement's publisher abstract. The September 21 and July 15 archived occurrences were corrected, together with the reading history.

Publisher evidence:
- Incorrect DOI destination: https://www.tandfonline.com/doi/abs/10.1080/14693062.2004.9685516
- Verified replacement: https://www.tandfonline.com/doi/abs/10.1080/14693062.2004.9685508

All seven updated seed citations were checked live against Crossref on September 22. The production pipeline now checks DOI, title, journal, author surnames and publication year, derives URLs from the verified DOI, and excludes mismatches or records that cannot be verified. Only explicit offline dry-run previews bypass the network gate. Traced papers retain registry metadata when a seed title or journal disagrees. Generated paper selection remains constrained to the supplied citation tuples.

## Duplicate articles

The generation validator checked candidates and source limits independently for news and signals, without checking overlap. The September 21 issue therefore included the same two Carbon Brief URLs in both sections. URL-normalized deduplication now retains the detailed signal once and removes the duplicate brief; it also applies to offline fallback and the public archive renderer/search index. The current issue now has six news briefs and two signals.

## Missing September 7 artwork

Commit `dfdedd3` introduced the September 7 `.jpg` in both source and public assets. Its bytes did not begin with a JPEG header and could not be decoded. Existing-file checks and site tests checked presence, not image validity. The repository alone does not establish which transfer or encoding step corrupted the bytes.

The corrupt asset was replaced with original generated editorial artwork. Image generation, reuse, atomic writing and site publication now decode/verify JPEGs. Invalid existing artwork triggers regeneration, invalid site assets block publication, and the latest issue must have artwork before site replacement. The workflow no longer ignores image-generation failure. Prompt and generation mode are recorded in `2026-09-22-artwork-prompt.txt`.

## Validation

Regression tests cover cross-section and within-section duplicates, URL tracking variants, wrong DOI titles, unavailable metadata, seed/traced conflicts, corrupt JPEG data, repair of existing corrupt assets, and preservation of the published site on artwork failure. Desktop and mobile previews were visually inspected.
