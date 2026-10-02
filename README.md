# Mormor

**An agent communication protocol for compressed agent-to-agent and agent-to-user messages.**

I made Mormor to spend fewer tokens on Anthropic. My agents — and the subagents they start — send a lot of long text, and I pay for every token. Mormor is a small set of labels that makes them write shorter, without losing the important parts.

I'm on the Max20 plan and I kept hitting the limit. There is no bigger plan. After it you pay per API usage or move to another provider, and I don't want that now. Fewer tokens means I stay under the limit.

This is what I measured:

| | baseline | terse | mormor |
| --- | ---: | ---: | ---: |
| **Fable 5.1** — billed Δ | — | -14% | **-44%** |
| **Fable 5.1** — quality | 4.98 | 4.98 | 4.94 |
| **Opus 5.5** — billed Δ | — | -21% | **-46%** |
| **Opus 5.5** — quality | 4.96 | 4.96 | 4.95 |
| **Sonnet 5.5** — billed Δ | — | -29% | **-40%** |
| **Sonnet 5.5** — quality | 4.97 | 4.94 | 4.97 |

<sub>Billed Δ is vs the **baseline** (verbose-prose) variant; **terse** = "just be concise", **mormor** = the v6 cheatsheet. Quality is 1–5. In the benchmark every prompt repeats across runs, so the baseline caches too and billed Δ understates the compression; on the cache-independent response size, mormor answers are **0.51× baseline** on Fable 5.1, **0.49×** on Opus 5.5, and **0.54×** on Sonnet 5.5 (see [Empirical results](#empirical-results)).</sub>

Mormor saves the most on billed cost while holding quality at or near baseline on every model. Answers also come back faster — **about 36% quicker on Fable 5.1, ~35% on Opus 5.5, ~26% on Sonnet 5.5** — because there is less to write.

The cheatsheet is about 570 tokens — above Anthropic's 512-token cache minimum on all three models, so it bills at the cached rate. Every scenario is a billed win except short one-line answers, which come out about even; see [Empirical results](#empirical-results).

### How Mormor works

Mormor uses six labels rendered as level-3 markdown headings (`### goal:`, `### note:`, `### case:`, `### done:`, `### ask:`, `### test:`) on top of plain markdown. Agents replace prose connectives with labels and keep technical content verbatim. The result is shorter and easier to read — for other agents and for me skimming the output.

Here is an example — a parent agent sending a task to a child agent:

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

The child agent answers, also in Mormor:

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

These are clean examples — what good Mormor looks like. Real answers follow the same shape but the wording and line counts vary. See [`examples/`](./examples/) for more.

### How I use it

I use Mormor every day in a slash-command plugin I built for my own Claude Code workflow. This is how I do it — not the only way.

My main agent is instructed to talk to its subagents in Mormor — and since they run Mormor too, they report back in it. When it fans out to several at once, each brief is a labeled Mormor message, usually opening with `### goal:` and adding `### note:`, `### test:` and so on as the task needs; here the rows are collapsed to the `### goal:` line:

![Parallel subagents, each briefed with a labeled Mormor message collapsed to its goal line](assets/usage-subagents.png)

And here's another — running my commit command, the main agent opened a performance-reviewer subagent and gave it this Mormor brief, expanded here so you can read the full instruction (`### goal:` / `### note:` / `### test:`):

![Main agent, running my commit command, briefing a performance-reviewer subagent with an expanded Mormor goal/note/test brief](assets/usage-kit-commit.png)

Both cases are agent-to-agent, which is where Mormor saves the most (see the per-scenario table below).

### Caveats

**Pre-1.0.** Try it on an experimental project first to build confidence, and feel free to adapt the cheatsheet per-project if defaults don't fit your workflow. See [`CHANGELOG.md`](./CHANGELOG.md) for the current version.

**Tested models.** Mormor's headline numbers are from Sonnet 5.5, Opus 5.5, and Fable 5.1 (the latest tested version of each), all on all 5 scenarios. Earlier Sonnet 5, Fable 5, Opus 5, Opus 4.8, Opus 4.7, and Sonnet 4.6 results — and Fable 5.1's September run — are retained under [Earlier results](#earlier-results-superseded-model-versions). Haiku 4.5 was tested early on but consistently lost on billed cost on the smaller model, so it's not part of the tested set going forward.

---

## Getting started

There is nothing to install — Mormor is a vocabulary, not software. Open the current cheatsheet — [`cheatsheets/v6.md`](./cheatsheets/v6.md) (the recommended version; see [`cheatsheets/`](./cheatsheets/)) — paste it into your system prompt (or append it to `CLAUDE.md`), and use the labels in your messages. For a single agent that is the whole setup. Subagents need an extra step — see [Agent-to-agent setup](#agent-to-agent-setup).

---

## Why a protocol

Agents that talk to other agents (and to users in scripted work) write a lot of filler: hedging, side comments, different ways to say the same thing, polite openings. The real signal — code, paths, error strings, decisions — is a small part of the output.

My idea is simple: a small set of labels lets the model drop the filler without losing meaning. The labels carry what the prose used to say between the lines ("here is the result", "here is some context", "here is a condition").

The simplest alternative is just asking the model to be concise. In my benchmark that saves 14% (Fable 5.1) to 29% (Sonnet 5.5) on billed cost — useful on its own — but it stops there, because the savings come from fewer hedges, not from shorter structure. Mormor compresses further still (Fable 5.1 −44%, Opus 5.5 −46%, Sonnet 5.5 −40%) at about equal quality, and the biggest gaps are in agent-to-agent cases, where the labeled output is easy for the next agent to read.

---

## Empirical results

The headline table at the top aggregates 5 scenarios × 3 variants × 50 runs each, on Sonnet 5.5, Opus 5.5, and Fable 5.1. The terse-prose variant ("just be concise" without the protocol vocabulary) is the relevant comparison — it tells me how much of Mormor's gain comes from the labels and how much from simply asking the model to be brief.

**How the aggregate is computed.** Billed-cost percentages are **scenario-equal**: the per-scenario mean billed cost is summed across all 5 scenarios per (variant, model), then the delta is taken on the sums. Every scenario contributes equally regardless of how many turns it produces. This is the `AGGREGATE (scen-eq)` row in the bench's `BILLED-COST delta` matrices (see [bench/README.md](./bench/README.md)). Latency percentages are **row-equal**: the mean across every recorded row per (variant, model), as emitted by the bench's `mean latency` matrix.

**Cost is all-in.** The `billed` numbers above are computed on the SDK's `output_tokens`, which includes any extended-thinking tokens the model generated before the visible response — not just displayed text. Mormor's compression edge therefore reflects real wallet impact with no hidden-thinking blind spot. Runs use the SDK's `effort='low'` setting to dampen extended thinking; results at higher effort levels may differ.

**Caching note.** Billed savings assume the cheatsheet caches (cached input bills at 0.10×). The system prompt is cached as its own entry only above Anthropic's [minimum cacheable length](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — 512 tokens on Fable 5.1, Opus 5.5 and Sonnet 5.5 (1,024 on Sonnet 5 and Opus 4.8). v6 is about 570 tokens, so it caches; if you trim it, keep it above ~475 tokens, or it bills in full on every call. The *baseline* prompt is too short to cache on its own, but in the benchmark every prompt repeats across runs, so whole requests cache for all three variants — that narrows the billed gap without changing the compression. The cache-independent metrics — response-size ratio, latency, quality, compliance — are unaffected, and are the fairer comparison across models.

### Per-scenario billed-cost reduction (mormor v6 vs baseline)

| scenario | fable 5.1 | opus 5.5 | sonnet 5.5 |
| --- | ---: | ---: | ---: |
| `single_round_trip` (planning task) | -41% | -42% | -39% |
| `branching` (security review) | -44% | -47% | -47% |
| `multi_turn` (5-turn debugging) | -23% | -31% | -21% |
| `high_frequency` (classification) | -6% | +7% | +2% |
| `delegated_chain` (5-hop fan-out) | **-63%** | **-63%** | **-57%** |

The strongest scenario on every model is the agent-to-agent `delegated_chain`, where compression compounds across hops. `high_frequency` is about even: a one-line answer leaves little to compress, while every call still reads the cheatsheet from cache — mormor's answers are 19–30% shorter, which roughly pays for that read. The cache-independent **response-size ratio** tells the cleaner compression story: responses are ~0.51× baseline on Fable 5.1, ~0.49× on Opus 5.5, and ~0.54× on Sonnet 5.5. Quality stays within 0.04 of baseline on every model.

**v6 vs v5.** v6 is a subtraction: v5's rules, each said once, in about 570 tokens instead of 1,460. Every call reads the cheatsheet from cache, so on a one-line answer v5 cost more than mormor saved — `high_frequency` was a +21% to +33% billed loss. v6 brings that to about even and makes the whole suite cheaper: against the same baselines, Opus 5.5 goes from -36% to **-46%** billed (0.54× → 0.49× response size) and Sonnet 5.5 from -35% to **-40%** (0.59× → 0.54×). The one-line coverage rule also stops Sonnet 5.5 over-specifying planning answers (`single_round_trip` -15% → -39%). Fable 5.1 started writing longer answers after its September run, so it was re-measured; side by side on the current model (n=15), v5 is -35% and v6 -45%.

### Where Mormor shines

- **Agent-to-agent chains** — `delegated_chain` is Mormor's strongest scenario (-63% fable 5.1 / -63% opus 5.5 / -57% sonnet 5.5 billed). Compression compounds across hops; mormor's labeled outputs flow cleanly into downstream agents' inputs.
- **Code review and decision tables** — `case:` directly satisfies a severity→action classification framework; baseline+terse use prose headings + bold which compress less. `branching` posts -47% opus 5.5 / -47% sonnet 5.5 / -44% fable 5.1 with quality at 5.00.
- **Planning tasks** — `single_round_trip` saves -39% to -42% on all three models with quality at 5.00 (4.98 on Sonnet 5.5).
- **Keeping the model on task** — the prose variants occasionally slip into a degenerate loop on code-investigation prompts, re-emitting the same tool call until the output limit (Opus 5.5 baseline: 4 times in 850 calls; Fable 5.1 baseline: 23 times in its September run). Mormor never did. These runs are excluded from the numbers above.

### Where Mormor's compression doesn't pay as hard

- **High-frequency atomic classification** — `high_frequency` is about even on billed cost (-6% Fable 5.1, +2% Sonnet 5.5, +7% Opus 5.5): a one-line answer leaves little to compress, and every call still reads the cheatsheet from cache. Mormor's answers are 19–30% shorter, which roughly pays for that read.
- **Multi-turn debugging** — `multi_turn` saves least of the multi-call scenarios (-21% Sonnet 5.5, -23% Fable 5.1, -31% Opus 5.5). On Fable 5.1 its quality is 4.87 against 4.96 baseline: a brief follow-up turn occasionally drops a step the grader expects.

Per-scenario breakdowns, full methodology, and reproduction steps: [`bench/README.md`](./bench/README.md). Per-scenario sample exchanges live in [`examples/`](./examples/).

### Earlier results (superseded model versions)

Kept for reference as models advance. The headline above uses the latest tested version of each model; older runs move here — including runs from before a model's behaviour changed (Sonnet 5 in August, Fable 5.1 in September).

**Fable 5.1, September 2026** (n=50, cheatsheet v5 — superseded: Fable 5.1 later changed behaviour, re-measured above):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.90 |
| terse | -31% | 4.97 |
| **mormor** | **-46%** | **4.97** |

Per-scenario (mormor vs baseline): `single_round_trip` -42%, `branching` -36%, `multi_turn` -35%, `high_frequency` +25%, `delegated_chain` -67%. Response size 0.48× baseline.

**Sonnet 5, September 2026** (n=50, cheatsheet v5 — superseded by Sonnet 5.5):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.98 |
| terse | -28% | 4.98 |
| **mormor** | **-30%** | **4.97** |

Per-scenario (mormor vs baseline): `single_round_trip` +4%, `branching` -25%, `multi_turn` -28%, `high_frequency` +19%, `delegated_chain` -61%. Response size 0.60× baseline.

**Sonnet 5, August 2026** (n=50, cheatsheet v4 — superseded: Sonnet 5 later changed behaviour, re-measured in September above):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.98 |
| terse | -30% | 4.96 |
| **mormor** | **-65%** | **4.92** |

Per-scenario (mormor vs baseline): `single_round_trip` -64%, `branching` -75%, `multi_turn` -60%, `high_frequency` -41%, `delegated_chain` -67%.

**Opus 5** (n=50, cheatsheet v4 — superseded by Opus 5.5):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.98 |
| terse | -30% | 4.98 |
| **mormor** | **-61%** | **4.99** |

Per-scenario (mormor vs baseline): `single_round_trip` -44%, `branching` -74%, `multi_turn` -53%, `high_frequency` -38%, `delegated_chain` -74%.

**Fable 5** (n=50, cheatsheet v4, 4 scenarios — superseded by Fable 5.1; it declined the `delegated_chain` security-review chain under its usage policy):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 5.00 |
| terse | -33% | 4.94 |
| **mormor** | **-46%** | **4.98** |

Per-scenario (mormor vs baseline): `single_round_trip` -34%, `branching` -45%, `multi_turn` -54%, `high_frequency` -38%.

**Sonnet 4.6** (n=50, cheatsheet v3 — superseded by Sonnet 5):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.93 |
| terse | -44% | 4.90 |
| **mormor** | **-64%** | **4.90** |

Per-scenario (mormor vs baseline): `single_round_trip` -66%, `branching` -64%, `multi_turn` -55%, `high_frequency` -34%, `delegated_chain` -71%.

**Opus 4.8** (n=50, cheatsheet v3 — superseded by Opus 5):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.95 |
| terse | -24% | 4.94 |
| **mormor** | **-53%** | **4.86** |

Per-scenario (mormor vs baseline): `single_round_trip` -55%, `branching` -51%, `multi_turn` -49%, `high_frequency` -35%, `delegated_chain` -58%.

**Opus 4.7** (n=50, cheatsheet v1 — superseded by Opus 4.8):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.85 |
| terse | -20% | 4.85 |
| **mormor** | **-50%** | **4.87** |

Per-scenario (mormor vs baseline): `single_round_trip` -57%, `branching` -65%, `multi_turn` -32%, `high_frequency` -26%, `delegated_chain` -68%.

note: 4.7 billed costs aren't directly comparable to 4.8 — the SDK/CLI context regime changed between the runs (4.7 prompts carried more cached context, so baseline economics differ). Each model's run is internally consistent: all three variants were measured under the same regime, so the within-run mormor-vs-baseline deltas are sound.

---

## Agent-to-agent setup

This is the one part that needs more than pasting the cheatsheet. Subagents (Claude Code Task tool, Agent SDK sub-agents) run in a **fresh context** — no parent conversation, no parent system prompt. They *can* load your project `CLAUDE.md`, but that alone isn't enough: a cheatsheet sitting in passive memory doesn't reliably make a subagent follow Mormor. They comply when Mormor is the instruction handed to them up front — models follow the protocol they're addressed in. Leave it only in `CLAUDE.md` and subagents tend to reply in prose, so the savings across hops never happen.

The rule is **Mormor everywhere around the subagent** — delivered as a direct instruction, not just memory. Three things, all needed:

1. **Hand the cheatsheet to each subagent as direct context, not just `CLAUDE.md`.** With the Agent SDK, include the cheatsheet text in each subagent's `AgentDefinition` prompt. In Claude Code, inject it via a `SubagentStart` hook in `settings.json` (optionally scoped per-agent with a `matcher`), emitting the cheatsheet as `additionalContext`.
2. **Write the subagent definition in Mormor**, and open it with one line so the agent knows the channel is Mormor — e.g. *"respond using the Mormor cheatsheet provided; every label is a `### ` heading on its own line, content on the next."*
3. **Write the parent's task brief in Mormor** (`### goal:` + `### note:`), so the child meets Mormor on the way *in*, not only in a reference card it might skip.

For larger fleets (optional): only inject the cheatsheet into agents you own (don't push it onto third-party agents), and keep a per-agent override where "default to brief" would drop needed detail — e.g. tell a full security reviewer to report every finding even at low signal.

---

## Project layout

```
mormor/
├── README.md          # this file — overview, empirical results, agent-to-agent setup
├── cheatsheets/       # the protocol — frozen versions; paste the recommended one (see DEFAULT)
├── CHANGELOG.md       # version history
├── assets/            # screenshots used in this README
├── examples/          # short Mormor exchanges by use case
└── bench/             # benchmark + research infra (python run.py)
```
