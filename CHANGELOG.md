# Changelog

Mormor uses two independent version axes:

- **Cheatsheet version** (`v1`, `v2`, …) — the protocol artifact itself; bumps when the cheatsheet body changes. Every version is frozen in [`cheatsheets/`](./cheatsheets/); `cheatsheets/DEFAULT` names the recommended pick.
- **Repo / release version** — [SemVer](https://semver.org/), the entries below. A cheatsheet change is a **minor** bump; benchmark re-runs, docs, and tooling are **patch** bumps with the cheatsheet unchanged. 0.x is experimental.

## [0.1.1] — 2026-05-29

Maintenance — **cheatsheet unchanged (still v1)**.

- Re-validated on Opus 4.8 (n=50) after its release. The headline numbers in [`README.md`](./README.md) now use Opus 4.8; the earlier Opus 4.7 results moved to the README's "Earlier results" section. Aggregate held: mormor ~-50% billed vs baseline, quality 4.82.
- Introduced cheatsheet versioning: frozen versions under [`cheatsheets/`](./cheatsheets/) (v1), with `cheatsheets/DEFAULT` naming the recommended pick.

## [0.1.0] — 2026-05-15

Initial release.

- 6-label vocabulary (`goal:`, `note:`, `case:`, `done:`, `ask:`, `test:`) rendered as level-3 markdown headings (`### label:`) on their own line, with content on the next line.
- Strict markdown discipline: only bullet lists, numbered lists, fenced code, tables, and backticks for code/paths/identifiers are allowed alongside the label headings. No bold, italics, other heading levels, or horizontal rules in responses.
- Empirically validated on Sonnet 4.6 and Opus 4.7 across 5 scenarios at 50 runs per cell — see [`README.md`](./README.md) for the headline numbers and [`bench/README.md`](./bench/README.md) for methodology.
