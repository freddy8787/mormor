# Decision-table (security review) example

A code-review task where the agent receives a pre-defined severity framework and classifies findings against it. This is the canonical use case for `case:` — the response naturally takes a finding → severity → action table shape.

## User prompt

The same prompt is sent to all three variants. Only the SYSTEM PROMPT differs.

````
Security review of this function. Categorize each finding:
- must-fix → block merge
- should-fix → comment, no block
- nit → skip / optional

```python
def process_user(user_id):
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
    if user:
        return user[0]
    return None
```
````

## Benchmark results

Sonnet 5 + Opus 5 + Fable 5, n=50 runs each, cheatsheet v3. Figures are **response-size** reduction vs baseline (cache-independent); for billed cost and the caching caveat, see the [README](../README.md#empirical-results).

| variant | fable 5 size Δ | fable 5 quality | opus 5 size Δ | opus 5 quality | sonnet 5 size Δ | sonnet 5 quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (verbose prose) | — | 5.00 | — | 5.00 | — | 5.00 |
| terse (concise prose) | -41% | 5.00 | -49% | 5.00 | -38% | 5.00 |
| **mormor (v3)** | **-37%** | **5.00** | **-75%** | **5.00** | **-74%** | **5.00** |

note: the `### case:` table makes mormor's compression structural rather than just "fewer words". mormor runs -75% on Opus 5 / -74% on Sonnet 5, well beyond terse, with quality holding at baseline (Sonnet 5 5.00, Opus 5 5.00, Fable 5.00). On Fable the raw-size gap over terse is small here (baselines are already terse), but it still wins on billed cost through caching (-42%).

## Responses (Sonnet samples)

### baseline (q=5, ~466 tokens)

```
## Security Review

### 🔴 Must-Fix

**SQL Injection** — user_id is interpolated directly into the query string with
no sanitization. An attacker can pass `1 OR 1=1` to dump all rows, or
`1; DROP TABLE users; --` to cause destruction.

[code block: vulnerable + parameterized fix]

### 🟡 Should-Fix

**SELECT * over-fetches sensitive columns** — Returning every column
(hashed passwords, tokens, PII, internal flags) violates least-privilege.

**No input validation** — Nothing ensures user_id is an integer before
hitting the DB layer.

**No exception handling** — A DB error surfaces as an unhandled exception
that may expose a stack trace.

### 🔵 Nit

**Vague function name** — process_user implies side effects.

### Summary

| Finding | Severity | Blocks merge? |
| --- | --- | --- |
| SQL injection via f-string | **Must-fix** | ✅ Yes |
| SELECT * exposes sensitive fields | Should-fix | No |
| No input validation | Should-fix | No |
| No exception handling | Should-fix | No |
| Vague function name | Nit | No |

The SQL injection alone is enough to block this.
```

(Truncated; full response ~466 tokens.)

### terse (q=5, ~396 tokens)

````
## Security Review: process_user

| # | Finding | Category | Severity |
|---|---------|----------|----------|
| 1 | **SQL Injection** — user_id interpolated; attacker can pass `1 OR 1=1` or `; DROP TABLE users--` | **must-fix** | 🔴 Critical |
| 2 | **No input validation** — user_id type/format never checked before DB | **must-fix** | 🔴 Critical |
| 3 | **SELECT *** — returns all columns including sensitive fields | **should-fix** | 🟡 Medium |
| 4 | **Silent None return** — caller may not distinguish not-found from error | **should-fix** | 🟡 Low |
| 5 | **No auth/authz check** — any caller can fetch any user by ID | **should-fix** | 🟡 Medium |
| 6 | **No logging/audit trail** — user data access is unlogged | **nit** | ⚪ Optional |

### Minimal must-fix patch

```python
def process_user(user_id: int):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(f"Invalid user_id: {user_id!r}")
    user = db.query(
        "SELECT id, name, email FROM users WHERE id = %s",
        (user_id,)
    )
    if not user:
        raise UserNotFoundError(user_id)
    return user[0]
```
````

### mormor (q=5, ~240 tokens)

````
### case:
finding → severity → action

| finding | severity | action |
| --- | --- | --- |
| f-string interpolation in SQL → SQL injection | must-fix | block merge |
| `SELECT *` exposes all columns (passwords, tokens, PII) | should-fix | comment inline |
| no input validation on `user_id` (type, range, null) | should-fix | comment inline |
| no exception handling around `db.query()` | should-fix | comment inline |
| function name `process_user` doesn't describe behavior | nit | skip |

### note:
- SQL injection fix → parameterized query:
```python
user = db.query("SELECT * FROM users WHERE id = %s", (user_id,))
```
- `SELECT *` fix → enumerate columns explicitly, e.g. `SELECT id, name, email`
- validation example: `if not isinstance(user_id, int) or user_id <= 0: raise ValueError`
- unhandled `db.query()` exception → caller gets uncaught DB error, leaks stack trace if bubbled to API layer
````

## Notes

- Mormor's `case:` table directly satisfies the user's classification framework — every finding has a row with severity + action mapped 1:1
- `case:` saves significant bytes here vs prose: the baseline uses headers (`### Must-Fix`, `### Should-Fix`, `### Nit`) + bold text + emoji severity markers; mormor collapses all of that into one structured table
- quality holds at baseline (Sonnet 5 5.00, Opus 5 5.00, Fable 5.00); any occasional point off comes from a secondary finding being phrased more tersely under the same `case:` table, not from dropping it
