# Delegation example (fan-out)

A parent agent receives a PR review request and dispatches it to TWO specialist children — a security reviewer and a code-quality reviewer — then synthesizes their reports into a unified review with a merge recommendation.

This is the canonical agentic pattern Mormor was designed for: compression compounds across hops, AND across siblings whose outputs both feed back to the parent.

Note the dispatch hops (0 and 1) below: the parent's brief *to* each child is itself in Mormor (`### goal:` + `### note:`), not just the child's report back — and it only delegates: the code plus what the child can't infer, not a checklist of what to find. The parent→child brief is part of the protocol surface — a child meets Mormor on the way in, which is what makes it answer in Mormor on the way out.

## Chain shape (5 hops)

```
   ┌────────────────────┐         ┌────────────────────┐
   │  parent dispatch   │         │  parent dispatch   │
   │     (security)     │         │      (quality)     │
   └─────────┬──────────┘         └──────────┬─────────┘
             │                               │
             ▼                               ▼
   ┌────────────────────┐         ┌────────────────────┐
   │ security reviewer  │         │ quality reviewer   │
   └─────────┬──────────┘         └──────────┬─────────┘
             │                               │
             └──────────┐         ┌──────────┘
                        ▼         ▼
              ┌────────────────────┐
              │ parent synthesize  │
              └─────────┬──────────┘
                        ▼
              user-facing PR review
```

## User task (entering the chain)

````
Pull request review request — the developer wants this function reviewed before merging:

```python
def process_user(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        return user[0]
    return None
```

Run this through your security reviewer AND your code-quality reviewer, then give a final merge recommendation.
````

## Benchmark results

Sonnet 5.5 + Opus 5.5 + Fable 5.1, n=50 runs × 5 hops each, cheatsheet v6; quality is the mean across the 5 hops. Figures are **response-size** reduction vs baseline (cache-independent); for billed cost and the caching caveat, see the [README](../README.md#empirical-results).

| variant | fable 5.1 size Δ | fable 5.1 quality | opus 5.5 size Δ | opus 5.5 quality | sonnet 5.5 size Δ | sonnet 5.5 quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | — | 4.95 | — | 4.93 | — | 4.91 |
| terse | -18% | 4.98 | -17% | 4.95 | -30% | 4.86 |
| **mormor (v6)** | **-69%** | **4.93** | **-72%** | **4.87** | **-67%** | **4.97** |

note: this is where mormor's structural advantage shines hardest — compression compounds across the 5 hops, each agent's output shrinking the next agent's input. **Fable 5.1: ~51pts shorter than terse. Opus 5.5: ~55pts. Sonnet 5.5: ~37pts.** Quality is above baseline on Sonnet 5.5 (4.97 vs 4.91) and slightly below on Fable 5.1 (4.93 vs 4.95) and Opus 5.5 (4.87 vs 4.93). On Opus 5.5 the dip is the brief to the code-quality reviewer: the grader marks down lean briefs that don't spell out what to review, while the reviewers' own reports still score 4.94–5.00.

## Sample exchange — Sonnet 5.5, run 15, mormor v6 (all 5 hops)

### Hop 0 — parent → security child brief

````
### goal:
Security review of PR function before merge. Report findings with severity and fix.

### note:
Code under review:
```python
def process_user(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        return user[0]
    return None
```
Caller, origin of `user_id`, and `db` library unknown; inspect repo if needed.
````

### Hop 1 — parent → quality child brief

````
### goal:
review function for code quality before merge; report findings

### note:
input below; security is covered by a separate reviewer, so skip injection analysis
```python
def process_user(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        return user[0]
    return None
```
````

### Hop 2 — security child report

````
### done:
Finding 1: SQL injection, severity critical
- `user_id` is interpolated into the SQL via f-string → attacker-controlled input can alter the query
- Example: `user_id = "1 OR 1=1"` returns all users; `"1; DROP TABLE users"` runs a second statement on drivers that allow it
- Fix: parameterize

```python
def process_user(user_id):
    user = db.query("SELECT id, name, email FROM users WHERE id = %s", (user_id,))
    return user[0] if user else None
```

Finding 2: `SELECT *` over-fetch, severity low
- Returns every column, including any sensitive ones (password hash, tokens) → leaks if the caller serializes the row
- Fix: list the needed columns, as above

Finding 3: no input validation, severity low
- Enforce `int` at the boundary, e.g. `user_id = int(user_id)` → rejects junk early
- Defense in depth only; parameterization is the real fix

Verdict: block merge until Finding 1 is fixed.

### note:
- Placeholder is `%s` (psycopg2/MySQL style); use `?` for sqlite3, or `:id` for SQLAlchemy `text()`
- Column list `id, name, email` is an assumption; match the real schema
- Caller and `db` library not inspected; the injection holds regardless of the caller unless `user_id` is provably a trusted `int`, which this function doesn't enforce
- No authorization check in the function; confirm the caller verifies the requester may read this user
````

### Hop 3 — quality child report

````
### done:
Findings, most to least important:
- name `process_user` misleads → it only fetches; rename `get_user` or `fetch_user`
- `SELECT *` → couples callers to schema and column order; list needed columns
- fetches all matching rows, uses only first → add `LIMIT 1` or use the driver's fetch-one call
- returns raw row → callers depend on column positions; return a dataclass or mapping
- global `db` → hard to test; pass as parameter or inject
- no type hints, no docstring → signature and return shape (`row | None`) undocumented
- if/return None block → collapse to a conditional expression
- no tests → missing cases: user found, user absent

Minimal fix, assuming a DB-API style `db` with `LIMIT` support:
```python
def get_user(db, user_id: int) -> tuple | None:
    rows = db.query("SELECT id, name, email FROM users WHERE id = ... LIMIT 1")
    return rows[0] if rows else None
```

### note:
injection skipped per request; the `...` stands in for the id filter, which the security reviewer owns
column list `id, name, email` is a placeholder → use the real needed columns
````

### Hop 4 — parent synthesizes final review

````
### done:
Block merge. Fix SQL injection first; the rest are non-blocking.

Merged fix (parameterized + quality items):
```python
def get_user(db, user_id: int) -> tuple | None:
    rows = db.query(
        "SELECT id, name, email FROM users WHERE id = %s LIMIT 1",
        (user_id,),
    )
    return rows[0] if rows else None
```

### case:
| severity | finding | action |
| --- | --- | --- |
| critical | SQL injection: f-string interpolates `user_id` | must-fix: parameterize (`%s`, `(user_id,)`) |
| low | `SELECT *` over-fetch, leaks sensitive columns, couples callers to schema | should-fix: list columns |
| low | no input validation | optional: `int(user_id)` at boundary; defense in depth |
| medium | fetches all rows, uses first | should-fix: `LIMIT 1` |
| medium | name `process_user` misleads | should-fix: rename `get_user` (update callers) |
| medium | global `db`, hard to test | should-fix: inject as parameter |
| low | raw row return, positional column coupling | optional: dataclass or mapping |
| low | no type hints, no docstring | optional: add hints as above, docstring |
| low | no tests | should-fix: cases found, absent, injection-shaped input |

### note:
- placeholder `%s` is psycopg2/MySQL style; `?` for sqlite3, `:id` for SQLAlchemy `text()`
- column list `id, name, email` assumed; match real schema
- no authorization check in function; confirm caller verifies requester may read this user
- caller and `db` library not inspected
- reviewers' fixes agree; the only overlap is `SELECT *` → column list
- rename and `db` parameter change the signature → update all call sites
````

(Unedited responses from the v6 n=50 run — a run where every hop scored 5, with total size near the median.)

## Notes on compounding compression

| metric | value |
| --- | --- |
| baseline response size (5 hops) | _high_ — verbose dispatch + verbose reports + verbose synthesis |
| mormor response-size reduction (5 hops) | -69% fable 5.1, -72% opus 5.5, -67% sonnet 5.5 |
| terse response-size reduction (5 hops) | -18% fable 5.1, -17% opus 5.5, -30% sonnet 5.5 |
| **mormor's lead over terse** | **+51 pts fable 5.1, +55 pts opus 5.5, +37 pts sonnet 5.5** |

Where mormor's structural advantage compounds:
- **dispatch hops (0, 1)**: `goal:` + `note:` carry the brief tighter than prose framing, and hand over the task without pre-solving it — the child gets no checklist or report spec to expand on
- **review hops (2, 3)**: one line per finding, severity first; the fix is a minimal diff rather than a rewrite
- **synthesis hop (4)**: parent inherits both children's compressed reports as input → cache cost lower → mormor's largest absolute saving

The 5-hop fan-out is **the workload Mormor was designed for**. The empirical numbers confirm it.
