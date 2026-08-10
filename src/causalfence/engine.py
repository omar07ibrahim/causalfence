"""Compose deterministic analysis receipts."""

from __future__ import annotations

from causalfence.analyze import analyze
from causalfence.canonical import sha256_value
from causalfence.ledger import build_ledger
from causalfence.model import parse_trace

RECEIPT_FORMAT = "causalfence.receipt.v1"


def analyze_document(document: object) -> dict[str, object]:
    """Validate a trace and return its complete deterministic receipt."""

    trace = parse_trace(document)
    findings, summary, relation = analyze(trace)
    ledger, ledger_root = build_ledger(trace, findings)
    core: dict[str, object] = {
        "format": RECEIPT_FORMAT,
        "trace": trace.to_dict(),
        "trace_sha256": sha256_value(trace.to_dict()),
        "relation": relation.to_dict(),
        "findings": findings,
        "summary": summary,
        "ledger": ledger,
        "ledger_root_sha256": ledger_root,
    }
    return {**core, "receipt_sha256": sha256_value(core)}
