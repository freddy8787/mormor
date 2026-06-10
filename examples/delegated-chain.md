# Delegation example (fan-out)

A parent agent receives a PR review request and dispatches it to TWO specialist children — a security reviewer and a code-quality reviewer — then synthesizes their reports into a unified review with a merge recommendation.

This is the canonical agentic pattern Mormor was designed for: compression compounds across hops, AND across siblings whose outputs both feed back to the parent.

Note the dispatch hops (0 and 1) below: the parent's brief *to* each child is itself in Mormor (`### goal:` + `### note:`), not just the child's report back. The parent→child brief is part of the protocol surface — a child meets Mormor on the way in, which is what makes it answer in Mormor on the way out.

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

Sonnet 4.6 + Opus 4.8, n=50 runs × 5 hops each, cheatsheet v2. Figures are **response-size** reduction vs baseline (cache-independent); for billed cost and the caching caveat, see the [README](../README.md#empirical-results).

| variant | sonnet size Δ | sonnet quality (mean across 5 hops) | opus size Δ | opus quality |
| --- | ---: | ---: | ---: | ---: |
| baseline | — | 4.86 | — | 4.92 |
| terse | -59% | 4.93 | -26% | 4.94 |
| **mormor (v2)** | **-79%** | **4.91** | **-68%** | **4.88** |

note: this is where mormor's structural advantage shines hardest — compression compounds across the 5 hops, each agent's output shrinking the next agent's input. **Sonnet: ~20pts shorter than terse. Opus: ~42pts.** Quality holds near baseline on both (Sonnet 4.91 vs 4.86; Opus 4.88 vs 4.92), graded under rubric v2 (which no longer penalizes a parent for sharing context with the child — that scored an orchestration choice, not Mormor).

## Sample exchange — Sonnet, run 0, mormor variant (all 5 hops)

### Hop 0 — parent → security child brief

```
### goal:
security review of the following Python function before merge decision

### note:
- part of a two-specialist review pipeline (security + code-quality); findings will be merged into a final merge recommendation
- function accepts `user_id` from an unspecified call site — assume it may originate from user-controlled input

[code block omitted]

### note:
assess injection vectors (SQLi via f-string interpolation), unsafe query patterns, data exposure risks (`SELECT *` returning full user row to caller), and any other security concerns

### done:
return findings as a `### case:` table with severity → finding → fix, using `must-fix` / `should-fix` / `nit`
```

### Hop 1 — parent → quality child brief

```
### goal:
review the following Python function for code quality before merge decision

### note:
- security review running in parallel (separate specialist)
- final merge recommendation will be compiled from both reviews
- function is submitted as a PR; developer awaiting go/no-go

[code block omitted]

### note:
review for naming clarity (`process_user` — does it accurately describe behavior?), return-type consistency (returns `user[0]` or `None` with no type hints), error handling (no try/except around DB call), `SELECT *` over-fetching, brittle `user[0]` indexing, missing docstring or param annotation

### done:
deliver findings as a `### case:` table with severity (must-fix / should-fix / nit) + specific recommendation per issue
```

### Hop 2 — security child report

````
### case:
severity → finding → fix

| severity | finding | fix |
| --- | --- | --- |
| must-fix | SQL injection via f-string interpolation; `user_id` controls query | parameterized query: `db.query("SELECT * FROM users WHERE id = ?", (user_id,))` |
| must-fix | no input type coercion before query | `user_id = int(user_id)` raises on non-numeric |
| should-fix | `SELECT *` returns full row incl. password hash, tokens, PII | enumerate required columns explicitly |
| should-fix | raw DB row leaks internal schema through return type | map result to a DTO/dataclass |
| should-fix | no exception handling around `db.query()`; stack traces expose internals | try/except; log internally; re-raise sanitized |
| nit | name `process_user` implies mutation; behavior is read-only lookup | rename to `get_user_by_id` |
````

### Hop 3 — quality child report

````
### case:
issue → severity → recommendation

| issue | severity | recommendation |
| --- | --- | --- |
| `process_user` misleads — behavior is fetch, not process | must-fix | rename to `get_user_by_id` |
| f-string SQL interpolation | must-fix | parameterized query (flag for security reviewer too) |
| no try/except around `db.query` | must-fix | wrap; catches `DatabaseError`; caller can distinguish "not found" from "DB down" |
| `SELECT *` | should-fix | enumerate required columns; prevents breakage on schema changes |
| `user[0]` — assumes sequence return | should-fix | assert/document return contract; use `db.query_one()` if available |
| no return-type hint | should-fix | annotate `-> Optional[User]` |
| no docstring / param annotation | nit | add one-liner + `:param user_id:` + `:returns:` |

### note:
- must-fix items individually sufficient to block merge; SQL injection overlaps security review — coordinate to avoid conflicting instructions
- naming + error handling are independent fixes; can be addressed in same commit
````

### Hop 4 — parent synthesizes final review

````
### done:
BLOCK MERGE — 3 confirmed must-fix items; SQL injection alone is sufficient to block

### case:
severity → finding → fix

| severity | finding | fix |
| --- | --- | --- |
| must-fix | SQL injection via f-string interpolation | parameterized query: `db.query("SELECT * FROM users WHERE id = ?", (user_id,))` |
| must-fix | no input type coercion before query | `user_id = int(user_id)` raises on non-numeric |
| must-fix | no exception handling around `db.query()` | wrap in try/except, log internally, raise sanitized `UserLookupError` |
| should-fix | `SELECT *` exposes all columns incl. secrets | enumerate required columns explicitly |
| should-fix | raw DB row leaks schema | map to DTO/dataclass |
| should-fix | `user[0]` assumes sequence return | assert/document contract; use `db.query_one()` if available |
| should-fix | `process_user` misleads — behavior is read-only fetch | rename to `get_user_by_id` |
| should-fix | no return-type hint | annotate `-> Optional[User]` |
| nit | no docstring / param annotation | add one-liner + `:param user_id:` + `:returns:` |

### note:
two severity conflicts resolved before consolidation —
- try/except: security said should-fix, quality said must-fix → escalated to must-fix
- function rename: security said nit, quality said must-fix → settled at should-fix

### note:
suggested rewrite (incorporates all must-fix + should-fix):
```python
@dataclass
class User:
    id: int
    name: str
    email: str

def get_user_by_id(user_id: int) -> Optional[User]:
    """Fetch user by id; returns None if not found."""
    user_id = int(user_id)
    try:
        rows = db.query(
            "SELECT id, name, email FROM users WHERE id = ?",
            (user_id,),
        )
    except DatabaseError as e:
        logger.error("user lookup failed: %s", e)
        raise UserLookupError(f"could not retrieve user {user_id}") from e
    return User(**rows[0]) if rows else None
```
````

(Sample compressed for readability — actual hop-4 responses are typically ~400-500 tokens.)

## Notes on compounding compression

| metric | value |
| --- | --- |
| baseline response size (5 hops) | _high_ — verbose dispatch + verbose reports + verbose synthesis |
| mormor response-size reduction (5 hops) | -79% sonnet, -68% opus |
| terse response-size reduction (5 hops) | -59% sonnet, -26% opus |
| **mormor's lead over terse** | **+20 pts sonnet, +42 pts opus** |

Where mormor's structural advantage compounds:
- **dispatch hops (0, 1)**: `goal:` + `note:` carry the brief tighter than prose framing
- **review hops (2, 3)**: `case:` table for the quality review consolidates 7 issues into one structure
- **synthesis hop (4)**: parent inherits both children's compressed reports as input → cache cost lower → mormor's largest absolute saving

The 5-hop fan-out is **the workload Mormor was designed for**. The empirical numbers confirm it.
