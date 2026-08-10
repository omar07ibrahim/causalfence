# Changelog

All notable changes to CausalFence are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-10

### Added

- Strict duplicate-key-free bounded trace contract for up to 512 KiB and 256
  events.
- Deterministic checks for causal closure, read-your-writes, monotonic reads,
  writes-follow-reads, and monotonic writes.
- Content-bound local witnesses and a canonical SHA-256 event/finding ledger.
- Independent Floyd–Warshall receipt verifier.
- Offline CLI for analyze, verify, inspect, and self-contained HTML report.
- Synthetic 16-event multi-region fixture with nine replayable findings.
- 60-test suite with 97.78% measured line coverage and CPython 3.11–3.14
  compatibility.
- Reproducible desktop, mobile, CLI, diagram, chart, GIF, HTML, JSON, and
  manifest evidence.
- Byte-identical archival preservation of the repository's original 2025 DTK
  LPR upload, excluded from the package and Apache-2.0 grant.

[Unreleased]: https://github.com/omar07ibrahim/causalfence/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/omar07ibrahim/causalfence/releases/tag/v0.1.0
