# Cheatsheet versions

The cheatsheet is versioned independently from the repo/release version.

- **Cheatsheet version** — whole numbers (`v1`, `v2`, …). Each is a frozen file in this directory. A version bumps only when the cheatsheet body changes.
- **Repo / release version** — SemVer, tracked in [`../CHANGELOG.md`](../CHANGELOG.md). A cheatsheet change is a **minor** bump; benchmark re-runs, docs, and tooling are **patch** bumps with the cheatsheet unchanged.

## Which one to use

Paste the **recommended** version — currently [`v3.md`](./v3.md). The recommended pick is named in [`DEFAULT`](./DEFAULT): it's the most stable, general one, and not necessarily the highest number (specialized or experimental versions may also live here). Reference a specific version so your setup is pinned and reproducible.

## Files

| file | role |
| --- | --- |
| [`v3.md`](./v3.md) | frozen cheatsheet v3 — **the recommended pick** (validated at n=50 in [`../README.md`](../README.md)). Paste this. |
| [`v2.md`](./v2.md) | frozen cheatsheet v2 — superseded by v3. Kept for reference/reproducibility. |
| [`v1.md`](./v1.md) | frozen cheatsheet v1 — the initial release artifact (the exact bytes benchmarked for v0.1.0). Kept for reference/reproducibility. |
| `DEFAULT` | names the recommended version (currently `v3`) |

## Adding a new version

1. Copy the frozen version you want to build on: `cp cheatsheets/v1.md cheatsheets/v2.md`.
2. Edit `cheatsheets/v2.md`. Benchmark it head-to-head against the existing frozen versions (which stay available): `python bench/run.py --system-prompt-file cheatsheets/v2.md` vs. `--system-prompt-file cheatsheets/v1.md`.
3. If `v2` becomes the new recommended pick: `printf 'v2\n' > cheatsheets/DEFAULT`.
4. Bump the repo **minor** version in `CHANGELOG.md` and note the cheatsheet `v1 → v2` change. Re-validate with the benchmark.

Past versions stay here forever, so older results and references remain reproducible and every version can be re-benchmarked at any time.
