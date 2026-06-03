# Multi-turn debugging example

A 5-turn debugging conversation: the user is tracking down a flaky CI test that passes locally. Each turn refines the hypothesis based on what the user tried — a realistic back-and-forth diagnosis.

## User turns (sent across all variants)

The same 5 turns are sent to every variant. Only the SYSTEM PROMPT differs (baseline = minimal, terse = "be concise" rules, mormor = the cheatsheet).

```
Turn 1: Test passing locally but flaking in CI — `tests/test_pipeline.py`
        fails ~30% of runs, different assertions each time. How do I track
        this down?

Turn 2: Reran in CI 50 times — fails on different assertions, not always
        the same one. Could be ordering or shared state?

Turn 3: Ran the failing test in isolation — passes 100%. Only flakes when
        run as part of the full suite. So another test is leaving state
        behind.

Turn 4: Found it: an earlier test leaves a row in the DB; my test assumes
        the table is empty. Should I add cleanup or use transactions?

Turn 5: Going with transactions. Can you sketch the pytest fixture?
```

## Benchmark results

Sonnet 4.6 + Opus 4.8, n=50 runs each, 5 turns per run, cheatsheet v1.

| variant | sonnet billed Δ | sonnet quality (mean) | opus billed Δ | opus quality |
| --- | ---: | ---: | ---: | ---: |
| baseline | — | 4.88 | — | 4.99 |
| terse | -22% | 4.90 | -16% | 4.97 |
| **mormor** | **-36%** | **4.87** | **-40%** | **4.96** |

note: mormor stays within 0.06 of baseline quality on both models. Compression gap to terse is ~14pts on Sonnet and ~24pts on Opus 4.8 (terse compresses only -16% here, so mormor's structured form pulls well ahead) — cache_read dominates the bill in this scenario, so the absolute spend is small either way. Per-turn quality holds even on the densest turn.

## Sample exchange — Sonnet, run 0, mormor variant (full 5 turns)

### Turn 1 — agent response

````
### done:
systematic narrowing strategy — identify pattern first, then bisect culprits

### note:
replay loop to confirm flake pattern:
```bash
pip install pytest-repeat
pytest tests/test_pipeline.py --count=50 -x
```
also run in random order to catch state bleed:
```bash
pytest tests/test_pipeline.py -p randomly --randomly-seed=last
```

### case:
symptom → likely cause

| symptom | cause |
| --- | --- |
| different assertions each run | shared mutable state between tests |
| timing-related assertions | sleep/time calls + CI is slower → race condition |
| failures only in CI, never local | env vars, missing secrets, or parallelism |
| set/dict iteration results vary | non-deterministic iteration order |
| passes alone, fails in suite | test-order dependency |

[truncated — instrumentation snippet follows]
````

### Turn 2 — agent response

````
### done:
"different assertions, never the same one" is the canonical signature of shared mutable state — ordering is the trigger

### note:
confirm it's state, not timing — run two seeds:
```bash
pytest tests/test_pipeline.py -p randomly --randomly-seed=12345 -v
pytest tests/test_pipeline.py -p randomly --randomly-seed=99999 -v
```
different seeds → different failures → ordering-driven state bleed

### note:
find the culprit fast:
```bash
pytest tests/test_pipeline.py --randomly-seed=last -x -v 2>&1 | grep "FAILED\|PASSED"
```
`--randomly-seed=last` replays the exact order that just failed → reproducible sequence to bisect

[truncated — bisection snippet + grep patterns follow]
````

### Turn 3 — agent response

````
### done:
confirmed state-bleed — another test mutates something `test_pipeline.py` depends on, doesn't clean up

### note:
find the poisoning test in ~5 min:
```bash
pytest tests/ --randomly-seed=random -x -v 2>&1 | tail -20
# note the seed printed at top: "Using --randomly-seed=XXXXX"

pytest tests/ --randomly-seed=XXXXX -v 2>&1 | grep -E "PASSED|FAILED" > order.txt
# find the last test that ran BEFORE your failing one — that's your prime suspect
```

### case:
leaked resource → signs in the suspect test

| leaked resource | signs in suspect test |
| --- | --- |
| module-level global | `import pipeline_module; pipeline_module.state = x` |
| monkeypatch not restored | manual `mock.patch` without context manager or `addCleanup` |
| env var set, not cleared | `os.environ["X"] = "y"` with no teardown |
| singleton/registry | `Registry.register(x)` — cumulative across tests |
````

### Turn 4 — agent response

````
### done:
use transactions — strictly better here

### case:
approach → tradeoff

| approach | problem |
| --- | --- |
| `DELETE FROM table` in teardown | teardown can be skipped on crash; order-sensitive; slow |
| `DELETE FROM table` in setup | masks the bug; still slow |
| transaction rollback | atomic, instant, guaranteed — no teardown needed |

### note:
pytest + SQLAlchemy fixture:
```python
@pytest.fixture()
def db_session():
    conn = engine.connect()
    tx = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    tx.rollback()
    conn.close()
```
````

### Turn 5 — agent response

````
### done:
transactional pytest fixture below

```python
# conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from yourapp.db import Base

DATABASE_URL = "postgresql://user:pass@localhost/test_db"
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine)

@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture()
def db():
    conn = engine.connect()
    tx = conn.begin()
    session = TestingSessionLocal(bind=conn)
    yield session
    session.close()
    tx.rollback()
    conn.close()
```

### note:
usage:
```python
def test_pipeline_assumes_empty_table(db):
    assert db.query(MyModel).count() == 0
    db.add(MyModel(name="foo"))
    db.flush()
    # rollback fires after yield — "foo" never committed
```
````

## Notes

- mormor uses `### done:` to lead each turn (so the user can scan the headline answer first), then organizes details under `### case:` tables or labeled bullets
- compression in multi-turn is dominated by conversation cache — by turn 5, the input has accumulated all 4 prior turns + responses; mormor's smaller responses keep the cache lean
- per-turn mean quality 4.87 sonnet / 4.92 opus — within 0.06 of baseline on both models even on the densest turn (turn 5 with the fixture sketch)
