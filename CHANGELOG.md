# Changelog

Mormor uses two independent version axes:

- **Cheatsheet version** (`v1`, `v2`, …) — the protocol artifact itself; bumps when the cheatsheet body changes. Every version is frozen in [`cheatsheets/`](./cheatsheets/); `cheatsheets/DEFAULT` names the recommended pick.
- **Repo / release version** — [SemVer](https://semver.org/), the entries below. A cheatsheet change is a **minor** bump; benchmark re-runs, docs, and tooling are **patch** bumps with the cheatsheet unchanged. 0.x is experimental.

## [0.2.0] — 2026-06-10

Cheatsheet **v1 → v2** — `cheatsheets/DEFAULT` now points to [`v2`](./cheatsheets/v2.md); v1 stays frozen.

- **v2 cheatsheet:** dedup of v1 plus a classification cue, an `AskUserQuestion` rule, and a fragment-style compression rule. Smaller and cleaner than v1.
- **Re-validated at n=50 (Opus 4.8 / Sonnet 4.6).** vs v1: ~8–10% shorter responses, quality held, format compliance 1.000. Billed Δ vs baseline: Opus −52%, Sonnet −54%.
- **Caching finding:** the cheatsheet only caches above Anthropic's [1,024-token minimum](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — clears it on Opus but not Sonnet single-message calls (resolves the old "cache anomaly"; the Sonnet billed figure is conservative). See README → Empirical results.
- **Benchmark:** rubric v2 — `delegated_chain` dispatch hops no longer penalize a parent for sharing context with the child.

## [0.1.1] — 2026-05-29

Maintenance — **cheatsheet unchanged (still v1)**.

- Re-validated on Opus 4.8 (n=50) after its release. The headline numbers in [`README.md`](./README.md) now use Opus 4.8; the earlier Opus 4.7 results moved to the README's "Earlier results" section. Aggregate held: mormor ~-50% billed vs baseline, quality 4.82.
- Introduced cheatsheet versioning: frozen versions under [`cheatsheets/`](./cheatsheets/) (v1), with `cheatsheets/DEFAULT` naming the recommended pick.

## [0.1.0] — 2026-05-15

Initial release.

- 6-label vocabulary (`goal:`, `note:`, `case:`, `done:`, `ask:`, `test:`) rendered as level-3 markdown headings (`### label:`) on their own line, with content on the next line.
- Strict markdown discipline: only bullet lists, numbered lists, fenced code, tables, and backticks for code/paths/identifiers are allowed alongside the label headings. No bold, italics, other heading levels, or horizontal rules in responses.
- Empirically validated on Sonnet 4.6 and Opus 4.7 across 5 scenarios at 50 runs per cell — see [`README.md`](./README.md) for the headline numbers and [`bench/README.md`](./bench/README.md) for methodology.
