# Trace and receipt contract

A trace has exactly `format`, `trace_id`, and `events`.
`format` is `causalfence.trace.v1`; the event list contains 1–256 entries.
JSON must be duplicate-key-free UTF-8 and at most 512 KiB.

## Event fields

| Field | Constraint |
|---|---|
| `event_id` | unique; also the version ID for a write |
| `step` | integer equal to the 1-based list position |
| `region` | restricted source-region label |
| `session` | restricted client-session label |
| `kind` | `read` or `write` |
| `key` | restricted logical-key label |
| `observed` | prior same-key write for a read, otherwise `null` |
| `context` | sorted, duplicate-free list of prior write IDs |

Names match `^[a-z][a-z0-9._-]{0,63}$`. Unknown fields are rejected. Every
reference must exist, identify a write, and occur at a smaller step. The step is
ordering evidence, not elapsed time; the contract accepts no wall-clock field.

## Receipt

A `causalfence.receipt.v1` object contains exactly:

- format, normalized trace, and trace SHA-256;
- declared relation and complete evidence edges;
- content-bound findings and exact summary;
- event/finding ledger and root;
- receipt SHA-256.

The verifier reconstructs every field. Missing or extra fields fail. Contract
and verification failures return CLI status 2 with bounded messages. Output
uses exclusive creation so invalid runs cannot replace existing artifacts.
