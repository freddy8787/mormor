# Mormor benchmark

Empirical validation of Mormor against a prose baseline and a "terse prose" middle variant.

## What it measures

For each (scenario, variant, model) combination, it measures:

- **input/output tokens** — separate counts for input, cache-creation, cache-read, output. `output_tokens` is the SDK's total generation count and includes any extended-thinking tokens the model emitted before the visible response. Runs use `effort='low'` (passed in [engine.py make_options](engine.py)) to dampen extended thinking where the SDK accepts it; older SDK builds silently fall back to default thinking.
- **visible_output_tokens** — approximation of the size of the displayed response (output minus extended-thinking overhead). Computed as `len(response_text) // 4` — the English-prose folk heuristic. Real BPE tokenizers count differently on label-dense or code-dense content; an offline probe against this benchmark's response_text shows the heuristic over-counts by ~3-7% relative to a words+punct proxy, with the bias roughly uniform across variants (baseline 1.07, terse 1.03, mormor 1.04).
- **latency_ms** — how long each call took, in milliseconds (request → full response)
- **quality_score (1–5)** — graded by Claude Haiku 4.5 (LLM-as-judge) against scenario-specific rubrics — constant grader across all runs for fair comparison
- **format_compliance** — binary; is the response in a Mormor-compliant shape? `1` when any of the 6 labels appears at line start OR the entire response is a bare atomic answer (number / yes / no), which the cheatsheet allows for prompts with no accompanying-context requirement. `0` otherwise. Across the current scenario suite the atomic branch fires rarely — every scenario is multi-part (`category + reason`, decision-table, multi-hop synthesis), so the labeled form is the dominant compliance path.

Aggregated metrics derived from those:

- **billed_cost** — token spend with cache-aware weights (input 1.0, cache_creation 1.25, cache_read 0.10, output 5.0). These ratios match [Anthropic's published pricing multipliers](https://platform.claude.com/docs/en/about-claude/pricing): 5-minute cache write at 1.25× input, cache reads at 0.10× input, output at 5× input (consistent across Opus 4.x, Sonnet 4.x, Haiku 4.x). The 1-hour cache TTL (2× input) is not modeled — defaults to 5-min caching.
- **vis_out_ratio** — ratio of response sizes — mormor responses divided by baseline responses (lower = better compression). Unaffected by cache state, so it's the cleanest cross-run comparison. Inherits the chars/4 approximation from `visible_output_tokens`; the bias is roughly uniform across variants (see above), so the ratio survives the approximation within a few percent of the true tokenizer ratio.
- **q/kt** — quality score per 1,000 tokens spent — efficiency metric (higher is better). If mormor saves tokens but loses quality at the same rate, q/kt stays flat. If it saves tokens AND keeps quality, q/kt rises.

## Scenarios

| scenario | shape | turns per run |
| --- | --- | ---: |
| `single_round_trip` | one user message → one agent response | 1 |
| `branching` | review-with-classification (severity → action) | 1 |
| `multi_turn` | 5-turn debugging conversation | 5 |
| `high_frequency` | 5 inputs, 1 turn each (classification) | 5 |
| `delegated_chain` | 5-hop fan-out (parent → 2 children → parent synthesize) | 5 |

Each scenario has three matched variants: `baseline` (verbose prose), `terse` (short prose, no protocol), `mormor` (full labeled protocol).

## Per-run folders

Every invocation lands in its own dated folder under `results/`:

```
bench/results/
├── 2026-05-10_15-30-22_sonnet_cheatsheet/
│   ├── benchmark.csv            # per-row data (one SDK call per row)
│   ├── run.log                  # full stdout+stderr (retries, checkpoints, summary)
│   ├── summary.txt              # the final summary tables, no noise
│   └── meta.json                # CLI args + model ids + system-prompt path + status
└── 2026-05-10_16-45-10_opus_cheatsheet/
    └── ...
```

Folder name format: `<DATE>_<TIME>_<MODEL>_<DETAILS>[_<LABEL>]`

| element | example | rules |
| --- | --- | --- |
| date | `2026-05-10` | ISO; sorts chronologically |
| time | `15-30-22` | HH-MM-SS; disambiguates parallel starts |
| model | `sonnet`, `opus`, `multi` | from `--only-models`; `multi` if multiple |
| details | `cheatsheet`, `smoke`, or custom file basename | derived from `--system-prompt-file`, `--smoke` |
| label | `<sanitized-string>` | from `--label` (optional) |

The `results/` directory is `.gitignore`d — runs are local-only artifacts.

## Run it

Requires `claude_agent_sdk` and Python 3.10+.

```bash
# full default run (opus + sonnet, all 5 scenarios, all 3 variants, RUNS=5)
python run.py

# smoke (1 RUN, sonnet only, baseline + mormor only)
python run.py --smoke

# only specific scenarios
python run.py --only-scenarios multi_turn,branching

# only specific models
python run.py --only-models sonnet

# only specific variants — useful for splitting a canonical run across
# parallel processes (one per variant; 6 processes total = 2 models × 3
# variants). Each process gets its own (model, system_prompt) cache and runs
# independently. Merge the per-variant benchmark.csv files afterward.
python run.py --only-variants mormor --label canonical-mormor

# override RUNS
python run.py --runs 3

# use a custom file as the system prompt (e.g. testing a candidate revision)
python run.py --system-prompt-file /tmp/cheatsheet_candidate.md

# tag an ad-hoc experiment with a custom label
python run.py --label test-x --only-models sonnet

# resume a partial run after a crash or plan-limit
python run.py --resume bench/results/2026-05-10_15-30-22_sonnet_cheatsheet
```

Combine flags freely. The folder name auto-derives from them.

## Resuming

`--resume PATH` continues an existing run by re-using its `benchmark.csv` and skipping `(scenario, variant, model, run_n)` tuples already complete in the CSV. Useful when:

- A long run hit an Anthropic plan-limit ceiling and exited partway
- An SDK transient failure exhausted the retry budget on a single call
- You stopped a run with Ctrl-C and want to pick up where it left off

The `--resume` flag is **explicit** — there's no auto-detect. Pass the same flags you originally used (model filter, system prompt, etc.); the script doesn't re-derive them from `meta.json`.

## Reliability

- **Per-call atomic save:** rows are persisted incrementally (tmp file + rename) after each call. Mid-run crashes don't lose more than one row.
- **Retry:** transient SDK errors (e.g. "Command failed exit 1") get exponential-backoff retry — up to 7 retries (8 attempts total) before failing the call. Grader calls retry up to 4 times (5 attempts total); on exhaustion the row records `quality_score=0` and the run continues.
- **Disallowed tools:** the agent runs with no tool access (no Task, Bash, Edit, etc.) so the benchmark measures system-prompt + user-prompt → text-response, with nothing else in the loop.

## Methodology notes

- **Quality grader is constant.** Always Claude Haiku 4.5, regardless of which model is being benchmarked. This isolates protocol effects from model effects.
- **Per-scenario rubrics.** Each scenario has 5 binary criteria worth 1 point each, anchored to factual content (e.g. "names the missing index", "doesn't include extraneous frameworks"). This catches the case where a response "looks good" but misses the actual point.
- **Cache state is non-deterministic across runs.** `cache_read_input_tokens` swings between runs due to prompt-cache eviction. Cross-run comparisons should prefer `vis_out_ratio` or `billed_cost`, not raw `input_tokens`.
- **Multi-turn caveat.** Multi-turn scenarios accumulate cache across turns; compression appears smaller on raw token counts because cache_read dwarfs visible output. The `billed_cost` weighting (cache_read at 0.10× input per Anthropic's published rate) reflects real spend.
- **Grader=0 handling.** When grader retries exhaust (e.g. during plan-limit windows), the row records `quality_score=0`. The summary's quality aggregations (`qual`, `q_std`, `q/kt`, the `qual_drop` used by verdicts) automatically exclude these rows. The averages table's `q0` column shows the count of excluded rows per cell, and `meta.json.rows_grader_zero` gives the run total. If you re-aggregate a CSV yourself, filter with `quality_score > 0`.

## Cleanup snippets

Common housekeeping:

```bash
# delete all runs older than 7 days
find bench/results -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +

# delete all sonnet runs
rm -rf bench/results/*_sonnet_*

# delete all smoke runs
rm -rf bench/results/*_smoke*

# delete a specific run
rm -rf bench/results/2026-05-10_15-30-22_sonnet_cheatsheet

# wipe everything
rm -rf bench/results/*

# list runs with their final mormor-vs-baseline summary line
for d in bench/results/*/; do
  if [ -f "$d/summary.txt" ]; then
    echo "$(basename "$d") → $(grep -A2 'mormor vs baseline — BILLED' "$d/summary.txt" | tail -1)"
  fi
done

# show meta.json status of every run (requires jq)
for d in bench/results/*/; do
  status=$(jq -r '.exit_status' "$d/meta.json" 2>/dev/null)
  rows=$(jq -r '.rows_total' "$d/meta.json" 2>/dev/null)
  echo "$(basename "$d") → $status, $rows rows"
done
```

## Adding a scenario

Scenarios live in the `SCENARIOS` dict in `scenarios.py`. Each scenario has a single `user` key (or `user_template` for parameterized inputs, `turns` for multi-turn, `assign_security`/`assign_quality`/`synthesize` for chained ones). The grading rubric goes in `SCENARIO_RUBRICS` (or `CHAIN_HOP_RUBRICS` for chained scenarios).

Three matched variants per scenario. Same task, three different framings — that's what we're measuring.

## Files

```
bench/
├── run.py           # entry point — argparse, CLI overrides, main orchestrator
├── config.py        # knobs: MODELS, RUNS, GRADER_MODEL, COST_WEIGHTS, DISALLOWED_TOOLS
├── prompts.py       # BASELINE_SYSTEM, TERSE_SYSTEM, cheatsheet loader, label detection
├── scenarios.py     # SCENARIOS dict, DELEGATED_CHAIN_TASK, SCENARIO_RUBRICS, CHAIN_HOP_RUBRICS
├── engine.py        # SDK calls, grading, scenario runners, CSV/folder I/O
├── reporting.py     # print_summary + aggregate row helpers
├── results/         # per-run output folders (gitignored)
└── README.md        # this file
```

Edit `config.py` to retarget models or change cost weights. Edit `scenarios.py` to add a new workload. Other files rarely need touching.

## Limitations

- Two production models tested (Sonnet 4.6, Opus 4.8; earlier Opus 4.7 results retained in the README's "Earlier results"). Smaller / faster models can be added to `MODELS` if useful.
- Five scenarios. Coverage is intentionally narrow but representative; broader workload coverage is a future expansion.
- Quality grader is itself a model. We use a constant grader and per-scenario rubrics to mitigate, but absolute quality scores are noisier than relative comparisons.
- Cache-aware billed cost uses standard public-pricing weights. Your actual cost depends on your contract.

## Reproducing the baseline

```bash
# sequential (single command, both models, RUNS=5, ~3–4h wall time)
python run.py
```

Default settings = opus + sonnet, all 5 scenarios, RUNS=5, full 6-label cheatsheet. Output lands in `bench/results/<DATE>_<TIME>_<MODEL>_cheatsheet/`.

The README's headline numbers come from canonical runs with `--runs 50` (label `v0.1.0-final-n50`) — same script, just more samples per cell for tighter confidence intervals (~6–8h wall time per model with the 3 variants split across parallel processes, ~20h sequential). The current Opus column is a 4.8 re-run done after that model's release; earlier Opus 4.7 results are retained under the README's "Earlier results".

For ~half the wall time, split per-model and run them in parallel — each writes to its own per-run folder:

```bash
# parallel (two terminals or `&`); ~1.5–2.5h end-to-end at RUNS=5
python run.py --only-models sonnet &
python run.py --only-models opus &
wait
```

For ~1/3 the wall time, split per `(model, variant)` and fan out across 6 parallel processes — each gets its own clean `(model, system_prompt)` cache and writes to its own folder. After all 6 finish, concatenate the `benchmark.csv` files into a single combined CSV and re-run `reporting.print_summary` against it to regenerate the canonical aggregate (the `AGGREGATE (scen-eq)` row in the delta matrices is the marketing-relevant number):

```bash
# 6 parallel processes; ~2.5–3h end-to-end at RUNS=20
for model in sonnet opus; do
  for variant in baseline terse mormor; do
    python run.py --only-models $model --only-variants $variant \
      --runs 20 --label canonical-$variant &
  done
done
wait
```

This works because each invocation creates an independent run folder; nothing is shared between processes.
