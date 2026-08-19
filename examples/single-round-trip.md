# Single round-trip example

A one-shot task: the user describes what they need; the agent produces a plan in a single message. No back-and-forth, no delegation.

This scenario tests how the protocol handles a planning request — the agent maps out endpoints, methods, and shapes, not pretend-execution.

## User prompt

The same prompt is sent to all three variants. Only the SYSTEM PROMPT differs (baseline = minimal, terse = "be concise" rules, mormor = the cheatsheet).

```
Planning the REST API for a simple todo list app. Single user (no auth
yet), each todo has title + done flag + optional due_date. Map out the
endpoints.
```

## Benchmark results

Sonnet 5 + Opus 5 + Fable 5, n=50 runs each, cheatsheet v3. Figures are **response-size** reduction vs baseline (cache-independent); for billed cost and the caching caveat, see the [README](../README.md#empirical-results).

| variant | fable 5 size Δ | fable 5 quality | opus 5 size Δ | opus 5 quality | sonnet 5 size Δ | sonnet 5 quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (verbose prose) | — | 5.00 | — | 5.00 | — | 4.98 |
| terse (concise prose) | -40% | 4.76 | -30% | 4.98 | -38% | 4.88 |
| **mormor (v3)** | **-43%** | **4.94** | **-53%** | **5.00** | **-64%** | **4.64** |

note: a planning task — the agent maps endpoints, methods, status codes, and response shapes. Mormor's completeness guard (*compress wording, never coverage*) keeps every enumerated item the task implies, so responses run -64% shorter on Sonnet 5, -53% on Opus 5, -43% on Fable. Quality holds at baseline on Opus 5 (5.00) and Fable (4.94); on Sonnet 5 this is Mormor's softest cell (4.64 vs 4.98) — the answer stays complete, but phrasing is tightest here. See [Notes](#notes) below.

## Responses (Sonnet samples — median quality picks)

### baseline (q=5, ~535 tokens)

```
Here's a clean, minimal REST API design for your todo list app:

## Base URL
`/api/v1`

## Resource: `/todos`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/todos` | List all todos |
| `POST` | `/todos` | Create a new todo |
| `GET` | `/todos/:id` | Get a single todo |
| `PUT` | `/todos/:id` | Replace a todo (full update) |
| `PATCH` | `/todos/:id` | Partial update (e.g. toggle `done`) |
| `DELETE` | `/todos/:id` | Delete a todo |

## Payloads

**Todo object (response)**
[full JSON example with id, title, done, due_date, timestamps]

**POST /todos — body**
[full JSON example]

**PATCH /todos/:id — body**
[partial-update examples]

## GET /todos — Query Params
[table with done, sort, order]

## HTTP Status Codes
[table mapping scenarios to codes]

## Design notes
[bullet list with PUT-vs-PATCH, due_date format, IDs, etc.]
```

(Truncated for readability — full response is ~535 tokens.)

### terse (q=5, ~370 tokens)

````
## Todo List REST API Endpoints

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|--------------|----------|
| `GET` | `/todos` | List all todos | — | `200` array of todos |
| `POST` | `/todos` | Create a todo | `{title, due_date?}` | `201` created todo |
| `GET` | `/todos/:id` | Get single todo | — | `200` todo or `404` |
| `PATCH` | `/todos/:id` | Update todo (partial) | `{title?, done?, due_date?}` | `200` updated todo |
| `DELETE` | `/todos/:id` | Delete a todo | — | `204` no content |

### Todo Resource Shape
```json
{
  "id": "uuid",
  "title": "Buy groceries",
  "done": false,
  "due_date": "2026-05-15",
  "created_at": "2026-05-10T12:00:00Z",
  "updated_at": "2026-05-10T12:00:00Z"
}
```

### Key Design Decisions
- `PATCH` not `PUT` — partial updates; no need to send full object to toggle `done`
- `due_date` is nullable — omit to leave unset; `null` to clear
- `done` defaults to `false` on creation
- No `/todos/:id/complete` action route — `PATCH {"done": true}` is sufficient

### Suggested Query Params for GET /todos
| Param | Values | Effect |
|-------|--------|--------|
| `done` | `true`/`false` | Filter by completion |
| `sort` | `due_date`, `created_at` | Sort field |
| `order` | `asc`/`desc` | Sort direction |
````

### mormor (q=5, ~210 tokens)

```
### done:
REST API endpoint map

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/todos` | list all todos |
| `POST` | `/todos` | create todo |
| `GET` | `/todos/:id` | get single todo |
| `PATCH` | `/todos/:id` | update (title / done / due_date) |
| `DELETE` | `/todos/:id` | delete todo |

### note:
- `POST /todos` body: `{ title: string, due_date?: string }` — `done` defaults to `false` server-side
- `PATCH` not `PUT` → partial updates; clients send only changed fields
- `due_date` as ISO 8601 string (`"2026-05-15"`) — keeps it timezone-safe
- status codes: `200` list/get/patch, `201` create, `204` delete, `404` missing id, `422` invalid body
- filtering (e.g. `GET /todos?done=false`) can be added as query param later without breaking contract
```

## Notes

Mormor compresses this scenario hard (-64% sonnet 5 / -53% opus 5 / -43% fable vs baseline). The completeness guard does the work: it drops filler wording but keeps every enumerated item the task implies — endpoints, methods, status codes, request/response shapes — so the shorter response stays complete. The sample above keeps all five endpoints plus the status-code line and body shapes under `### note:`. Quality holds at baseline on Opus 5 (5.00) and Fable (4.94); Sonnet 5 is the softest cell (4.64), where the tighter phrasing costs a fraction of a point without dropping coverage.

**Completeness-critical tasks:** if a task needs a detail that isn't obviously implied, ask for it explicitly in the prompt ("…include status codes and request/response JSON shapes"). Compression trims wording, not requested coverage.
