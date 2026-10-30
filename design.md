# Design: SDG Weekly Compass

Approved direction A: an editorial publication in paper white and forest green.
This shared system applies to every public website route. Future issues inherit it through the website generator.

## System
- Genre: editorial; existing brand, with the user's approved A preview as the reference.
- Home: issue metadata, headline and artwork split, linked contents, news, research signals, weekly thread, research readings, previous issues.
- Issue: a smaller headline/artwork split, desktop reading rail, readable article column.
- Archive: two editorial columns, stacked on phones; original summaries remain available.
- Search: full-width query and filters, readable single-column results.
- About and copyright: a centered long-form measure with left-aligned text.

## Tokens
`website_assets/tokens.css` is the source of truth.
- Paper: #f8f8f4; secondary paper: #e9ede5.
- Research Signals: pale sage #f0f2ec, dark body text, muted metadata and hairline dividers. Reserve solid forest green for compact controls.
- Ink: #142a24; muted ink: #57685e.
- Brand green: #17392f; hover green: #285345.
- Rules: #cbd2c9; focus and numerals: #91621a; external links: #245d9b.
- Display: Iowan Old Style, Palatino, Georgia, serif.
- Body and labels: system sans serif, with no external font dependency.
- Maximum site width: 1280px. Desktop margins grow above that width.
- Headline: 48px maximum on the home page, 32px on narrow phones.
- Body: 16px minimum; secondary source metadata: 12–14px.
- Primary content gap: 40px; hero: 48px; compact controls: 24px.

## Controls and accessibility
- One forest-green primary button, 48px minimum height.
- Primary navigation stays visible on phones, on a separate row.
- Links and controls have instant focus rings and comfortable touch targets.
- Source titles, analyses, dates and legal copy remain intact.
- No fixed-height text truncation; grids collapse in reading order.
- No animation. Smooth anchor scrolling respects reduced motion.
- Search needs JavaScript and provides an archive link when scripts are disabled.
- Optional artwork hides on failure and the hero expands to a text layout.

## Exports
- `website_assets/tokens.css`: palette, fonts and layout constants.
- `website_assets/base.css`: document defaults and accessibility.
- `website_assets/site.css`: shared components and responsive layouts.
- `sdg_digest/website.py`: route templates and asset copying.
