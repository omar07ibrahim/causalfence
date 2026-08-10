"""Analyzer-side graph construction using memoized predecessor walks."""

from __future__ import annotations

from dataclasses import dataclass

from causalfence.model import Trace

_EDGE_ORDER = {"session": 0, "context": 1, "read-from": 2}


@dataclass(frozen=True, slots=True)
class Relation:
    """Declared version order plus the complete evidence edge set."""

    version_ancestors: dict[str, frozenset[str]]
    version_edges: tuple[tuple[str, str], ...]
    trace_edges: tuple[tuple[str, str, str], ...]

    def descends_from(self, current: str | None, required: str) -> bool:
        if current is None:
            return False
        return current == required or required in self.version_ancestors[current]

    def context_carries(self, context: tuple[str, ...], required: str) -> bool:
        return any(self.descends_from(candidate, required) for candidate in context)

    def to_dict(self) -> dict[str, object]:
        return {
            "version_edges": [
                {"source": source, "target": target} for source, target in self.version_edges
            ],
            "version_ancestors": {
                version: sorted(ancestors)
                for version, ancestors in sorted(self.version_ancestors.items())
            },
            "trace_edges": [
                {"source": source, "target": target, "kind": kind}
                for source, target, kind in self.trace_edges
            ],
        }


def build_relation(trace: Trace) -> Relation:
    """Build deterministic relations without trusting wall-clock timestamps."""

    writes = [event for event in trace.events if event.kind == "write"]
    dependencies = {event.event_id: set(event.context) for event in writes}
    memo: dict[str, frozenset[str]] = {}

    def ancestors(version: str) -> frozenset[str]:
        cached = memo.get(version)
        if cached is not None:
            return cached
        result: set[str] = set()
        for dependency in sorted(dependencies[version]):
            result.add(dependency)
            result.update(ancestors(dependency))
        frozen = frozenset(result)
        memo[version] = frozen
        return frozen

    version_ancestors = {event.event_id: ancestors(event.event_id) for event in writes}
    version_edges = tuple(
        sorted(
            (dependency, event.event_id)
            for event in writes
            for dependency in event.context
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
        edge_set.update(
            (event_ids[index - 1], event_ids[index], "session")
            for index in range(1, len(event_ids))
        )
    step = {event.event_id: event.step for event in trace.events}
    trace_edges = tuple(
        sorted(
            edge_set,
            key=lambda edge: (
                step[edge[1]],
                _EDGE_ORDER[edge[2]],
                step[edge[0]],
                edge[0],
            ),
        )
    )
    return Relation(
        version_ancestors=version_ancestors,
        version_edges=version_edges,
        trace_edges=trace_edges,
    )
