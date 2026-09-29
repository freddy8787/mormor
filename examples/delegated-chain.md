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

Sonnet 5 + Opus 5.5 + Fable 5.1, n=50 runs × 5 hops each, cheatsheet v5; quality is the mean across the 5 hops. Figures are **response-size** reduction vs baseline (cache-independent); for billed cost and the caching caveat, see the [README](../README.md#empirical-results).

| variant | fable 5.1 size Δ | fable 5.1 quality | opus 5.5 size Δ | opus 5.5 quality | sonnet 5 size Δ | sonnet 5 quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | — | 4.93 | — | 4.93 | — | 4.92 |
| terse | -32% | 4.98 | -17% | 4.95 | -27% | 4.94 |
| **mormor (v5)** | **-76%** | **4.96** | **-71%** | **4.96** | **-71%** | **4.92** |

note: this is where mormor's structural advantage shines hardest — compression compounds across the 5 hops, each agent's output shrinking the next agent's input. **Fable 5.1: ~44pts shorter than terse. Opus 5.5: ~54pts. Sonnet 5: ~44pts.** Quality holds at or above baseline on all three (Fable 5.1 4.96 vs 4.93; Opus 5.5 4.96 vs 4.93; Sonnet 5 4.92 vs 4.92).

## Sample exchange — Sonnet 5, run 21, mormor v5 (all 5 hops)

### Hop 0 — parent → security child brief

````
### goal:
security review of PR function before merge; report findings in Mormor

### note:
code under review:

```python
def process_user(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        return user[0]
    return None
```
````

### Hop 1 — parent → quality child brief

````
### goal:
review code quality of `process_user` for PR merge; report findings in Mormor

### note:
security review handled by separate reviewer; skip injection analysis

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
block merge: 1 must-fix, 2 should-fix

1. must-fix: SQL injection → `user_id` interpolated via f-string, e.g. `1 OR 1=1` returns all rows, `1; DROP TABLE users` runs a second statement on drivers allowing stacked queries
2. should-fix: `SELECT *` → returns every column (password hash, tokens, PII) to callers
3. should-fix: no type/format validation on `user_id`

Fix:

```python
def process_user(user_id):
    user = db.query(
        "SELECT id, name, email FROM users WHERE id = %s",
        (int(user_id),),
    )
    if user:
        return user[0]
    return None
```

### note:
placeholder style `%s` assumed; use the `db` driver's paramstyle (`?`, `:id`)
column list `id, name, email` is a placeholder; match what callers need
`int(user_id)` raises `ValueError` on non-numeric input; assumes integer ids
````

### Hop 3 — quality child report

````
### done:
code quality findings for `process_user`:

- name: `process_user` → misleading, only fetches; rename `get_user_by_id`
- `SELECT *` → couples to schema column order/additions, over-fetches; list needed columns
- no `LIMIT 1` → id is unique, still fetches full result set; add `LIMIT 1`
- `user[0]` → returns raw row, shape undocumented; map to dataclass/dict
- global `db` → hidden dependency, hard to unit test; inject as parameter
- no type hints, no docstring → return type unclear (`row | None`)
- if/else → collapsible to one expression
- no tests → add found and not-found cases

```python
def get_user_by_id(db, user_id: int) -> User | None:
    rows = db.query("SELECT id, name, email FROM users WHERE id = ? LIMIT 1", (user_id,))
    return User(*rows[0]) if rows else None
```

### test:
none in diff → add `test_get_user_by_id_found` and `test_get_user_by_id_missing`
````

### Hop 4 — parent synthesizes final review

````
### done:
block merge → 1 must-fix, 4 should-fix, 3 nits. Apply merged fix below, add tests, re-review.

### case:
severity → finding → action

| severity | finding | action |
| --- | --- | --- |
| must-fix | SQL injection: f-string interpolation of `user_id` (`1 OR 1=1` dumps table; stacked queries possible) | parameterized query |
| should-fix | `SELECT *` → leaks password hash/tokens/PII, couples to schema | explicit column list |
| should-fix | no validation of `user_id` | type hint `int`; coerce/validate at boundary |
| should-fix | no tests | add `test_get_user_by_id_found`, `test_get_user_by_id_missing`, plus injection-string case |
| should-fix | global `db` → hidden dependency, hard to test | inject as parameter |
| nit | name `process_user` misleads (only fetches) | rename `get_user_by_id` |
| nit | no `LIMIT 1` | add `LIMIT 1` |
| nit | raw row returned, no type hints/docstring | map to `User`, annotate `User | None` |

Merged fix:

```python
def get_user_by_id(db, user_id: int) -> User | None:
    rows = db.query(
        "SELECT id, name, email FROM users WHERE id = %s LIMIT 1",
        (user_id,),
    )
    return User(*rows[0]) if rows else None
```

### note:
reviewers disagree on validation: security → `int(user_id)` coercion, quality → type hint only. Hints aren't enforced at runtime → validate/coerce at the caller boundary; parameterization alone already closes the injection
placeholder: security used `%s`, quality used `?` → use the `db` driver's paramstyle
column list `id, name, email` is a placeholder; match what callers need
rename breaks existing callers of `process_user` → update call sites
`User` type not defined in diff → assumed to exist or be added

### test:
none in diff → required before merge
````

(Unedited responses from the v5 n=50 run — a run where every hop scored 5, with total size at the median.)

## Notes on compounding compression

| metric | value |
| --- | --- |
| baseline response size (5 hops) | _high_ — verbose dispatch + verbose reports + verbose synthesis |
| mormor response-size reduction (5 hops) | -76% fable 5.1, -71% opus 5.5, -71% sonnet 5 |
| terse response-size reduction (5 hops) | -32% fable 5.1, -17% opus 5.5, -27% sonnet 5 |
| **mormor's lead over terse** | **+44 pts fable 5.1, +54 pts opus 5.5, +44 pts sonnet 5** |

Where mormor's structural advantage compounds:
- **dispatch hops (0, 1)**: `goal:` + `note:` carry the brief tighter than prose framing, and hand over the task without pre-solving it — the child gets no checklist or report spec to expand on
- **review hops (2, 3)**: one line per finding, severity first; the fix is a minimal diff rather than a rewrite
- **synthesis hop (4)**: parent inherits both children's compressed reports as input → cache cost lower → mormor's largest absolute saving

The 5-hop fan-out is **the workload Mormor was designed for**. The empirical numbers confirm it.
