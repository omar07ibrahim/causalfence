# Contributing

Thank you for improving CausalFence. Contributions should preserve
determinism, explicit claim boundaries, and reproducible evidence.

## Development setup

Use a supported CPython release (3.14.6 matches the quality job):

~~~bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps --require-hashes -r requirements/quality.txt
python -m pip install --no-build-isolation --no-deps -e .
~~~

Do not add credentials, private traces, personal data, proprietary fixtures, or
unlicensed assets. Use synthetic, reviewable examples.

## Required checks

Run the same core checks as CI:

~~~bash
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q --cov=causalfence --cov-report=term-missing --cov-fail-under=92
git diff --check
~~~

Changes to the analyzer, verifier, trace contract, fixture, report, or evidence
generator must also regenerate the tracked evidence through the
`Visual evidence` workflow and review every changed artifact. Do not hand-edit
generated evidence.

## Design constraints

- Keep the installed runtime dependency-free and offline.
- Preserve strict duplicate-key JSON parsing, bounded input, and exclusive
  output creation.
- Do not make wall-clock ordering part of the causal relation.
- Keep verification algorithmically independent from analyzer relation and
  ledger implementations.
- Bind new receipt fields canonically and cover mutation rejection.
- Describe witnesses as deterministic and bounded unless a global minimality
  proof is added.
- State whether every chart, benchmark, screenshot, and count is synthetic,
  measured, or inferred.

## Pull requests

Keep commits focused and explain the contract or security consequence of each
change. A pull request should include tests, documentation, and reproducible
visual evidence when user-visible output changes. All required workflows,
CodeQL, and review conversations must be green or resolved before merge.

The contents of `legacy/dtk-lpr-2025/` are a byte-identical provenance
snapshot. Do not modify, reformat, execute, package, or relicense them.
