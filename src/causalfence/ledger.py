"""Hash-chain the normalized trace and every analyzer finding."""

from __future__ import annotations

from causalfence.canonical import sha256_value
from causalfence.model import Trace


def build_ledger(
    trace: Trace, findings: list[dict[str, object]]
) -> tuple[list[dict[str, object]], str]:
    """Build an append-only canonical hash chain."""

    payloads: list[tuple[str, object]] = [("event", event.to_dict()) for event in trace.events]
    payloads.extend(("finding", finding) for finding in findings)
    previous = "0" * 64
    entries: list[dict[str, object]] = []
    for index, (kind, payload) in enumerate(payloads):
        material: dict[str, object] = {
            "index": index,
            "kind": kind,
            "previous_sha256": previous,
            "payload_sha256": sha256_value(payload),
        }
        entry_sha256 = sha256_value(material)
        entries.append({**material, "entry_sha256": entry_sha256})
        previous = entry_sha256
    return entries, previous
