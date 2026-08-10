# Frozen DTK LPR upload (2025)

This directory preserves the original 19 February 2025 `test1` upload byte-for-byte for provenance. Every original blob SHA-1 and size is recorded in [`manifest.json`](manifest.json).

## Status

This snapshot is historical evidence, not a supported application. It depends on unbundled proprietary DTK LPR/DTKVID native libraries plus desktop, OpenCV, Pillow, NumPy, SQLite, and Levenshtein components. The upload supplied no dependency lock, SDK binaries or license grant, fixtures, tests, usage guide, or reproducible runtime. It also contains a hard-coded single-character local UI gate, which is not an authentication design.

Do not deploy or execute it as a service. It is excluded from CausalFence packaging, linting, tests, CodeQL paths, and the root Apache-2.0 license. Rights in third-party SDKs and this frozen historical snapshot are not expanded by the new project.

## Integrity check

The source commit is `1539c298736daa101bd13cf4329238971c45b988`. To compare an entry, read its original blob from that commit and its archived blob from this directory; the object IDs must match the manifest.
