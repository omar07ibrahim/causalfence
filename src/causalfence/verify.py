"""Independent receipt replay using a transitive-closure matrix.

This module deliberately does not import the analyzer, relation builder, ledger,
or engine. It reconstructs their public contract with a different relation
algorithm so mutations cannot pass by reusing the implementation under test.
"""

from __future__ import annotations

from collections import Counter
from typing import cast

from causalfence.canonical import sha256_value
from causalfence.engine import RECEIPT_FORMAT
from causalfence.errors import VerificationError
from causalfence.model import Event, Trace, parse_trace

_RULES = (
    "CAUSAL_CLOSURE",
    "READ_YOUR_WRITES",
    "MONOTONIC_READS",
    "WRITES_FOLLOW_READS",
    "MONOTONIC_WRITES",
)
_EDGE_ORDER = {"session": 0, "context": 1, "read-from": 2}


def _finding(
    rule: str,
    event: Event,
    witness_events: tuple[str, ...],
    missing_versions: tuple[str, ...],
    explanation: str,
) -> dict[str, object]:
    body: dict[str, object] = {
        "rule": rule,
        "session": event.session,
        "key": event.key,
        "at_event": event.event_id,
        "witness_events": list(witness_events),
        "missing_versions": list(missing_versions),
        "explanation": explanation,
    }
    return {"finding_id": "CF-" + sha256_value(body)[:12].upper(), **body}


def _replay(trace: Trace) -> tuple[
    list[dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    writes = [event for event in trace.events if event.kind == "write"]
    versions = [event.event_id for event in writes]
    index = {version: position for position, version in enumerate(versions)}
    reachable = [[False for _ in versions] for _ in versions]
    version_edges: list[tuple[str, str]] = []
    for event in writes:
        for dependency in event.context:
            reachable[index[dependency]][index[event.event_id]] = True
            version_edges.append((dependency, event.event_id))
    for pivot in range(len(versions)):
        for source in range(len(versions)):
            if reachable[source][pivot]:
                for target in range(len(versions)):
                    reachable[source][target] = (
                        reachable[source][target]
                        or reachable[pivot][target]
                    )

    ancestors = {
        target: {
            source
            for source in versions
            if reachable[index[source]][index[target]]
        }
        for target in versions
    }

    def descends(current: str | None, required: str) -> bool:
        return current is not None and (
            current == required or reachable[index[required]][index[current]]
        )

    def carries(context: tuple[str, ...], required: str) -> bool:
        return any(descends(candidate, required) for candidate in context)

    step = {event.event_id: event.step for event in trace.events}
    findings: list[dict[str, object]] = []
    for event in trace.events:
        referenced = set(event.context)
        if event.observed is not None:
            referenced.add(event.observed)
        missing = set()
        for version in referenced:
            missing.update(ancestors[version] - set(event.context))
        if missing:
            ordered = tuple(sorted(missing, key=lambda version: (step[version], version)))
            findings.append(
                _finding(
                    "CAUSAL_CLOSURE",
                    event,
                    (*ordered, event.event_id),
                    ordered,
                    f"event {event.event_id} omits causal ancestor(s): {', '.join(ordered)}",
                )
            )

        prior = [
            candidate
            for candidate in trace.events
            if candidate.step < event.step and candidate.session == event.session
        ]
        if event.kind == "read":
            prior_writes = [
                candidate
                for candidate in prior
                if candidate.kind == "write" and candidate.key == event.key
            ]
            if prior_writes:
                latest_write = prior_writes[-1]
                if not descends(event.observed, latest_write.event_id):
                    findings.append(
                        _finding(
                            "READ_YOUR_WRITES",
                            event,
                            (latest_write.event_id, event.event_id),
                            (latest_write.event_id,),
                            f"read {event.event_id} does not include session write "
                            f"{latest_write.event_id}",
                        )
                    )
            prior_reads = [
                candidate
                for candidate in prior
                if candidate.kind == "read"
                and candidate.key == event.key
                and candidate.observed is not None
            ]
            if prior_reads:
                latest_read = prior_reads[-1]
                assert latest_read.observed is not None
                if not descends(event.observed, latest_read.observed):
                    findings.append(
                        _finding(
                            "MONOTONIC_READS",
                            event,
                            (latest_read.event_id, event.event_id),
                            (latest_read.observed,),
                            f"read {event.event_id} moves behind observed version "
                            f"{latest_read.observed}",
                        )
                    )
        else:
            prior_reads = [
                candidate
                for candidate in prior
                if candidate.kind == "read" and candidate.observed is not None
            ]
            missing_reads = [
                candidate
                for candidate in prior_reads
                if candidate.observed is not None
                and not carries(event.context, candidate.observed)
            ]
            if missing_reads:
                latest_read = missing_reads[-1]
                assert latest_read.observed is not None
                findings.append(
                    _finding(
                        "WRITES_FOLLOW_READS",
                        event,
                        (latest_read.event_id, event.event_id),
                        (latest_read.observed,),
                        f"write {event.event_id} does not carry read version "
                        f"{latest_read.observed}",
                    )
                )
            prior_writes = [candidate for candidate in prior if candidate.kind == "write"]
            if prior_writes:
                latest_write = prior_writes[-1]
                if not descends(event.event_id, latest_write.event_id):
                    findings.append(
                        _finding(
                            "MONOTONIC_WRITES",
                            event,
                            (latest_write.event_id, event.event_id),
                            (latest_write.event_id,),
                            f"write {event.event_id} does not descend from session write "
                            f"{latest_write.event_id}",
                        )
                    )

    edge_set: set[tuple[str, str, str]] = set()
    sessions: dict[str, list[str]] = {}
    for event in trace.events:
        sessions.setdefault(event.session, []).append(event.event_id)
        edge_set.update((version, event.event_id, "context") for version in event.context)
        if event.observed is not None:
            edge_set.add((event.observed, event.event_id, "read-from"))
    for event_ids in sessions.values():
        for position in range(1, len(event_ids)):
            edge_set.add((event_ids[position - 1], event_ids[position], "session"))
    trace_edges = sorted(
        edge_set,
        key=lambda edge: (
            step[edge[1]],
            _EDGE_ORDER[edge[2]],
            step[edge[0]],
            edge[0],
        ),
    )
    relation: dict[str, object] = {
        "version_edges": [
            {"source": source, "target": target}
            for source, target in sorted(version_edges)
        ],
        "version_ancestors": {
            version: sorted(ancestors[version]) for version in sorted(versions)
        },
        "trace_edges": [
            {"source": source, "target": target, "kind": kind}
            for source, target, kind in trace_edges
        ],
    }
    counts = Counter(str(finding["rule"]) for finding in findings)
    violating = {str(finding["at_event"]) for finding in findings}
    summary: dict[str, object] = {
        "events": len(trace.events),
        "writes": len(writes),
        "reads": len(trace.events) - len(writes),
        "sessions": len({event.session for event in trace.events}),
        "regions": len({event.region for event in trace.events}),
        "trace_edges": len(trace_edges),
        "version_edges": len(version_edges),
        "findings": len(findings),
        "violating_events": len(violating),
        "conformant_events": len(trace.events) - len(violating),
        "rule_counts": {rule: counts[rule] for rule in _RULES},
    }
    return findings, summary, relation


def _ledger(
    trace: Trace, findings: list[dict[str, object]]
) -> tuple[list[dict[str, object]], str]:
    payloads: list[tuple[str, object]] = [
        ("event", event.to_dict()) for event in trace.events
    ]
    payloads.extend(("finding", finding) for finding in findings)
    previous = "0" * 64
    entries: list[dict[str, object]] = []
    for position, (kind, payload) in enumerate(payloads):
        material: dict[str, object] = {
            "index": position,
            "kind": kind,
            "previous_sha256": previous,
            "payload_sha256": sha256_value(payload),
        }
        digest = sha256_value(material)
        entries.append({**material, "entry_sha256": digest})
        previous = digest
    return entries, previous


def verify_receipt(document: object) -> dict[str, object]:
    """Replay every receipt field independently and return its summary."""

    if not isinstance(document, dict):
        raise VerificationError("receipt must be an object")
    receipt = cast(dict[str, object], document)
    if receipt.get("format") != RECEIPT_FORMAT:
        raise VerificationError(f"receipt format must be {RECEIPT_FORMAT}")
    try:
        trace = parse_trace(receipt["trace"])
    except (KeyError, ValueError) as exc:
        raise VerificationError("receipt trace is invalid") from exc

    findings, summary, relation = _replay(trace)
    ledger, root = _ledger(trace, findings)
    core: dict[str, object] = {
        "format": RECEIPT_FORMAT,
        "trace": trace.to_dict(),
        "trace_sha256": sha256_value(trace.to_dict()),
        "relation": relation,
        "findings": findings,
        "summary": summary,
        "ledger": ledger,
        "ledger_root_sha256": root,
    }
    expected = {**core, "receipt_sha256": sha256_value(core)}
    if set(receipt) != set(expected):
        raise VerificationError("receipt fields differ")
    for key, value in expected.items():
        if receipt[key] != value:
            raise VerificationError(f"receipt {key} does not replay")
    return summary
