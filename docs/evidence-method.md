# Evidence generation and verification

The evidence comes from installed CausalFence commands and real local Chromium
rendering. No screenshot is a hand-authored mockup.

## Source binding

The workflow finds the latest commit that changed the application, fixture,
generator, workflow, or dependency locks. The manifest stores that commit and
tree plus SHA-256 and size for every source input. An evidence-only commit
therefore preserves the source binding; a later source change invalidates stale
evidence.

## Application and browser stages

Python 3.14.6 installs hash-locked tools and the package without runtime
dependencies. The installed CLI runs analyze, verify, inspect, and report in a
private runner directory. Preparation independently verifies the receipt,
re-renders HTML, rejects sensitive markers, and renders four SVGs from receipt
fields.

A Python 3.12.3 downloader obtains exactly five hash-locked evidence wheels.
Capture runs in the digest-pinned Playwright Linux/amd64 image with network
disabled, source read-only, all capabilities dropped, no-new-privileges, a
non-root UID/GID, and bounded PIDs, memory, CPU, shared memory, and temporary
storage. Versions are Playwright 1.62.0, Pillow 12.3.0, and Chromium
151.0.7922.34.

## Final replay

The final Python 3.14.6 stage validates the exact 13-file set, source and
artifact hashes, PNG/GIF dimensions, SVG structure, three distinct GIF frames,
independent receipt replay, exact HTML replay, manifest counts and digests,
sensitive-text markers, and a clean worktree.

The current record is
[`causalfence-evidence.json`](evidence/causalfence-evidence.json).

This establishes reproducibility on the pinned Linux/amd64 toolchain. It is not
a cross-browser pixel, accessibility, database, or production certification.
