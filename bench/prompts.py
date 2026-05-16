"""Mormor benchmark — system prompts and label compliance.

Three system prompts are benchmarked side-by-side per scenario:
- BASELINE_SYSTEM:  bare "helpful agent" — no guidance; the true reference
- TERSE_SYSTEM:     one line of "be concise" — what a developer writes when they want brevity
- MORMOR_CHEATSHEET: loaded at startup from CHEATSHEET.md by `run.py`

The three points test the full cheatsheet (labels + compression + form + behavior + precedence)
against reasonable alternatives a developer would actually write. Baseline shows default model
behavior; terse shows what a single sentence of guidance buys; mormor is the whole protocol.
"""

import re


BASELINE_SYSTEM = 'You are a helpful agent.'


TERSE_SYSTEM = 'You are a helpful agent. Be concise. Lead with the answer.'


# Loaded from disk at startup by `run.py` via `load_cheatsheet()`.
MORMOR_CHEATSHEET = None


def load_cheatsheet(path):
    """Read the cheatsheet at `path` into MORMOR_CHEATSHEET. Returns the text."""
    global MORMOR_CHEATSHEET
    with open(path) as f:
        MORMOR_CHEATSHEET = f.read()
    return MORMOR_CHEATSHEET


def system_for(variant):
    """Return the system prompt string for a variant ('baseline'/'terse'/'mormor')."""
    return {
        'baseline': BASELINE_SYSTEM,
        'terse':    TERSE_SYSTEM,
        'mormor':   MORMOR_CHEATSHEET,
    }[variant]


# Production set is 6 labels — see CHEATSHEET.md for the canonical list.
MORMOR_LABELS = ('goal:', 'note:', 'case:', 'done:', 'ask:', 'test:')


# Match a Mormor label at the start of a line (after optional whitespace).
# Accepts three forms:
#   - bare       (`done: foo`)         — the historical form
#   - h3 heading (`### done:` ...)     — the v0.1.0 form from the cheatsheet
#   - backticked (`` `done:` ``)       — edge case some models produce; the
#                                         cheatsheet treats `code/paths/ids` as
#                                         backtick territory and a few models
#                                         spill into wrapping the label too
# Embedded-in-prose matches ("what was done:") are excluded because the label
# must be at line start (after optional whitespace and optional `###` prefix).
_LABEL_AT_LINE_START = re.compile(
    r'(?:^|\n)\s*(?:###\s+)?`?(?:' + '|'.join(re.escape(l) for l in MORMOR_LABELS) + r')'
)


# Match an atomic-form response per CHEATSHEET.md:40 — "just a number, yes/no,
# or status code with NO accompanying context: emit that value alone". The
# example at CHEATSHEET.md:50-53 is `42`. We accept the whole response being
# (optional whitespace) + (signed int/decimal | yes | no) + (optional terminal
# punctuation) + (optional whitespace). Anything else (e.g. "yes, because foo",
# "42 records", "200 OK") fails — it has accompanying context, so per the
# cheatsheet the response should have used `done:` + `note:` instead.
_ATOMIC_RESPONSE = re.compile(
    r'\A\s*(?:[-+]?\d+(?:\.\d+)?|yes|no)\s*[.!?]?\s*\Z',
    re.IGNORECASE,
)


def detect_mormor_format(text):
    """Binary: is the response in a Mormor-compliant form?

    Two shapes count as compliant per CHEATSHEET.md:
      - labeled — any of the 6 labels appears at line start (the common case)
      - atomic  — the entire response is a bare number, yes, or no
                  (allowed only when the prompt has no accompanying context;
                  the cheatsheet explicitly classifies "category + reason" as
                  multi-part, so this branch fires rarely in the current
                  scenario suite — included for cheatsheet-fidelity and
                  forward-compatibility if atomic-eligible prompts are added)
    """
    s = text or ''
    if _LABEL_AT_LINE_START.search(s):
        return 1
    if _ATOMIC_RESPONSE.match(s):
        return 1
    return 0
