"""Mormor benchmark — engine: SDK calls, grading, scenario runners, CSV/folder I/O.

This module does the actual benchmarking work. Public entry point is `main()`,
called from `run.py` after CLI args have been parsed and config has been
mutated to reflect overrides (--runs, --only-models, etc.).

Sections:
- Run-folder helpers:   _Tee, _make_run_label, _make_run_dir, _write_meta_json
- SDK helpers:          make_options, extract_metrics, call_one_shot, call_multi_turn
- Grading:              _grade_with_prompt, grade, grade_with_history, grade_chain_hop
- Scenario runners:     run_repeated, run_multi_turn_scenario, run_delegated_chain
- CSV bookkeeping:      record, _save_incremental, _load_existing, _run_complete
- Orchestrator:         main

Resilience:
- Every SDK call retries up to 8x with exponential backoff + jitter.
- Every grader call retries up to 5x; if all retries fail the row gets
  quality_score=0 (visible as outlier in summary) instead of crashing.
- CSV is rewritten atomically after every row → safe against mid-write crashes;
  `--resume` re-reads the partial CSV and skips completed (scenario, variant,
  model, run_n) tuples.
"""

import csv
import datetime
import json
import os
import random
import socket
import time

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    query,
)

import config
import scenarios as scen
from prompts import system_for, detect_mormor_format


# ---------------------------------------------------------------------------
# Run-folder helpers
# ---------------------------------------------------------------------------

class Tee:
    """File-like wrapper that mirrors writes to multiple streams.

    Used to duplicate stdout/stderr to run.log while keeping the live console
    output intact. Failures on individual streams are swallowed — we never
    want a benchmark to die because the log file errored.
    """

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


def make_run_label(args, model_labels, system_prompt_label):
    """Build the descriptive suffix appended after the timestamp in the
    run-folder name. Encodes (model, system_prompt, smoke, label)."""
    parts = []
    if len(model_labels) == 1:
        parts.append(model_labels[0])
    elif len(model_labels) > 1:
        parts.append('multi')
    if system_prompt_label:
        parts.append(system_prompt_label)
    if getattr(args, 'smoke', False):
        parts.append('smoke')
    if getattr(args, 'label', None):
        # Sanitize: only [A-Za-z0-9_-]
        clean = ''.join(c if (c.isalnum() or c in '-_') else '-' for c in args.label)
        if clean:
            parts.append(clean)
    return '_'.join(parts) if parts else 'run'


def make_run_dir(results_root, run_label):
    """Create a uniquely-named folder under results_root and return its path.

    Folder name: `<YYYY-MM-DD>_<HH-MM-SS>_<run_label>`. If a folder with the
    same name already exists (multiple processes start in the same second),
    append `_2`, `_3`, etc., until unique.
    """
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y-%m-%d_%H-%M-%S')
    base = f'{timestamp}_{run_label}'
    dir_path = os.path.join(results_root, base)
    n = 1
    while os.path.exists(dir_path):
        n += 1
        dir_path = os.path.join(results_root, f'{base}_{n}')
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def write_meta_json(run_dir, args, model_ids, system_prompt_path,
                    system_prompt_chars, started_at, finished_at,
                    n_rows, n_grader_zero, exit_status):
    """Write meta.json snapshotting the config that produced this run."""
    meta = {
        'started_at':          started_at,
        'finished_at':         finished_at,
        'host':                socket.gethostname(),
        'args':                vars(args),
        'model_ids':           model_ids,
        'system_prompt_path':  system_prompt_path,
        'system_prompt_chars': system_prompt_chars,
        'rows_total':          n_rows,
        'rows_grader_zero':    n_grader_zero,
        'exit_status':         exit_status,
    }
    with open(os.path.join(run_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# SDK helpers
# ---------------------------------------------------------------------------

def make_options(system_prompt, model):
    """Minimal Claude Code config: no tools, no settings files, single-turn.

    Best-effort: passes effort='low' to suppress extended thinking
    (which on smaller models produces 100-300 hidden output tokens for
    trivial one-word answers). Older SDK versions don't accept this kwarg —
    we fall back gracefully.
    """
    base = dict(
        system_prompt=system_prompt,
        model=model,
        setting_sources=[],
        disallowed_tools=config.DISALLOWED_TOOLS,
        max_turns=1,
    )
    try:
        return ClaudeAgentOptions(**base, effort='low')
    except TypeError:
        return ClaudeAgentOptions(**base)


def extract_metrics(messages, latency_ms):
    """Pull response_text + usage tokens out of a returned message stream."""
    response_text = ''
    usage = {}
    for m in messages:
        if isinstance(m, AssistantMessage):
            for block in m.content:
                if isinstance(block, TextBlock):
                    response_text += block.text
        elif isinstance(m, ResultMessage):
            usage = m.usage or {}
    return {
        'response_text': response_text,
        'input_tokens': usage.get('input_tokens', 0),
        'output_tokens': usage.get('output_tokens', 0),
        'cache_read_tokens': usage.get('cache_read_input_tokens', 0),
        'cache_creation_tokens': usage.get('cache_creation_input_tokens', 0),
        'latency_ms': latency_ms,
    }


def _retry_wait(attempt):
    """Exponential backoff with jitter, capped at 90s."""
    base = min(90, 8 * (2 ** attempt))
    return base + random.uniform(0, base * 0.3)


async def call_one_shot(system_prompt, user_msg, model_id, max_retries=8):
    """Single-turn call with retry on transient SDK/API failures.

    The SDK occasionally raises "Command failed with exit code 1" on a single
    call — usually transient. Without retries that single hiccup kills the
    whole 5h benchmark and loses any uncommitted in-memory data.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            start = time.time()
            messages = []
            async for m in query(prompt=user_msg, options=make_options(system_prompt, model_id)):
                messages.append(m)
            latency_ms = int((time.time() - start) * 1000)
            return extract_metrics(messages, latency_ms)
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = _retry_wait(attempt)
                print(f'   [call failed ({type(e).__name__}); retry {attempt+1}/{max_retries-1} in {wait:.1f}s]', flush=True)
                await anyio.sleep(wait)
    raise last_exc


async def call_multi_turn(system_prompt, user_msgs, model_id, max_retries=8):
    """Stateful multi-turn session. Retries the WHOLE session on failure
    (cannot resume from a mid-session crash since SDK state is gone)."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            results = []
            async with ClaudeSDKClient(options=make_options(system_prompt, model_id)) as client:
                for user_msg in user_msgs:
                    start = time.time()
                    await client.query(user_msg)
                    messages = []
                    async for m in client.receive_response():
                        messages.append(m)
                    latency_ms = int((time.time() - start) * 1000)
                    results.append(extract_metrics(messages, latency_ms))
            return results
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = _retry_wait(attempt)
                print(f'   [call_multi_turn failed ({type(e).__name__}); retry {attempt+1}/{max_retries-1} in {wait:.1f}s]', flush=True)
                await anyio.sleep(wait)
    raise last_exc


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

async def _grade_with_prompt(grading_prompt, max_retries=5):
    """Common grader call. Returns int 1-5 or 0 on parse / exhaustion failure.

    Retries on transient SDK errors so a single grader hiccup doesn't kill a
    long benchmark run. The grader is stateless per-call → safe to retry the
    whole call.
    """
    options = ClaudeAgentOptions(
        system_prompt='You are a strict grader. Reply with a single digit 1-5 and nothing else.',
        model=config.GRADER_MODEL,
        setting_sources=[],
        disallowed_tools=config.DISALLOWED_TOOLS,
        max_turns=1,
    )

    last_exc = None
    for attempt in range(max_retries):
        try:
            text = ''
            async for m in query(prompt=grading_prompt, options=options):
                if isinstance(m, AssistantMessage):
                    for block in m.content:
                        if isinstance(block, TextBlock):
                            text += block.text
            text = text.strip()
            try:
                return int(text[0])
            except (ValueError, IndexError):
                return 0
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = _retry_wait(attempt)
                print(f'   [grader failed ({type(e).__name__}); retry {attempt+1}/{max_retries-1} in {wait:.1f}s]', flush=True)
                await anyio.sleep(wait)
    # All retries exhausted — return 0 (parse-failure sentinel) rather than
    # crashing the whole benchmark. Quality stats will show 0 as a clear
    # outlier in the summary.
    print(f'   [grader exhausted retries: {last_exc!r} — recording score=0]', flush=True)
    return 0


async def grade(task, response_text, scenario=None, expected=None):
    """Single-shot grading.

    Uses a per-scenario rubric when available; high_frequency uses an
    exact-category-match rubric driven by `expected`; otherwise falls back
    to a generic 1-5 correctness prompt.
    """
    if scenario == 'high_frequency' and expected:
        rubric = (
            f'You are grading a response that was asked to categorize an email '
            f'subject AND provide a one-line reason. The CORRECT category is '
            f'exactly: {expected}\n\n'
            f'Score 5 if the response correctly identifies the category as '
            f'"{expected}" (case-insensitive) AND includes a brief reason/explanation.\n'
            f'Score 4 if correct category but no reason.\n'
            f'Score 3 if ambiguous between categories.\n'
            f'Score 1 if it gives any other category.\n\n'
            f'Reply with ONLY a single digit 1-5.'
        )
    elif scenario in scen.SCENARIO_RUBRICS:
        rubric = scen.SCENARIO_RUBRICS[scenario]
    else:
        rubric = (
            'Score this agent response 1-5 on whether it correctly addresses the task.\n'
            '5 = fully correct and complete\n'
            '3 = partially addresses the task\n'
            '1 = irrelevant or wrong\n\n'
            'Reply with ONLY a single digit 1-5.'
        )

    prompt = f'''{rubric}

TASK:
{task}

RESPONSE:
{response_text}'''
    return await _grade_with_prompt(prompt)


async def grade_with_history(prior_turns, current_user, response_text):
    """Grade a multi-turn response with the conversation context the agent saw.

    Without context the grader penalizes short replies that are perfectly
    valid given prior turns (e.g. Mormor's `done: applied fix` looks like a
    non-answer if you don't know what was just asked). `prior_turns` is a
    list of {'user': ..., 'assistant': ...} dicts for completed earlier
    turns; `current_user` is the latest user message; `response_text` is the
    reply being scored.
    """
    if prior_turns:
        history_lines = []
        for t in prior_turns:
            history_lines.append(f'USER: {t["user"]}')
            history_lines.append(f'ASSISTANT: {t["assistant"]}')
        history_section = 'CONVERSATION SO FAR:\n' + '\n\n'.join(history_lines) + '\n\n'
    else:
        history_section = ''

    prompt = f'''Score this agent response 1-5 on whether it correctly addresses the LATEST user message in the context of the full conversation.
5 = fully correct and complete
3 = partially addresses the message
1 = irrelevant or wrong

A short reply can score 5 if it is a complete and correct answer in context (e.g. acknowledging an instruction, reporting completion, asking a clarifying question when ambiguity is genuine).

{history_section}LATEST USER MESSAGE:
{current_user}

LATEST AGENT RESPONSE (grade this):
{response_text}

Reply with ONLY a single digit 1-5.'''
    return await _grade_with_prompt(prompt)


async def grade_chain_hop(hop_idx, hop_input, response_text):
    """Grade a single hop in the delegated_chain scenario with its per-hop rubric."""
    rubric = scen.CHAIN_HOP_RUBRICS[hop_idx]
    prompt = f'''{rubric}

INPUT TO THIS AGENT (the prior message it received):
{hop_input}

RESPONSE FROM THIS AGENT (grade this):
{response_text}'''
    return await _grade_with_prompt(prompt)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record(scenario, variant, model_label, run_n, turn, metrics, score):
    """Build one CSV row from a metrics dict + quality score.

    visible_output_tokens approximates the size of the actual displayed
    response text. The SDK's output_tokens INCLUDES extended-thinking
    tokens (some models think before responding by default). Subtracting
    visible from output gives a rough thinking_overhead estimate.

    Approximation note: `len(text) // 4` is the English-prose folk
    heuristic (~4 chars/token). Real BPE tokenizers count differently for
    label-dense or code-dense content (more punctuation tokens, shorter
    identifier tokens). An offline probe against this benchmark's
    response_text showed the heuristic OVER-counts by ~3-7% across all
    three variants (baseline 1.07, terse 1.03, mormor 1.04 vs a
    words+punct proxy), with per-scenario variance in both directions but
    roughly uniform between variants within each scenario. Net effect:
    the mormor/baseline `vis_out_ratio` is robust to within a few percent
    of the "true" tokenizer ratio.
    """
    visible_output = len(metrics['response_text']) // 4
    return {
        'scenario': scenario,
        'variant': variant,
        'model': model_label,
        'run_n': run_n,
        'turn': turn,
        'input_tokens': metrics['input_tokens'],
        'output_tokens': metrics['output_tokens'],
        'visible_output_tokens': visible_output,
        'cache_read_tokens': metrics['cache_read_tokens'],
        'cache_creation_tokens': metrics['cache_creation_tokens'],
        'latency_ms': metrics['latency_ms'],
        'quality_score': score,
        'format_compliance': detect_mormor_format(metrics['response_text']),
        'response_text': metrics['response_text'],
    }


def save_incremental(results, path):
    """Write CSV atomically: tmp file + rename. Safe against mid-write crashes."""
    if not results:
        return
    tmp = path + '.tmp'
    fields = list(results[0].keys())
    with open(tmp, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)
    os.replace(tmp, path)


def load_existing(path):
    """Re-read partial CSV from a previous crash so we can resume.

    Returns a list of dict rows in the same shape `record()` produces. If
    the CSV doesn't exist, returns []. Numeric fields are coerced back to
    int so downstream summary code works without changes.

    Duplicate rows for the same (scenario, variant, model, run_n, turn) are
    collapsed with last-write-wins. Older versions of the runner could leave
    such duplicates behind: if a crash interrupted a run_n with N of M turns
    saved, the next resume re-executed from turn 0 and appended a fresh M
    rows on top of the partial N, inflating aggregates. Newer runs use the
    in-memory purge below to avoid producing duplicates in the first place;
    this dedup salvages any CSVs already poisoned by the old behaviour.
    """
    if not os.path.exists(path):
        return []
    int_fields = (
        'run_n', 'turn', 'input_tokens', 'output_tokens',
        'visible_output_tokens', 'cache_read_tokens',
        'cache_creation_tokens', 'latency_ms', 'quality_score',
        'format_compliance',
    )
    deduped = {}
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            for k in int_fields:
                if k in r and r[k] != '':
                    try:
                        r[k] = int(r[k])
                    except ValueError:
                        pass
            key = (r['scenario'], r['variant'], r['model'],
                   r.get('run_n'), r.get('turn'))
            if key in deduped:
                del deduped[key]
            deduped[key] = r
    return list(deduped.values())


def _run_complete(scenario, variant, model_label, run_n, all_results):
    """True if (scenario, variant, model, run_n) has all expected rows in the CSV."""
    expected = scen.EXPECTED_ROWS_PER_RUN[scenario]
    have = sum(
        1 for r in all_results
        if r['scenario'] == scenario
        and r['variant'] == variant
        and r['model'] == model_label
        and int(r['run_n']) == run_n
    )
    return have >= expected


def _purge_partial(all_results, scenario, variant, model_label, run_n):
    """Drop in-memory rows for (scenario, variant, model, run_n).

    Called when `_run_complete` is False, just before a runner re-executes
    the tuple from turn 0. Without this, the partial rows from a prior
    crashed run would linger in `all_results` and be double-counted alongside
    the freshly re-run rows. CSV is not rewritten here — the next
    `save_incremental` writes the cleaned list anyway, and a crash before
    that save just leaves the same partial state for the next resume to
    purge again (idempotent).
    """
    all_results[:] = [
        r for r in all_results
        if not (r['scenario'] == scenario
                and r['variant'] == variant
                and r['model'] == model_label
                and int(r['run_n']) == run_n)
    ]


# ---------------------------------------------------------------------------
# Scenario runners
# ---------------------------------------------------------------------------

async def run_repeated(scenario, variant, model_label, model_id, all_results, save_path):
    """One-shot scenario runner.

    Persists the CSV after every single call so a crash loses at most one
    call's data. Used for single_round_trip, branching, high_frequency.
    """
    sys_prompt = system_for(variant)
    sc = scen.SCENARIOS[scenario]

    if 'user_template' in sc:
        # high_frequency: template + per-subject inputs.
        prompts_meta = [
            (sc['user_template'].replace('__SUBJECT__', subj), expected)
            for subj, expected in sc['inputs']
        ]
    else:
        # single_round_trip, branching: single user prompt, no expected value.
        prompts_meta = [(sc['user'], None)]

    for run_n in range(config.RUNS):
        if _run_complete(scenario, variant, model_label, run_n, all_results):
            continue  # resume: this run is already in the CSV
        _purge_partial(all_results, scenario, variant, model_label, run_n)
        for iter_n, (user_msg, expected) in enumerate(prompts_meta):
            metrics = await call_one_shot(sys_prompt, user_msg, model_id)
            score = await grade(user_msg, metrics['response_text'],
                                scenario=scenario, expected=expected)
            all_results.append(record(scenario, variant, model_label, run_n, iter_n, metrics, score))
            save_incremental(all_results, save_path)


async def run_multi_turn_scenario(variant, model_label, model_id, all_results, save_path):
    """Multi-turn scenario runner.

    All 5 turns happen inside a single SDK session. CSV saved after every
    turn is graded. If a session crashes mid-run we lose the in-progress run
    only; completed turns of earlier runs are persisted.
    """
    sys_prompt = system_for(variant)
    turns = scen.SCENARIOS['multi_turn']['turns']

    for run_n in range(config.RUNS):
        if _run_complete('multi_turn', variant, model_label, run_n, all_results):
            continue  # resume
        _purge_partial(all_results, 'multi_turn', variant, model_label, run_n)
        per_turn = await call_multi_turn(sys_prompt, turns, model_id)
        prior = []
        for turn_idx, (user_msg, metrics) in enumerate(zip(turns, per_turn)):
            score = await grade_with_history(prior, user_msg, metrics['response_text'])
            all_results.append(record('multi_turn', variant, model_label, run_n, turn_idx, metrics, score))
            save_incremental(all_results, save_path)
            prior.append({'user': user_msg, 'assistant': metrics['response_text']})


async def run_delegated_chain(variant, model_label, model_id, all_results, save_path):
    """Five-hop fan-out delegation runner.

       hop 0: parent → security-child brief
       hop 1: parent → quality-child brief
       hop 2: security child reviews   (input = hop 0 output)
       hop 3: quality child reviews    (input = hop 1 output)
       hop 4: parent synthesizes both reports

    Each hop is graded with its own per-hop rubric (CHAIN_HOP_RUBRICS).
    Compression compounds across hops — output of hops 0+1 becomes input of
    hops 2+3; output of hops 2+3 becomes input of hop 4.
    """
    sys_prompt = system_for(variant)
    sc = scen.SCENARIOS['delegated_chain']
    task = scen.DELEGATED_CHAIN_TASK

    for run_n in range(config.RUNS):
        if _run_complete('delegated_chain', variant, model_label, run_n, all_results):
            continue  # resume
        _purge_partial(all_results, 'delegated_chain', variant, model_label, run_n)

        # Hop 0: parent → security-child brief
        p0 = sc['assign_security'].replace('__TASK__', task)
        m0 = await call_one_shot(sys_prompt, p0, model_id)
        s0 = await grade_chain_hop(0, p0, m0['response_text'])
        all_results.append(record('delegated_chain', variant, model_label, run_n, 0, m0, s0))
        save_incremental(all_results, save_path)

        # Hop 1: parent → quality-child brief
        p1 = sc['assign_quality'].replace('__TASK__', task)
        m1 = await call_one_shot(sys_prompt, p1, model_id)
        s1 = await grade_chain_hop(1, p1, m1['response_text'])
        all_results.append(record('delegated_chain', variant, model_label, run_n, 1, m1, s1))
        save_incremental(all_results, save_path)

        # Hop 2: security child reviews (input = parent's hop 0 output)
        m2 = await call_one_shot(sys_prompt, m0['response_text'], model_id)
        s2 = await grade_chain_hop(2, m0['response_text'], m2['response_text'])
        all_results.append(record('delegated_chain', variant, model_label, run_n, 2, m2, s2))
        save_incremental(all_results, save_path)

        # Hop 3: quality child reviews (input = parent's hop 1 output)
        m3 = await call_one_shot(sys_prompt, m1['response_text'], model_id)
        s3 = await grade_chain_hop(3, m1['response_text'], m3['response_text'])
        all_results.append(record('delegated_chain', variant, model_label, run_n, 3, m3, s3))
        save_incremental(all_results, save_path)

        # Hop 4: parent synthesizes both reports
        p4 = (sc['synthesize']
              .replace('__TASK__', task)
              .replace('__SECURITY_REPORT__', m2['response_text'])
              .replace('__QUALITY_REPORT__', m3['response_text']))
        m4 = await call_one_shot(sys_prompt, p4, model_id)
        # Grader receives p4 (the synthesize prompt with both child reports
        # interpolated) rather than `task` so it can evaluate criterion 5
        # ("reads as a unified review … combines both reviewers' findings")
        # against the actual material hop 4 was asked to combine.
        s4 = await grade_chain_hop(4, p4, m4['response_text'])
        all_results.append(record('delegated_chain', variant, model_label, run_n, 4, m4, s4))
        save_incremental(all_results, save_path)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def main(output_csv):
    """Top-level benchmark loop. Iterates models × variants × scenarios.

    Reads config.MODELS / config.VARIANTS / config.ENABLED_SCENARIOS — these
    are mutated by `run.py` based on CLI flags before main() is called.

    Returns the accumulated results list.
    """
    # Resume support: load any partial CSV from a prior crashed run, then
    # let each runner skip (scenario, variant, model, run_n) tuples already
    # complete. Cheap insurance against rate-limit blowouts in long runs.
    all_results = load_existing(output_csv)
    if all_results:
        print(f'### RESUME: loaded {len(all_results)} prior rows from {output_csv} ###', flush=True)

    for model_label, model_id in config.MODELS:
        print(f'\n##### MODEL: {model_label} ({model_id}) #####', flush=True)
        for variant in config.VARIANTS:
            for scenario in ('single_round_trip', 'branching'):
                if scenario not in config.ENABLED_SCENARIOS:
                    continue
                print(f'-- {scenario} / {variant} / {model_label}', flush=True)
                await run_repeated(scenario, variant, model_label, model_id, all_results, output_csv)

            if 'multi_turn' in config.ENABLED_SCENARIOS:
                print(f'-- multi_turn / {variant} / {model_label}', flush=True)
                await run_multi_turn_scenario(variant, model_label, model_id, all_results, output_csv)

            if 'high_frequency' in config.ENABLED_SCENARIOS:
                print(f'-- high_frequency / {variant} / {model_label}', flush=True)
                await run_repeated('high_frequency', variant, model_label, model_id, all_results, output_csv)

            if 'delegated_chain' in config.ENABLED_SCENARIOS:
                print(f'-- delegated_chain / {variant} / {model_label}', flush=True)
                await run_delegated_chain(variant, model_label, model_id, all_results, output_csv)

            print(f'   [checkpoint: {len(all_results)} rows persisted]', flush=True)

    return all_results
