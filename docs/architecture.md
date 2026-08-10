# Architecture and semantics

CausalFence analyzes a bounded client-visible trace. It does not connect to a
database or infer a history from wall-clock timestamps.

## Data model

Each event has a unique ID, contiguous step, region, session, operation kind,
key, optional observed write, and a sorted context of declared write versions.
A write's event ID is its version ID.

Every reference must name a prior write. A read may only observe a version for
the same key. Time-travel references and version cycles are invalid inputs, not
ambiguous findings.

## Two relations

### Declared version dependency

For each write version `v`, an edge `u -> v` exists for every `u` in that
write's context. Transitive ancestry answers whether one declared version is at
least as new as another.

The analyzer memoizes predecessor-set unions. These sets directly expose missing
versions.

### Complete trace evidence

The receipt separately records consecutive session-order edges, all context
edges into any event, and read-from edges. Session-order is not used to pretend
that a missing context was propagated: that missing carry is exactly what the
session-guarantee checks detect.

## Checks

Causal closure requires all ancestors of every context or observed version to
appear in the event context.

For a read, read-your-writes compares the latest prior same-key session write
with the observation. Monotonic-reads compares the latest prior non-empty
same-key session read.

For a write, writes-follow-reads requires its context to carry every previously
observed session version; the latest missing read becomes the witness.
Monotonic-writes requires the latest prior session write to be an ancestor.

A finding is local and deterministic, not a globally minimum counterexample.

## Receipt and verifier

Canonical JSON uses sorted keys, compact separators, UTF-8, and no non-finite
numbers. Events enter a SHA-256 chain followed by findings. Each entry binds its
index, kind, previous digest, and payload digest.

The receipt binds the normalized trace, both relations, all findings, summary,
ledger, and root. Its final digest covers every field except itself.

`verify.py` does not import the analyzer, relation builder, ledger, or engine.
It creates a write-version matrix, computes Floyd–Warshall transitive closure,
re-derives findings and summary, rebuilds the ledger, and compares every field.
Shared code is limited to the strict parser and canonical hashing helper.

## Bounds

Traces are capped at 256 events and 512 KiB; receipts at 2 MiB. Identifiers are
at most 64 restricted characters. Independent closure is `O(W^3)` time and
`O(W^2)` memory. Analyzer predecessor sets can also approach cubic work for a
dense bounded graph. These are correctness bounds, not benchmarks.
