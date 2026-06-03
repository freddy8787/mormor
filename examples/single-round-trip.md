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

Sonnet 4.6 + Opus 4.8, n=50 runs each, cheatsheet v1.

| variant | sonnet billed Δ | sonnet quality | opus billed Δ | opus quality |
| --- | ---: | ---: | ---: | ---: |
| baseline (verbose prose) | — | 4.94 | — | 4.98 |
| terse (concise prose) | -30% | 4.94 | -31% | 4.92 |
| **mormor** | **-60%** | **3.94** | **-48%** | **4.98** |

note: this is the scenario where mormor's "default to brief" rule costs the most quality — but only on Sonnet now. On Sonnet the model trades completeness for compression, skipping status codes or full GET-response shapes that the rubric checks for (mean 3.94/5). On Opus 4.8 the dip is gone (4.98/5, up from 4.62 on the earlier Opus 4.7) while still winning -48% on cost. See [Tradeoff notes](#tradeoff-notes) below.

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

### mormor (q=4, ~210 tokens)

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

## Tradeoff notes

Mormor on Sonnet compresses harder than terse (~60% billed reduction vs terse's ~30%) but scores lower on the rubric (3.94 vs 4.94). The lower-scoring runs typically skip:
- explicit status codes for each endpoint (not all 5 codes mentioned)
- the GET-response JSON shape (model lists "list all todos" but doesn't show the response object structure)

These are details the rubric checks for that the user didn't explicitly request — Mormor's "default to brief" rule causes the model to drop them.

On Opus 4.8 the dip disappears (4.98/5) and the cost win is solid at -48% billed — the newer model keeps the optional details under the same protocol. The earlier Opus 4.7 run dipped to 4.62/5 here (see [Earlier results](../README.md#earlier-results-superseded-model-versions)); Sonnet remains the one place this scenario trades quality for compression.

**Adapting for completeness-critical tasks:** if you need every detail in the response, explicitly request them in the prompt ("…include status codes and request/response JSON shapes"). Mormor's compression is honest about what gets dropped — adding the missing details to the prompt closes the gap.
