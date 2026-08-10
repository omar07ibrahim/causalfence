"""Detect bounded causal and session-guarantee violations."""

from __future__ import annotations

from collections import Counter

from causalfence.canonical import sha256_value
from causalfence.model import Event, Trace
from causalfence.relation import Relation, build_relation

RULES = (
    "CAUSAL_CLOSURE",
    "READ_YOUR_WRITES",
    "MONOTONIC_READS",
    "WRITES_FOLLOW_READS",
    "MONOTONIC_WRITES",
)


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


def _prior(trace: Trace, event: Event) -> list[Event]:
    return [
        candidate
        for candidate in trace.events
        if candidate.step < event.step and candidate.session == event.session
    ]


def analyze(trace: Trace) -> tuple[list[dict[str, object]], dict[str, object], Relation]:
    """Analyze one normalized trace with memoized version ancestry."""

    relation = build_relation(trace)
    step = {event.event_id: event.step for event in trace.events}
    findings: list[dict[str, object]] = []

    for event in trace.events:
        referenced = set(event.context)
        if event.observed is not None:
            referenced.add(event.observed)
        missing: set[str] = set()
        for version in referenced:
            missing.update(relation.version_ancestors[version] - set(event.context))
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

        prior = _prior(trace, event)
        if event.kind == "read":
            writes = [
                candidate
                for candidate in prior
                if candidate.kind == "write" and candidate.key == event.key
            ]
            if writes:
                latest_write = writes[-1]
                if not relation.descends_from(event.observed, latest_write.event_id):
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
            reads = [
                candidate
                for candidate in prior
                if candidate.kind == "read"
                and candidate.key == event.key
                and candidate.observed is not None
            ]
            if reads:
                latest_read = reads[-1]
                assert latest_read.observed is not None
                if not relation.descends_from(event.observed, latest_read.observed):
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
            reads = [
                candidate
                for candidate in prior
                if candidate.kind == "read" and candidate.observed is not None
            ]
            missing_reads = [
                candidate
                for candidate in reads
                if candidate.observed is not None
                and not relation.context_carries(event.context, candidate.observed)
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
            writes = [candidate for candidate in prior if candidate.kind == "write"]
            if writes:
                latest_write = writes[-1]
                if not relation.descends_from(event.event_id, latest_write.event_id):
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

    counts = Counter(str(finding["rule"]) for finding in findings)
    violating_events = {str(finding["at_event"]) for finding in findings}
    summary: dict[str, object] = {
        "events": len(trace.events),
        "writes": sum(event.kind == "write" for event in trace.events),
        "reads": sum(event.kind == "read" for event in trace.events),
        "sessions": len({event.session for event in trace.events}),
        "regions": len({event.region for event in trace.events}),
        "trace_edges": len(relation.trace_edges),
        "version_edges": len(relation.version_edges),
        "findings": len(findings),
        "violating_events": len(violating_events),
        "conformant_events": len(trace.events) - len(violating_events),
        "rule_counts": {rule: counts[rule] for rule in RULES},
    }
    return findings, summary, relation
