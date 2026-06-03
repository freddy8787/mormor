"""Mormor benchmark — entry point.

Usage:
    python run.py                              # opus + sonnet, RUNS=5 (~3–4h)
    python run.py --smoke                      # quick sanity check (~10 min)
    python run.py --runs 20                    # canonical run (tighter CIs)
    python run.py --only-models sonnet         # one model
    python run.py --only-scenarios multi_turn  # one or more scenarios
    python run.py --only-variants mormor       # one or more variants — split a
                                               # canonical run across parallel
                                               # processes (one per variant)
    python run.py --system-prompt-file path.md # try a candidate cheatsheet
    python run.py --resume <run_dir>           # continue a partial run

Output: a per-run folder under bench/results/ containing
    benchmark.csv  — one row per (scenario, variant, model, run_n, turn)
    run.log        — live tee of stdout/stderr
    summary.txt    — final aggregate tables
    meta.json      — config snapshot, host, timestamps, exit status

Requires `claude_agent_sdk`, Python 3.10+, and the `claude` CLI installed and
authenticated. Routes through your Claude Code subscription — no API key needed.
"""

import argparse
import datetime
import io
import os
import sys

import anyio

import config
import engine
import prompts
import reporting


def _build_parser():
    p = argparse.ArgumentParser(description='Mormor benchmark runner.')
    p.add_argument(
        '--smoke', action='store_true',
        help='Quick test: 1 run, sonnet only, baseline+mormor variants only.',
    )
    p.add_argument(
        '--only-scenarios',
        help='Comma-separated scenario names to run (e.g. multi_turn). '
             'Defaults to all five.',
    )
    p.add_argument(
        '--only-models',
        help='Comma-separated model labels to run (e.g. sonnet,opus). '
             'Defaults to config.MODELS (opus + sonnet).',
    )
    p.add_argument(
        '--only-variants',
        help='Comma-separated variant names to run (e.g. baseline,terse). '
             'Defaults to config.VARIANTS (baseline + terse + mormor). '
             'Useful for splitting a canonical run across multiple parallel '
             'processes — each process runs one variant.',
    )
    p.add_argument(
        '--runs', type=int,
        help='Override config.RUNS (default 5, or 1 in --smoke mode).',
    )
    p.add_argument(
        '--system-prompt', choices=('cheatsheet',), default='cheatsheet',
        help='Mormor system prompt source. "cheatsheet" (default) loads the '
             'curated default frozen version (../cheatsheets/<DEFAULT>.md). '
             'Use --system-prompt-file for arbitrary paths (e.g. when '
             'comparing candidate revisions).',
    )
    p.add_argument(
        '--system-prompt-file',
        help='Path to a custom file to use as the mormor system prompt. '
             'Overrides --system-prompt. Useful for testing candidate '
             'cheatsheets. The file basename (without extension) becomes '
             'the system-prompt label in the run folder name.',
    )
    p.add_argument(
        '--results-root',
        default=config.DEFAULT_RESULTS_ROOT,
        help=f'Where per-run folders are created. Default: {config.DEFAULT_RESULTS_ROOT}',
    )
    p.add_argument(
        '--resume',
        help='Path to an existing run folder to continue. Re-uses the '
             'benchmark.csv inside it; new rows are appended.',
    )
    p.add_argument(
        '--label',
        help='Free-form suffix to append to the run-folder name. Useful for '
             'tagging ad-hoc experiments. Sanitized to [A-Za-z0-9_-].',
    )
    return p


def _resolve_system_prompt(args, parser):
    """Resolve and load the mormor system prompt.

    Returns (path, label). Sets prompts.MORMOR_CHEATSHEET as a side effect.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    if args.system_prompt_file:
        path = os.path.abspath(args.system_prompt_file)
        label = os.path.splitext(os.path.basename(path))[0]
    else:
        # Load the cheatsheet version named in cheatsheets/DEFAULT (the
        # recommended pick); the existence check below reports a clear error
        # if the cheatsheets/ layout is missing.
        ver = 'v1'
        default_ptr = os.path.join(project_root, 'cheatsheets', 'DEFAULT')
        if os.path.exists(default_ptr):
            with open(default_ptr) as f:
                ver = f.read().strip() or ver
        path = os.path.join(project_root, 'cheatsheets', f'{ver}.md')
        label = 'cheatsheet'

    if not os.path.exists(path):
        parser.error(f'system prompt file not found at {path!r}')

    prompts.load_cheatsheet(path)
    return path, label


def _apply_cli_overrides(args, parser):
    """Mutate config to reflect --smoke / --runs / --only-* flags."""
    if args.smoke:
        config.MODELS = [config.SMOKE_MODEL]
        config.RUNS = 1
        config.VARIANTS = ['baseline', 'mormor']
    if args.runs is not None:
        config.RUNS = args.runs
    if args.only_scenarios:
        config.ENABLED_SCENARIOS = [s.strip() for s in args.only_scenarios.split(',')]
    if args.only_models:
        wanted = {m.strip() for m in args.only_models.split(',')}
        config.MODELS = [m for m in config.MODELS if m[0] in wanted]
        if not config.MODELS:
            parser.error(f'--only-models: no MODELS matched {sorted(wanted)} (known: opus, sonnet)')
    if args.only_variants:
        wanted = [v.strip() for v in args.only_variants.split(',')]
        unknown = [v for v in wanted if v not in config.VARIANTS]
        if unknown:
            parser.error(f'--only-variants: unknown variant(s) {unknown} (known: {config.VARIANTS})')
        config.VARIANTS = [v for v in config.VARIANTS if v in wanted]


def _print_banner(run_dir, resumed, system_prompt_path, system_prompt_label, args):
    print(f'### RUN DIR: {run_dir}{"  (RESUMED)" if resumed else ""} ###')
    print(f'### SYSTEM PROMPT: label={system_prompt_label}, path={system_prompt_path}, '
          f'len={len(prompts.MORMOR_CHEATSHEET)} chars ###')
    if args.smoke:
        print(f'### SMOKE MODE: RUNS={config.RUNS}, models={[m[0] for m in config.MODELS]}, '
              f'variants={config.VARIANTS} ###')
    if args.runs is not None:
        print(f'### RUNS override: RUNS={config.RUNS} ###')
    if args.only_scenarios:
        print(f'### ONLY SCENARIOS: {config.ENABLED_SCENARIOS} ###')
    if args.only_models:
        print(f'### ONLY MODELS: {[m[0] for m in config.MODELS]} ###')


def _write_summary_txt(run_dir, output_csv):
    """Re-load CSV and dump summary.txt — even on partial / failed runs."""
    rows = engine.load_existing(output_csv) if os.path.exists(output_csv) else []
    n_rows = len(rows)
    n_grader_zero = sum(1 for r in rows if int(r.get('quality_score', 0) or 0) == 0)
    if rows:
        buf = io.StringIO()
        saved_stdout = sys.stdout
        sys.stdout = engine.Tee(buf)  # capture only, don't echo to run.log again
        try:
            reporting.print_summary(rows)
        finally:
            sys.stdout = saved_stdout
        with open(os.path.join(run_dir, 'summary.txt'), 'w') as f:
            f.write(buf.getvalue())
    return n_rows, n_grader_zero


def main():
    parser = _build_parser()
    args = parser.parse_args()

    # 1. Resolve and load the mormor system prompt.
    system_prompt_path, system_prompt_label = _resolve_system_prompt(args, parser)

    # 2. Apply CLI overrides to config (--smoke / --runs / --only-*).
    _apply_cli_overrides(args, parser)
    model_labels = [m[0] for m in config.MODELS]

    # 3. Create or resume the per-run folder.
    if args.resume:
        run_dir = os.path.abspath(args.resume)
        if not os.path.isdir(run_dir):
            parser.error(f'--resume: not a directory: {run_dir!r}')
        resumed = True
    else:
        run_label = engine.make_run_label(args, model_labels, system_prompt_label)
        run_dir = engine.make_run_dir(args.results_root, run_label)
        resumed = False

    output_csv = os.path.join(run_dir, 'benchmark.csv')

    # 4. Tee stdout/stderr to run.log so the live console and the saved log match.
    log_path = os.path.join(run_dir, 'run.log')
    log_file = open(log_path, 'a', buffering=1)  # line-buffered
    sys.stdout = engine.Tee(sys.__stdout__, log_file)
    sys.stderr = engine.Tee(sys.__stderr__, log_file)

    _print_banner(run_dir, resumed, system_prompt_path, system_prompt_label, args)

    # 5. Execute the benchmark and capture summary into summary.txt.
    started_at = datetime.datetime.now().isoformat(timespec='seconds')
    exit_status = 'completed'
    try:
        all_results = anyio.run(engine.main, output_csv)
        print(f'\nwrote {len(all_results)} rows to {output_csv}\n')
        reporting.print_summary(all_results)
    except KeyboardInterrupt:
        exit_status = 'interrupted'
        print('\n### INTERRUPTED ###')
    except Exception as e:
        exit_status = f'failed: {type(e).__name__}: {e}'
        print(f'\n### FAILED: {e} ###')
    finally:
        finished_at = datetime.datetime.now().isoformat(timespec='seconds')

        try:
            n_rows, n_grader_zero = _write_summary_txt(run_dir, output_csv)
        except Exception as e:
            print(f'### summary capture failed: {e} ###')
            n_rows, n_grader_zero = 0, 0

        engine.write_meta_json(
            run_dir=run_dir,
            args=args,
            model_ids=config.MODELS,
            system_prompt_path=system_prompt_path,
            system_prompt_chars=len(prompts.MORMOR_CHEATSHEET) if prompts.MORMOR_CHEATSHEET else 0,
            started_at=started_at,
            finished_at=finished_at,
            n_rows=n_rows,
            n_grader_zero=n_grader_zero,
            exit_status=exit_status,
        )
        print(f'### artifacts: {run_dir} ###')
        log_file.close()


if __name__ == '__main__':
    main()
