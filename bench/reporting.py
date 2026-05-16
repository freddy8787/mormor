"""Mormor benchmark — aggregate metrics and summary tables.

Pure-Python row helpers (no SDK calls). Takes the list-of-dicts produced by
`engine` and prints the multi-section summary table that lands in summary.txt.

The order of sections matches the published README presentation:
1. averages per scenario × variant × model
2. terse/mormor vs baseline — raw token delta + quality verdict
3. terse/mormor vs baseline — visible-output-only delta (no cache_read)
4. response-size ratio (mormor / baseline)
5. terse/mormor vs baseline — billed-cost delta (cache-weighted)
6. mean quality score matrix
7. quality-per-kilotoken matrix
8. mean latency matrix
"""

import statistics

import config


# --- row-level helpers ---

def _row_total(r):
    """Raw token sum — input + cache_read + cache_creation + output.

    Cross-run comparisons of this metric are NOISY because cache_read varies
    wildly between runs (cache machinery decides differently). For
    cross-run comparison use `_row_billed` instead.
    """
    return (
        r['input_tokens']
        + r['cache_read_tokens']
        + r['cache_creation_tokens']
        + r['output_tokens']
    )


def _row_billed(r):
    """Cost-weighted token total. Stable across runs; closer to real billing."""
    w = config.COST_WEIGHTS
    return (
        r['input_tokens']           * w['input']
        + r['cache_creation_tokens'] * w['cache_creation']
        + r['cache_read_tokens']     * w['cache_read']
        + r['output_tokens']         * w['output']
    )


def _row_visible(r):
    """Fresh tokens + visible output only — strips cache_read noise and
    invisible thinking tokens. Closer to "true protocol cost" per call."""
    return (
        r['input_tokens']
        + r['cache_creation_tokens']
        + r['visible_output_tokens']
    )


# --- aggregations ---

def _avg(rows, fn):
    return sum(fn(r) for r in rows) / len(rows) if rows else 0


def _graded(rows):
    """Rows whose grader call succeeded (quality_score > 0).

    `engine._grade_with_prompt` records score=0 when grader retries exhaust
    — a single such row in a 5-run cell otherwise drags the mean by 1.0 and
    can flip a verdict. All quality aggregations filter through this so the
    summary reflects the score over rows that were actually graded. Count
    of excluded rows is surfaced via the `q0` column in the averages
    table, and the total appears in `meta.json.rows_grader_zero`.
    """
    return [r for r in rows if r['quality_score'] > 0]


def _avg_total(rows):     return _avg(rows, _row_total)
def _avg_billed(rows):    return _avg(rows, _row_billed)
def _avg_visible(rows):   return _avg(rows, _row_visible)
def _avg_quality(rows):   return _avg(_graded(rows), lambda r: r['quality_score'])
def _avg_fmt(rows):       return _avg(rows, lambda r: r['format_compliance'])
def _avg_latency_ms(rows): return _avg(rows, lambda r: r['latency_ms'])


def _n_grader_zero(rows):
    return sum(1 for r in rows if r['quality_score'] == 0)


def _qual_stats(rows):
    """(mean, stdev, min, max) for quality scores excluding grader-zero rows.

    stdev = 0 if fewer than 2 valid scores remain after filtering.
    """
    scores = [r['quality_score'] for r in _graded(rows)]
    if not scores:
        return 0, 0, 0, 0
    mean = statistics.mean(scores)
    stdev = statistics.stdev(scores) if len(scores) >= 2 else 0
    return mean, stdev, min(scores), max(scores)


def _q_per_kt(rows):
    """Quality per kilotoken — mean quality_score / (mean total_tokens / 1000).

    Higher = more quality per token. A variant that uses fewer tokens but
    loses quality will show LOWER q/kt — caught here without extra logic.

    Both numerator and denominator are computed over graded rows only —
    using a row's tokens with its missing quality would deflate q/kt
    artificially.
    """
    valid = _graded(rows)
    if not valid:
        return 0
    mean_q = _avg(valid, lambda r: r['quality_score'])
    mean_t = _avg(valid, _row_total)
    return (mean_q * 1000 / mean_t) if mean_t > 0 else 0


def _verdict(delta_pct, quality_drop=0.0):
    """Quality-conditional verdict.

    A token "win" that costs >0.3 quality points is downgraded to MIXED — the
    protocol may save tokens but produces meaningfully worse answers.
    Otherwise: WIN <-15%, WASH ±15%, LOSS >+15%.
    """
    if quality_drop > 0.3:
        return 'MIXED'
    if delta_pct < -15:
        return 'WIN'
    if abs(delta_pct) < 15:
        return 'WASH'
    return 'LOSS'


def _filter(results, **kwargs):
    return [r for r in results if all(r[k] == v for k, v in kwargs.items())]


# --- summary ---

def print_summary(results):
    """Print the full multi-section summary table to stdout.

    Caller wires stdout to wherever the summary should land (terminal,
    run.log, summary.txt).
    """
    scenarios = sorted(set(r['scenario'] for r in results))
    # Preserve config.MODELS order; only include models that actually appear.
    models = [m for m, _ in config.MODELS if any(r['model'] == m for r in results)]
    variants = config.VARIANTS

    _print_averages(results, scenarios, variants, models)
    _print_delta_matrices(results, scenarios, variants, models, mode='total')
    _print_delta_matrices(results, scenarios, variants, models, mode='visible')
    _print_response_size_ratio(results, scenarios, models)
    _print_delta_matrices(results, scenarios, variants, models, mode='billed')
    _print_quality_matrix(results, variants, models)
    _print_q_per_kt_matrix(results, variants, models)
    _print_latency_matrix(results, variants, models)


def _print_averages(results, scenarios, variants, models):
    # vis_out = visible response text tokens (≈ chars/4); out = total output
    # tokens reported by SDK (includes hidden thinking). Gap = thinking overhead.
    # qual_std reveals whether the grader is scoring binary (0 stdev = everyone
    # gets 5) or actually graduated. q0 = count of rows in this cell whose
    # grader exhausted retries (quality_score==0) and are therefore excluded
    # from qual / q_std / q/kt. fmt% = % of responses in a Mormor-compliant
    # shape — either a label at line start OR (rarer) a pure atomic answer
    # (bare number / yes / no). For mormor variant this should be high; for
    # others near zero (occasional false-positive on label-like content or
    # baseline responses that happen to be atomic).
    for model in models:
        print(f'\n=== averages — {model} ===')
        # billed = weighted cost (cache_read at 0.10x, output at 5x) — the
        # cross-run-stable cost metric. total = raw face-value sum (noisy).
        print(f'{"scenario":<22} {"variant":<10} {"in_new":<7} {"in_cache":<9} '
              f'{"out":<6} {"vis_out":<8} {"total":<7} {"billed":<7} {"lat_s":<6} '
              f'{"qual":<5} {"q/kt":<6} {"q_std":<6} {"q0":<3} {"fmt%":<5}')
        for scenario in scenarios:
            for variant in variants:
                rs = _filter(results, scenario=scenario, variant=variant, model=model)
                if not rs:
                    continue
                in_new = sum(r['input_tokens'] for r in rs) / len(rs)
                in_cache = sum(r['cache_read_tokens'] + r['cache_creation_tokens'] for r in rs) / len(rs)
                out = sum(r['output_tokens'] for r in rs) / len(rs)
                vis_out = sum(r['visible_output_tokens'] for r in rs) / len(rs)
                total = in_new + in_cache + out
                billed = _avg_billed(rs)
                qmean, qstd, _, _ = _qual_stats(rs)
                lat_s = _avg_latency_ms(rs) / 1000
                qkt = _q_per_kt(rs)
                q0 = _n_grader_zero(rs)
                fmt_pct = 100 * _avg_fmt(rs)
                print(f'{scenario:<22} {variant:<10} {in_new:<7.0f} {in_cache:<9.0f} '
                      f'{out:<6.0f} {vis_out:<8.0f} {total:<7.0f} {billed:<7.0f} '
                      f'{lat_s:<6.1f} {qmean:<5.2f} {qkt:<6.2f} {qstd:<6.2f} '
                      f'{q0:<3d} {fmt_pct:<5.0f}')


def _print_delta_matrices(results, scenarios, variants, models, mode):
    """One matrix per (new, ref) variant pair: token delta + quality verdict.

    mode controls which token measure is compared:
    - 'total':   raw token sum (input+cache_read+cache_creation+output)
    - 'visible': fresh + visible only (no cache_read, no thinking)
    - 'billed':  cost-weighted (cache-aware) — the stable cross-run metric

    The trailing `AGGREGATE` row is computed with **scenario-equal**
    weighting: each scenario's per-cell mean is summed, then the delta is
    taken on the sums. This treats every scenario as equally important
    regardless of how many rows it produces (high_frequency / multi_turn /
    delegated_chain have 5 rows per run, single_round_trip and branching
    have 1). Scenario-equal is what the README's headline aggregates use;
    if you want row-equal instead, compute it manually from the per-cell
    means in the averages section.
    """
    title = {
        'total':   'token delta + quality verdict by model',
        'visible': 'VISIBLE-OUTPUT delta by model (no cache_read, no thinking)',
        'billed':  'BILLED-COST delta by model (cache-weighted)',
    }[mode]
    measure = {
        'total':   _avg_total,
        'visible': _avg_visible,
        'billed':  _avg_billed,
    }[mode]

    pairs = [('terse', 'baseline'), ('mormor', 'baseline'), ('mormor', 'terse')]
    for new, ref in pairs:
        if new not in variants or ref not in variants:
            continue
        print(f'\n=== {new} vs {ref} — {title} ===')
        header = f'{"scenario":<22}' + ''.join(f'{m:>18}' for m in models)
        print(header)
        # Accumulate per-model sums of per-scenario means for the AGGREGATE row.
        agg_ref = {m: 0.0 for m in models}
        agg_new = {m: 0.0 for m in models}
        agg_qual_ref = {m: 0.0 for m in models}
        agg_qual_new = {m: 0.0 for m in models}
        agg_n = {m: 0 for m in models}
        for s in scenarios:
            cells = []
            for m in models:
                ref_rs = _filter(results, scenario=s, variant=ref, model=m)
                new_rs = _filter(results, scenario=s, variant=new, model=m)
                if not ref_rs or not new_rs:
                    cells.append(f'{"-":>18}')
                    continue
                ref_v = measure(ref_rs)
                new_v = measure(new_rs)
                if ref_v <= 0:
                    cells.append(f'{"-":>18}')
                    continue
                delta = (new_v - ref_v) / ref_v * 100
                qual_drop = _avg_quality(ref_rs) - _avg_quality(new_rs)
                cells.append(f'{delta:+7.1f}% [{_verdict(delta, qual_drop):<5}] ')
                agg_ref[m] += ref_v
                agg_new[m] += new_v
                agg_qual_ref[m] += _avg_quality(ref_rs)
                agg_qual_new[m] += _avg_quality(new_rs)
                agg_n[m] += 1
            print(f'{s:<22}{"".join(cells)}')
        # AGGREGATE row (scenario-equal weighting — see docstring).
        agg_cells = []
        for m in models:
            if agg_n[m] == 0 or agg_ref[m] <= 0:
                agg_cells.append(f'{"-":>18}')
                continue
            delta = (agg_new[m] - agg_ref[m]) / agg_ref[m] * 100
            qual_drop = (agg_qual_ref[m] - agg_qual_new[m]) / agg_n[m]
            agg_cells.append(f'{delta:+7.1f}% [{_verdict(delta, qual_drop):<5}] ')
        print(f'{"AGGREGATE (scen-eq)":<22}{"".join(agg_cells)}')


def _print_response_size_ratio(results, scenarios, models):
    """Cleanest cross-run-stable compression metric.

    Independent of cache state — only measures how much smaller the visible
    response text is. 1.00 = same size; 0.50 = mormor responses half the
    size of baseline.
    """
    print('\n=== response-size ratio: mormor / baseline (vis_out only — cross-run friendly) ===')
    print(f'{"scenario":<22}' + ''.join(f'{m:>12}' for m in models))
    for s in scenarios:
        cells = []
        for m in models:
            b = _filter(results, scenario=s, variant='baseline', model=m)
            mr = _filter(results, scenario=s, variant='mormor', model=m)
            if not b or not mr:
                cells.append(f'{"-":>12}')
                continue
            b_vis = sum(r['visible_output_tokens'] for r in b) / len(b)
            m_vis = sum(r['visible_output_tokens'] for r in mr) / len(mr)
            ratio = m_vis / b_vis if b_vis > 0 else 0
            cells.append(f'{ratio:>11.2f} ')
        print(f'{s:<22}{"".join(cells)}')


def _print_quality_matrix(results, variants, models):
    print('\n=== mean quality score (1-5) by variant × model ===')
    print(f'{"variant":<22}' + ''.join(f'{m:>12}' for m in models))
    for variant in variants:
        cells = []
        for m in models:
            rs = _filter(results, variant=variant, model=m)
            cells.append(f'{_avg_quality(rs):>11.2f} ' if rs else f'{"-":>12}')
        print(f'{variant:<22}{"".join(cells)}')


def _print_q_per_kt_matrix(results, variants, models):
    # quality-per-kilotoken — headline efficiency metric. A variant that wins
    # on tokens but loses quality will show LOWER q/kt — caught automatically.
    print('\n=== quality per kilotoken (q/kt) by variant × model ===')
    print(f'{"variant":<22}' + ''.join(f'{m:>12}' for m in models))
    for variant in variants:
        cells = []
        for m in models:
            rs = _filter(results, variant=variant, model=m)
            cells.append(f'{_q_per_kt(rs):>11.3f} ' if rs else f'{"-":>12}')
        print(f'{variant:<22}{"".join(cells)}')


def _print_latency_matrix(results, variants, models):
    print('\n=== mean latency (sec) by variant × model ===')
    print(f'{"variant":<22}' + ''.join(f'{m:>12}' for m in models))
    for variant in variants:
        cells = []
        for m in models:
            rs = _filter(results, variant=variant, model=m)
            cells.append(f'{_avg_latency_ms(rs)/1000:>11.1f} ' if rs else f'{"-":>12}')
        print(f'{variant:<22}{"".join(cells)}')
