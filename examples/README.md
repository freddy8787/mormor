# Examples

Concrete Mormor exchanges, one per benchmark scenario. Each file is named after its scenario in `bench/scenarios.py` (kebab-case ↔ snake-case mapping).

| file | scenario | demonstrates |
| --- | --- | --- |
| [`single-round-trip.md`](./single-round-trip.md) | `single_round_trip` | one-shot task with full answer in one message; `goal:` + `### steps` + `done:` carrying code blocks |
| [`branching.md`](./branching.md) | `branching` | code review with severity classification; `case:` with a markdown table |
| [`multi-turn.md`](./multi-turn.md) | `multi_turn` | 5-turn debugging conversation; mixing `done:`, `note:`, `ask:` across turns |
| [`high-frequency.md`](./high-frequency.md) | `high_frequency` | one-line categorization at high call rate; atomic vs multi-part outputs |
| [`delegated-chain.md`](./delegated-chain.md) | `delegated_chain` | 5-hop fan-out (parent → 2 children → parent synthesize); compounding compression |

These are idealized exchanges paired with real benchmark numbers — what good Mormor looks like at the response level. Real responses vary slightly; the protocol accepts a range of valid forms.
