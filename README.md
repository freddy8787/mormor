# Mormor

**An agent communication protocol for compressed agent-to-agent and agent-to-user messages.**

I made Mormor to spend fewer tokens on Anthropic. My agents — and the subagents they start — send a lot of long text, and I pay for every token. Mormor is a small set of labels that makes them write shorter, without losing the important parts.

I'm on the Max20 plan and I kept hitting the limit. There is no bigger plan. After it you pay per API usage or move to another provider, and I don't want that now. Fewer tokens means I stay under the limit.

This is what I measured:

| | baseline | terse | mormor |
| --- | ---: | ---: | ---: |
| **Fable 5** — billed Δ * | — | -31% | **-45%** |
| **Fable 5** — quality | 4.99 | 4.96 | 4.98 |
| **Opus 4.8** — billed Δ | — | -24% | **-53%** |
| **Opus 4.8** — quality | 4.95 | 4.94 | 4.86 |
| **Sonnet 5** — billed Δ | — | -29% | **-62%** |
| **Sonnet 5** — quality | 4.96 | 4.95 | 4.90 |

<sub>Billed Δ is vs the **baseline** (verbose-prose) variant; **terse** = "just be concise", **mormor** = the v3 cheatsheet. Quality is 1–5. <br>\* Fable 5 is aggregated over 4 of the 5 scenarios — `delegated_chain` is excluded because Fable declines the agent-to-agent security review under its usage policy (see [Tested models](#caveats)). Opus 4.8 and Sonnet 5 cover all 5.</sub>

Mormor saves the most on billed cost while holding quality within ~0.1 of baseline on every model. Answers also come back faster — **about 46% quicker on Sonnet 5, ~26% on Opus 4.8, ~17% on Fable 5** — because there is less to write.

The cheatsheet caches on all three models — it clears Anthropic's 1,024-token cache minimum, so the prefix bills at the cached rate — and every measured scenario is a billed win, including high-frequency one-line classification. See [Empirical results](#empirical-results).

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

**Tested models.** Mormor's headline numbers are from Sonnet 5, Opus 4.8, and Fable 5 (the latest tested version of each). Fable 5 is measured on 4 of the 5 scenarios: it declines the `delegated_chain` agent-to-agent security review under its usage policy, so that scenario is excluded for Fable (the same review as a single shot — `branching` — completes normally). Earlier Opus 4.7 and Sonnet 4.6 results are retained under [Earlier results](#earlier-results-superseded-model-versions). Haiku 4.5 was tested early on but consistently lost on billed cost on the smaller model, so it's not part of the tested set going forward.

---

## Getting started

There is nothing to install — Mormor is a vocabulary, not software. Open the current cheatsheet — [`cheatsheets/v3.md`](./cheatsheets/v3.md) (the recommended version; see [`cheatsheets/`](./cheatsheets/)) — paste it into your system prompt (or append it to `CLAUDE.md`), and use the labels in your messages. For a single agent that is the whole setup. Subagents need an extra step — see [Agent-to-agent setup](#agent-to-agent-setup).

---

## Why a protocol

Agents that talk to other agents (and to users in scripted work) write a lot of filler: hedging, side comments, different ways to say the same thing, polite openings. The real signal — code, paths, error strings, decisions — is a small part of the output.

My idea is simple: a small set of labels lets the model drop the filler without losing meaning. The labels carry what the prose used to say between the lines ("here is the result", "here is some context", "here is a condition").

The simplest alternative is just asking the model to be concise. In my benchmark that saves 24% (Opus 4.8) to 31% (Fable 5) on billed cost — useful on its own — but it stops there, because the savings come from fewer hedges, not from shorter structure. Mormor compresses further still (Opus 4.8 −53%, Sonnet 5 −62%, Fable 5 −45%) at near-equal quality, and the biggest gaps are in agent-to-agent cases, where the labeled output is easy for the next agent to read.

---

## Empirical results

The headline table at the top aggregates 5 scenarios × 3 variants × 50 runs each, on Sonnet 5 and Opus 4.8 (and Fable 5 over 4 scenarios). The terse-prose variant ("just be concise" without the protocol vocabulary) is the relevant comparison — it tells me how much of Mormor's gain comes from the labels and how much from simply asking the model to be brief.

**How the aggregate is computed.** Billed-cost percentages are **scenario-equal**: the per-scenario mean billed cost is summed across all 5 scenarios per (variant, model), then the delta is taken on the sums. Every scenario contributes equally regardless of how many turns it produces. This is the `AGGREGATE (scen-eq)` row in the bench's `BILLED-COST delta` matrices (see [bench/README.md](./bench/README.md)). Latency percentages are **row-equal**: the mean across every recorded row per (variant, model), as emitted by the bench's `mean latency` matrix.

**Cost is all-in.** The `billed` numbers above are computed on the SDK's `output_tokens`, which includes any extended-thinking tokens the model generated before the visible response — not just displayed text. Mormor's compression edge therefore reflects real wallet impact with no hidden-thinking blind spot. Runs use the SDK's `effort='low'` setting to dampen extended thinking; results at higher effort levels may differ.

**Caching note.** Billed savings assume the cheatsheet caches (cached input bills at 0.10×), which needs the prompt prefix to clear Anthropic's [1,024-token minimum](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). The cheatsheet clears it on Sonnet 5, Opus 4.8, and Fable 5, so it caches on all three. The cache-independent metrics — response-size ratio, latency, quality, compliance — are unaffected.

### Per-scenario billed-cost reduction (mormor v3 vs baseline)

| scenario | fable 5 | opus 4.8 | sonnet 5 |
| --- | ---: | ---: | ---: |
| `single_round_trip` (planning task) | -42% | -55% | -63% |
| `branching` (security review) | -42% | -51% | **-71%** |
| `multi_turn` (5-turn debugging) | -49% | -49% | -58% |
| `high_frequency` (classification) | -41% | -35% | -40% |
| `delegated_chain` (5-hop fan-out) | — † | **-58%** | **-62%** |

<sub>† Fable declines the `delegated_chain` security-review chain under its usage policy — excluded for Fable. See [Tested models](#caveats).</sub>

Every measured scenario is a billed win on every model. The strongest are the agent-to-agent (`delegated_chain`) and multi-turn scenarios, where compression compounds across turns/hops; `high_frequency` is the smallest, since a one-line answer leaves little to compress. The cache-independent **response-size ratio** tells the cleaner compression story: responses are ~0.30× baseline on Sonnet 5 and 0.33× on Opus 4.8. Fable compresses less in raw size (~0.6×, its baselines are already terser) but still wins on billed cost through caching.

### Where Mormor shines

- **Agent-to-agent chains** — `delegated_chain` is Mormor's strongest scenario (-62% sonnet 5 / -58% opus billed). Compression compounds across hops; mormor's labeled outputs flow cleanly into downstream agents' inputs. (Fable declines this security-review chain, so it isn't measured there.)
- **Code review and decision tables** — `case:` directly satisfies a severity→action classification framework; baseline+terse use prose headings + bold which compress less. `branching` posts -71% sonnet 5 / -51% opus / -42% fable with quality near 5.00.
- **Multi-turn work** — `multi_turn` wins across the board (-58% sonnet 5 / -49% opus / -49% fable).

### Where Mormor's compression doesn't pay as hard

- **High-frequency atomic classification** — `high_frequency` is a billed win on every model (-40% sonnet 5 / -35% opus / -41% fable), but it's Mormor's *smallest* win on raw size: a one-line answer leaves almost nothing to compress, so the saving comes mostly from caching, not from a shorter response. Fine to use — the payoff is just modest.
- **A few soft quality cells** — Mormor stays within ~0.1 of baseline everywhere, but two cells sit at the low end: Opus `multi_turn` mormor quality is 4.72 (format compliance 94%, vs 100% elsewhere), and Sonnet 5 `single_round_trip` mormor quality is 4.64. Both still land the answer; the point off comes from tighter phrasing, not dropped content.

Per-scenario breakdowns, full methodology, and reproduction steps: [`bench/README.md`](./bench/README.md). Per-scenario sample exchanges live in [`examples/`](./examples/).

### Earlier results (superseded model versions)

Kept for reference as models advance. The headline above uses the latest tested version of each model; older runs move here.

**Sonnet 4.6** (n=50, cheatsheet v3 — superseded by Sonnet 5):

| variant | billed Δ | quality |
| --- | ---: | ---: |
| baseline | — | 4.93 |
| terse | -44% | 4.90 |
| **mormor** | **-64%** | **4.90** |

Per-scenario (mormor vs baseline): `single_round_trip` -66%, `branching` -64%, `multi_turn` -55%, `high_frequency` -34%, `delegated_chain` -71%.

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
