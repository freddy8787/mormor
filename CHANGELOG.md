# Changelog

Mormor follows [SemVer](https://semver.org/). 0.x is experimental — minor bumps may change the label set or behavior rules.

## [0.1.0] — 2026-05-15

Initial release.

- 6-label vocabulary (`goal:`, `note:`, `case:`, `done:`, `ask:`, `test:`) rendered as level-3 markdown headings (`### label:`) on their own line, with content on the next line.
- Strict markdown discipline: only bullet lists, numbered lists, fenced code, tables, and backticks for code/paths/identifiers are allowed alongside the label headings. No bold, italics, other heading levels, or horizontal rules in responses.
- Empirically validated on Sonnet 4.6 and Opus 4.7 across 5 scenarios at 50 runs per cell — see [`README.md`](./README.md) for the headline numbers and [`bench/README.md`](./bench/README.md) for methodology.
