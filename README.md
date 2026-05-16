# Mormor

**An agent communication protocol for compressed agent-to-agent and agent-to-user messages.**

| variant | sonnet billed Δ | sonnet quality | opus billed Δ | opus quality |
| --- | ---: | ---: | ---: | ---: |
| baseline (verbose prose) | — | 4.83 | — | 4.85 |
| terse (concise prose) | -29% | 4.85 | -20% | 4.85 |
| **mormor** | **-52%** | **4.79** | **-50%** | **4.87** |

Mormor wins decisively on billed cost — **23 percentage points beyond terse on Sonnet, 30 points on Opus** on aggregate. Quality holds at or near baseline in 8 of 10 scenario × model cells; in 2 cells the model trades completeness for compression on tasks that implicitly want every detail (see [Empirical results](#empirical-results) for the breakdown). Responses also come back faster — **~50% quicker on both models** — since there's less to generate.

### How Mormor works

Mormor uses six labels rendered as level-3 markdown headings (`### goal:`, `### note:`, `### case:`, `### done:`, `### ask:`, `### test:`) on top of plain markdown. Agents replace prose connectives with labels and keep technical content verbatim. The result is shorter, denser, and easier to parse — for both other agents and for humans skimming the output.

### Caveats

**Pre-1.0.** Labels and behavior rules may evolve between releases until the protocol stabilizes. Try it on an experimental project first to build confidence, and feel free to adapt the cheatsheet per-project if defaults don't fit your workflow. See [`CHANGELOG.md`](./CHANGELOG.md) for the current version.

**Tested models.** Mormor was validated on Sonnet 4.6 and Opus 4.7. Haiku 4.5 was also tested but consistently lost on billed cost — the cheatsheet's system-prompt overhead outweighed the response-size savings on the smaller model.

---

## Quick start

1. Open [`CHEATSHEET.md`](./CHEATSHEET.md).
2. Paste it into your system prompt (or append it to `CLAUDE.md`).
3. Use Mormor labels in messages where you want compressed responses.

For a **single agent** that's the whole path — Mormor is a vocabulary, not software, so there's nothing to install. **Agent-to-agent (subagents)** is what Mormor compresses hardest, but pasting into the parent's system prompt or `CLAUDE.md` does *not* propagate to subagents — see [Agent-to-agent setup](#agent-to-agent--subagents).

Example exchange — a parent agent delegating to a child agent:

````
### goal:
diagnose the slow PostgreSQL query and recommend a specific fix

### note:
user reports query takes 8s to return 50 rows; EXPLAIN ANALYZE output provided

```
Seq Scan on users (cost=0.00..125000.00 rows=50 width=128) (actual time=8200.123..8200.456 rows=50 loops=1)
  Filter: (email = 'user@example.com'::text)
  Rows Removed by Filter: 1999950
  Total runtime: 8203.789 ms
```
````

The child agent's response, also in Mormor:

````
### done:
missing index on `users.email` — full table scan of ~2M rows; fix is one DDL

```sql
CREATE INDEX CONCURRENTLY idx_users_email ON users (email);
```

### note:
- `Seq Scan` + `Rows Removed by Filter: 1,999,950` → planner has no index path
- selectivity 0.0025% → ideal B-tree candidate; planner would prefer Index Scan immediately
````

These are idealized exchanges — what good Mormor should look like. Real model responses follow this shape but vary slightly in wording, line counts, and structure. See [`examples/`](./examples/) for more patterns.

---

## Why a protocol

Agents talking to other agents (and to users in scripted contexts) generate a lot of *connective tissue*: hedging, meta-commentary, phrasing variants, polite preambles. The factual signal — code, paths, error strings, decisions — is a small fraction of the output.

Mormor's bet is that a small labeled vocabulary lets the model drop connective tissue without losing meaning, because the labels themselves carry the structural information that the prose was implicitly conveying ("here's the result", "here's some context", "here's a branching condition").

The closest alternative is just asking the model to be concise. In our benchmark this achieves 20–29% billed reduction — useful on its own — but plateaus there because the savings come from fewer hedges, not from compressing semantic structure. Mormor pulls ahead by another 23–30 percentage points on aggregate, with the biggest gaps on agent-to-agent scenarios where the labeled output gives the receiving agent a parsing scaffold.

---

## Empirical results

The headline table at the top is the aggregate of 5 scenarios × 3 variants × 2 models × 50 runs each. The terse-prose variant ("just be concise" without the protocol vocabulary) is the relevant comparison — it tells us how much of Mormor's gain comes from the labels vs from simply asking the model to be brief.

**How the aggregate is computed.** Billed-cost percentages are **scenario-equal**: the per-scenario mean billed cost is summed across all 5 scenarios per (variant, model), then the delta is taken on the sums. Every scenario contributes equally regardless of how many turns it produces. This is the `AGGREGATE (scen-eq)` row in the bench's `BILLED-COST delta` matrices (see [bench/README.md](./bench/README.md)). Latency percentages are **row-equal**: the mean across every recorded row per (variant, model), as emitted by the bench's `mean latency` matrix.

**Cost is all-in.** The `billed` numbers above are computed on the SDK's `output_tokens`, which includes any extended-thinking tokens the model generated before the visible response — not just displayed text. Mormor's compression edge therefore reflects real wallet impact with no hidden-thinking blind spot. Runs use the SDK's `effort='low'` setting to dampen extended thinking; results at higher effort levels may differ.

**Caching dependency — open question, help wanted.** The `billed` reductions assume Anthropic's prompt cache is functioning normally for `claude-agent-sdk` calls: the cheatsheet's ~1,030-token prefix caches on the first call, and subsequent calls report `cache_read_input_tokens > 0`. We've verified this is the typical regime via direct probes. **However**, we observed at least one multi-hour window where cache *writes* succeeded but cache *reads* stayed at zero across thousands of calls — and during that window, mormor's `billed` advantage shrank substantially because its larger system prompt no longer amortized via cache hits. The condition resolved on its own; root cause is unknown. Possibilities we can't yet rule out: an Anthropic-side rollout, a Claude Code CLI behavior shift, or a subscription-tier interaction. **If you can reproduce or diagnose the regime change, please open an issue.** The cache-independent metrics on this page — `response-size ratio`, `mean latency`, `mean quality` — are unaffected by this anomaly.

### Per-scenario billed-cost reduction (mormor vs baseline)

| scenario | sonnet | opus |
| --- | ---: | ---: |
| `single_round_trip` (planning task) | -60% | -57% |
| `branching` (security review) | -56% | -65% |
| `multi_turn` (5-turn debugging) | -36% | -32% |
| `high_frequency` (classification) | -20% | -26% |
| `delegated_chain` (5-hop fan-out) | **-68%** | **-68%** |

### Where Mormor shines

- **Agent-to-agent chains** — `delegated_chain` is Mormor's strongest scenario across both models (-68% / -68% billed reduction). Compression compounds across hops; mormor's labeled outputs flow cleanly into downstream agents' inputs.
- **Code review and decision tables** — `case:` directly satisfies the user's classification framework; baseline+terse use prose headings + bold which compress less. `branching` shows -56% / -65% billed reduction with quality preserved at or near 5.00.
- **Planning tasks** — `single_round_trip` posts strong wins on both models (-60% / -57% billed) when the task implicitly invites structured output.

### Where Mormor's compression doesn't pay as hard

- **High-frequency atomic classification** — `high_frequency` posts the smallest wins (-20% sonnet, -26% opus). The baseline is already very brief (one-line classification + reason), leaving little prose for the protocol to compress. Still positive on both models, just marginal.
- **Quality dips on `single_round_trip` (Sonnet 3.94/5, Opus 4.62/5)** — when the rubric implicitly checks for optional details (status codes, every secondary finding), Mormor's "default to brief" rule causes the model to skip them. Both dips are in the same scenario; other 8 cells hold within 0.3 of baseline.

  We attempted to engineer a cheatsheet rule that lifts these dips without regressing the other cells. Multiple rounds of candidate rules didn't yield a clean fix — every addition we tried introduced offsetting downsides elsewhere in the matrix. We accept the dips for v0.1.0 and document them here rather than ship a rule that pays for one cell with another. Future work (v0.2.0+): per-scenario rule injection, model-specific cheatsheet variants, or task-aware preambles.

Per-scenario breakdowns, full methodology, and reproduction steps: [`bench/README.md`](./bench/README.md). Per-scenario sample exchanges live in [`examples/`](./examples/).

---

## Adoption

### Where to use Mormor

1. **Agent-to-agent communication.** Parent delegating to a child, child reporting back, two peers coordinating. Compression compounds across hops, and the labeled structure gives the receiving agent a parsing scaffold rather than free-form prose.
2. **Agent-to-user communication, with user opt-in.** A developer comfortable reading Mormor can opt into denser output. Do NOT default to Mormor with users who haven't agreed to it.

### How to enable it (single agent)

Paste [`CHEATSHEET.md`](./CHEATSHEET.md) into the agent's system prompt. For Claude Code, append it to your project `CLAUDE.md`, or load it via the SDK:

```python
from claude_agent_sdk import ClaudeAgentOptions

with open('CHEATSHEET.md') as f:
    cheatsheet = f.read()

options = ClaudeAgentOptions(
    system_prompt=cheatsheet,
    model='claude-sonnet-4-6',
    # ...
)
```

### Agent-to-agent / subagents

Subagents (Claude Code Task tool, SDK sub-agents) run in a **fresh context**. They don't inherit the parent's system prompt or `CLAUDE.md`, so pasting the cheatsheet there reaches the orchestrator only — the subagents it spawns never see it. And because models mirror the style they're addressed in, a subagent that doesn't see Mormor replies in prose, so the cross-hop compression never materializes.

The principle is **Mormor everywhere around the subagent**. Three things, all required:

1. **Deliver the cheatsheet into each subagent's own context.** Not via `CLAUDE.md` / parent system prompt — those don't propagate (subagents receive only their own system prompt plus basic environment details). With the Agent SDK, include the cheatsheet text in each subagent's `AgentDefinition` prompt. In Claude Code, inject it via a `SubagentStart` hook in `settings.json` (optionally scoped per-agent with a `matcher`), emitting the cheatsheet as `additionalContext`.
2. **Author the subagent definition in Mormor**, and open it with a one-line self-declaration so the agent knows the channel is Mormor — e.g. *"respond using the Mormor cheatsheet provided; every label is a `### ` heading on its own line, content on the next."*
3. **Write the parent's dispatch brief in Mormor** (`### goal:` + `### note:`), so the child meets Mormor on the way *in*, not only in a reference card it might skim past.

Optional, for larger fleets: scope injection to agents you control (don't push the protocol onto third-party agents you don't own), and keep a per-agent override for agents where "default to brief" would drop required detail — e.g. an exhaustive security reviewer should be told to emit every finding even at low signal.

### What to expect

- Responses use `### label:` h3 headings as structural anchors, with content on the next line.
- Atomic answers (yes/no, a number, a status code with NO additional context) come back without labels — that's intended. Anything with a reason or named category uses `### done:` + `### note:`, even when the answer is short.
- Code, paths, error messages stay verbatim.
- The model may use markdown tables and bullet lists under labels — that's part of the compression.
- Compression varies by task; multi-paragraph tasks compress more than atomic outputs.
- Mormor changes how results are *presented*, not what the result is — reasoning capacity is unchanged.

---

## Project layout

```
mormor/
├── README.md          # this file — overview, empirical results, adoption notes
├── CHEATSHEET.md      # the protocol — paste into your system prompt
├── CHANGELOG.md       # version history
├── examples/          # short Mormor exchanges by use case
└── bench/             # benchmark + research infra (python run.py)
```

`CHEATSHEET.md` is the entire Mormor protocol — the spec, the cheatsheet, and the system-prompt artifact, all in one. There is no separate spec document; this README handles human-facing context, and `CHEATSHEET.md` is the authoritative definition of how to write Mormor.

---

## Status

Pre-1.0 experiment, single maintainer. Labels and behavior rules may change before v1.0 — try Mormor on experimental projects first.
