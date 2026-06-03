"""Mormor benchmark — tunable knobs.

All configuration lives here. Edit values in this file to retarget models,
change runs-per-cell, or adjust cost weights without touching runner logic.

Mutable state notes:
- MODELS, RUNS, VARIANTS, ENABLED_SCENARIOS are mutated by `run.py` at startup
  in response to CLI flags (--smoke, --runs, --only-models, --only-variants,
  --only-scenarios). Engine and reporting modules read these at runtime, so
  CLI overrides propagate without function-signature changes.
"""

import os


# Models exercised in production runs. Each entry is (label, model_id):
# - label goes into the CSV `model` column and the run folder name
# - model_id is the string passed to the Claude Code SDK / CLI
#
# Production default is Opus + Sonnet. Haiku has been excluded:
# it's chatty (62–74% thinking overhead vs ~37–47% on the bigger models),
# introduces protocol-compliance noise, and prior runs showed its quality is
# more variable.
MODELS = [
    ('opus',   'claude-opus-4-8'),
    ('sonnet', 'claude-sonnet-4-6'),
]

# Used only when --smoke is passed. Single fast model for sanity checks.
SMOKE_MODEL = ('sonnet', 'claude-sonnet-4-6')

# Grader is held constant across model runs so quality is scored by a single
# arbiter — eliminates "judge-bias by model under test" risk.
GRADER_MODEL = 'claude-haiku-4-5-20251001'

# How many samples per (scenario, variant, model) cell. CLI --runs overrides.
RUNS = 5

# Three variants benchmarked side-by-side per scenario.
VARIANTS = ['baseline', 'terse', 'mormor']

# Scenarios run in this order. CLI --only-scenarios overrides.
ENABLED_SCENARIOS = [
    'single_round_trip',
    'branching',
    'multi_turn',
    'high_frequency',
    'delegated_chain',
]

# Cost weights approximating Anthropic public pricing. Lets us compute a
# cache-aware "billed" cost that is stable across runs (raw token sums are
# noisy because cache_read varies wildly between runs). Model-agnostic ratios.
# Source: https://docs.anthropic.com/en/docs/about-claude/pricing
COST_WEIGHTS = {
    'input':           1.0,
    'cache_creation':  1.25,   # small premium for creating cache
    'cache_read':      0.10,   # ~90% cheaper than fresh input
    'output':          5.0,    # output ~5x input cost
}

# Tools that Claude Code might auto-invoke through the SDK. The benchmark is a
# pure system+user → text-response test; any tool call would pollute metrics
# and burn turns. We deny-list by name (allow-list isn't supported by the SDK
# in the same shape).
DISALLOWED_TOOLS = [
    'Task', 'AskUserQuestion', 'Bash', 'Edit', 'Read', 'Write',
    'Glob', 'Grep', 'NotebookEdit', 'WebFetch', 'WebSearch',
    'Skill', 'TodoWrite', 'ScheduleWakeup',
    'EnterPlanMode', 'ExitPlanMode', 'EnterWorktree', 'ExitWorktree',
    'Monitor', 'TaskOutput', 'TaskStop',
    'PushNotification', 'RemoteTrigger',
    'CronCreate', 'CronDelete', 'CronList',
    'ToolSearch', 'ShareOnboardingGuide',
    'ListMcpResourcesTool', 'ReadMcpResourceTool',
]

# Where per-run folders are created. Override with --results-root.
DEFAULT_RESULTS_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'results',
)
