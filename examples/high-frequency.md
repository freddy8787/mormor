# Classification (high-frequency) example

A high-frequency classifier task: each call gets one email subject and produces a category + one-line reason. Same call shape repeated many times — the kind of workload where every byte saved compounds across thousands of calls.

This scenario asks for a category PLUS a reason, so it tests Mormor's multi-part output handling (`### done:` + `### note:`). Per the cheatsheet, a category name is "nameable" content, not atomic, so even category-only prompts get the labeled form — see [Atomic-output note](#atomic-output-note) at the end.

## User prompt

The same template is sent across all variants. Only the SYSTEM PROMPT differs.

```
Classify this email subject (transactional / marketing / personal / spam) + one-line reason:

"<subject>"
```

The benchmark runs 5 different subjects through this template:

| subject | expected category |
| --- | --- |
| `Your order #12345 has shipped` | transactional |
| `FLASH SALE: 50% off everything ends tonight!` | marketing |
| `Hey, can we grab coffee tomorrow?` | personal |
| `CONGRATULATIONS WINNER! Claim your $1000 prize NOW` | spam |
| `Your monthly statement is ready` | transactional |

## Benchmark results

Sonnet 5.5 + Opus 5.5 + Fable 5.1, n=50 runs × 5 emails each, cheatsheet v5. Figures are **response-size** reduction vs baseline (cache-independent); for billed cost and the caching caveat, see the [README](../README.md#empirical-results).

| variant | fable 5.1 size Δ | fable 5.1 quality | opus 5.5 size Δ | opus 5.5 quality | sonnet 5.5 size Δ | sonnet 5.5 quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (verbose prose) | — | 5.00 | — | 5.00 | — | 5.00 |
| terse (concise prose) | -9% | 5.00 | -7% | 5.00 | -11% | 5.00 |
| **mormor (v5)** | **-23%** | **5.00** | **-15%** | **5.00** | **-25%** | **5.00** |

note: this is Mormor's weakest scenario — the baseline is already a one-line classification + reason, so there's little to compress; the `### done:`/`### note:` labels add a little structure, leaving mormor only modestly smaller than baseline (-15% to -25%). Quality is perfect (5.00 across the board). On **billed** cost it's a small loss on all three models: with a one-line answer the saving used to come from caching rather than a shorter response, and on the current CLI the baseline prompt caches too (see the [README](../README.md#empirical-results)).

## Sample responses (Sonnet, first email — `Your order #12345 has shipped` → transactional)

### baseline

```
**Classification: Transactional**

**Reason:** It's an automated order status notification triggered by a
specific customer action (a purchase), containing a unique order
reference number.
```
(47 vis_out tokens)

### terse

```
**transactional** — Order shipment notification triggered by a specific
user action (purchase).
```
(23 vis_out tokens)

### mormor

```
### done:
transactional

### note:
order status notification triggered by a specific user action (purchase)
```
(~28 vis_out tokens)

note: visible output is similar across terse and mormor here (~20–25 tokens) — the shape differs (mormor uses h3 labels, terse uses bold + dash), but there's no big byte gap on an already-tiny answer.

## Atomic-output note

The cheatsheet reserves atomic-output (bare value, no labels) for **just numbers, yes/no, or status codes with no context** — like `42` or `yes`. A category name like `transactional` is "nameable", which counts as multi-part, so it goes under `### done:` (with the reason in `### note:`) — never a bare `transactional → reason` line. Even when the prompt asks for only the category with no reason, the labeled form is the protocol-compliant shape.
