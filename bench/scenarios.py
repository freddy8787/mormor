"""Mormor benchmark — workloads and grading rubrics.

Every scenario uses a SINGLE user prompt across all three variants. Only the
system prompt differs (baseline / terse / mormor). This isolates the
protocol's contribution: equal input → measure how the system prompt shapes
the output.

Scenarios:
- single_round_trip  — single-shot planning task
- branching          — security review (decision-table use case)
- multi_turn         — 5-turn debugging conversation
- high_frequency     — 5 atomic email classifications
- delegated_chain    — 5-hop fan-out PR review (parent → 2 children → parent)
"""


# The fixed task that drives the delegated_chain scenario. 5-hop fan-out:
# parent dispatches to a security reviewer AND a code-quality reviewer
# (2 separate briefs), each child produces a specialist review, parent
# synthesizes both into a unified PR review with merge recommendation.
DELEGATED_CHAIN_TASK = '''Pull request review request — the developer wants this function reviewed before merging:

```python
def process_user(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        return user[0]
    return None
```

Run this through your security reviewer AND your code-quality reviewer, then give a final merge recommendation.'''


# Each scenario has a SINGLE user prompt (`user` / `user_template` / `turns`
# / chain-hop templates). The same string is sent to all three variants — only
# the system prompt differs. Templates use placeholders the runner replaces:
# - high_frequency:    __SUBJECT__         → email subject string from 'inputs'
# - delegated_chain:   __TASK__            → DELEGATED_CHAIN_TASK
#                      __SECURITY_REPORT__ → hop 2 output
#                      __QUALITY_REPORT__  → hop 3 output
SCENARIOS = {
    'single_round_trip': {
        'user': '''Planning the REST API for a simple todo list app. Single user (no auth yet), each todo has title + done flag + optional due_date. Map out the endpoints.''',
    },

    'high_frequency': {
        'user_template': '''Classify this email subject (transactional / marketing / personal / spam) + one-line reason:

"__SUBJECT__"''',
        'inputs': [
            ('Your order #12345 has shipped', 'transactional'),
            ('FLASH SALE: 50% off everything ends tonight!', 'marketing'),
            ('Hey, can we grab coffee tomorrow?', 'personal'),
            ('CONGRATULATIONS WINNER! Claim your $1000 prize NOW', 'spam'),
            ('Your monthly statement is ready', 'transactional'),
        ],
    },

    'branching': {
        'user': '''Security review of this function. Categorize each finding:
- must-fix → block merge
- should-fix → comment, no block
- nit → skip / optional

```python
def process_user(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        return user[0]
    return None
```''',
    },

    'multi_turn': {
        'turns': [
            'Test passing locally but flaking in CI — `tests/test_pipeline.py` fails ~30% of runs, different assertions each time. How do I track this down?',
            'Reran in CI 50 times — fails on different assertions, not always the same one. Could be ordering or shared state?',
            'Ran the failing test in isolation — passes 100%. Only flakes when run as part of the full suite. So another test is leaving state behind.',
            'Found it: an earlier test leaves a row in the DB; my test assumes the table is empty. Should I add cleanup or use transactions?',
            'Going with transactions. Can you sketch the pytest fixture?',
        ],
    },

    'delegated_chain': {
        # 5-hop fan-out:
        #   hop 0: parent → security-child brief    (assign_security)
        #   hop 1: parent → quality-child brief     (assign_quality)
        #   hop 2: security child reviews           (input = hop 0 output)
        #   hop 3: quality child reviews            (input = hop 1 output)
        #   hop 4: parent synthesizes both reports  (synthesize)
        'assign_security': '''You're a parent agent dispatching a PR review to specialists. Forward the task below to your security reviewer with any context they'll need. Output only the message to the security child.

USER TASK:
__TASK__''',

        'assign_quality': '''You're a parent agent dispatching a PR review to specialists. Forward the task below to your code-quality reviewer with any context they'll need. Output only the message to the quality child.

USER TASK:
__TASK__''',

        'synthesize': '''Both specialist reviewers have reported back. Synthesize a final unified PR review with a merge recommendation.

USER TASK:
__TASK__

SECURITY REVIEWER REPORT:
__SECURITY_REPORT__

CODE-QUALITY REVIEWER REPORT:
__QUALITY_REPORT__''',
    },
}


# Number of rows a single (scenario, variant, model, run_n) is expected to
# produce. Used by --resume logic to detect "this run is already complete in
# the CSV → skip it".
EXPECTED_ROWS_PER_RUN = {
    'single_round_trip': 1,
    'branching':         1,
    'multi_turn':        5,   # 5 turns
    'high_frequency':    5,   # 5 input emails
    'delegated_chain':   5,   # 5 hops (parent → 2 children fan-out → parent synthesize)
}


# Per-scenario rubrics — each grades 5 specific factual checks worth 1 point,
# so the 1-5 score measures criteria-met-count, not vague "correctness".
SCENARIO_RUBRICS = {
    'single_round_trip': '''Score 1-5 by counting how many of these criteria the response addresses (1 point each):
(1) lists 5 endpoints covering CRUD (list, get-one, create, update, delete) for the todo resource
(2) maps correct HTTP methods to each endpoint (GET for list+get-one, POST for create, PUT or PATCH for update, DELETE for delete)
(3) uses a consistent resource path (e.g. `/todos` for collection, `/todos/{id}` for single item)
(4) mentions reasonable success status codes (e.g. 200 OK, 201 Created for POST, 204 No Content for DELETE)
(5) acknowledges JSON request/response shapes — body for POST/PUT/PATCH, response for GET

Be strict. If a criterion is not addressed, do not award the point. Reply with ONLY a single digit 1-5.''',

    'branching': '''Score 1-5 by counting how many of these criteria the response addresses (1 point each):
(1) identifies the SQL injection vulnerability in the function (string interpolation into the SQL query)
(2) recommends parameterized queries / prepared statements as the fix
(3) classifies the SQL injection at must-fix severity (or equivalent block-merge category)
(4) identifies at least one secondary security finding (input-type validation, error-handling info leak, missing length/null guard, or similar — the secondary issue must be security-related)
(5) does NOT classify the SQL injection as `nit` or `should-fix`

Be strict. Reply with ONLY a single digit 1-5.''',

    'delegated_chain': '''Score 1-5 by counting how many of these criteria the final synthesized PR review addresses (1 point each):
(1) identifies the SQL injection in `db.query(f"...")` as a security issue
(2) classifies SQL injection as a must-fix / merge-blocker
(3) lists at least one code-quality issue (e.g., `SELECT *`, missing input validation, vague function name, error handling)
(4) gives a clear merge recommendation (block / changes-needed / approve-with-fixes)
(5) reads as a unified review (combines both reviewers' findings, not just concatenated reports)

Be strict. Reply with ONLY a single digit 1-5.''',
}


# Per-hop rubrics for the 5-hop fan-out delegated_chain.
#   hop 0: parent dispatches to security child
#   hop 1: parent dispatches to quality child
#   hop 2: security child reviews
#   hop 3: quality child reviews
#   hop 4: parent synthesizes both reports (reuses the scenario-level rubric)
CHAIN_HOP_RUBRICS = {
    0: '''Score 1-5: did the parent agent produce a useful delegation message for the SECURITY child?
Criteria (1 point each):
(1) message includes the code under review (the function being PR-reviewed)
(2) message asks for a security-focused review (not general code review)
(3) message is structured for an agent recipient (not addressed to a human end-user)
(4) parent does NOT pre-solve the task (no security findings produced by parent itself)
(5) message is concise — no preamble/postamble unrelated to the dispatch

Reply with ONLY a single digit 1-5.''',

    1: '''Score 1-5: did the parent agent produce a useful delegation message for the CODE-QUALITY child?
Criteria (1 point each):
(1) message includes the code under review
(2) message asks for a code-quality review (style, structure, maintainability — not security)
(3) message is structured for an agent recipient
(4) parent does NOT pre-solve the task
(5) message is concise — no preamble/postamble

Reply with ONLY a single digit 1-5.''',

    2: '''Score 1-5: did the security child produce a useful security review?
Criteria (1 point each):
(1) identifies the SQL injection vulnerability (f-string interpolation of `user_id` into the query)
(2) recommends parameterized queries / prepared statements as the fix
(3) classifies SQL injection as must-fix / merge-blocker / critical
(4) identifies at least one secondary security finding (input validation, info leak, etc.)
(5) does NOT misclassify SQL injection as low-severity / nit

Reply with ONLY a single digit 1-5.''',

    3: '''Score 1-5: did the code-quality child produce a useful quality review?
Criteria (1 point each):
(1) identifies at least 2 distinct code-quality issues (e.g., `SELECT *`, vague name `process_user`, silent `None` return, missing type hints/docstring, no error handling)
(2) suggests a concrete improvement for at least one issue
(3) does NOT focus primarily on security (security is the other reviewer's domain)
(4) is constructive (suggests improvements, not just complaints)
(5) is concise — no preamble/postamble unrelated to the review

Reply with ONLY a single digit 1-5.''',

    4: SCENARIO_RUBRICS['delegated_chain'],
}
