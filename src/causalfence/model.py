"""Strict, bounded trace contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

from causalfence.errors import ContractError

TRACE_FORMAT = "causalfence.trace.v1"
MAX_EVENTS = 256
_NAME = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_EVENT_KEYS = {
    "event_id",
    "step",
    "region",
    "session",
    "kind",
    "key",
    "observed",
    "context",
}
_TRACE_KEYS = {"format", "trace_id", "events"}


@dataclass(frozen=True, slots=True)
class Event:
    """One normalized client-visible operation."""

    event_id: str
    step: int
    region: str
    session: str
    kind: str
    key: str
    observed: str | None
    context: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "step": self.step,
            "region": self.region,
            "session": self.session,
            "kind": self.kind,
            "key": self.key,
            "observed": self.observed,
            "context": list(self.context),
        }


@dataclass(frozen=True, slots=True)
class Trace:
    """A normalized trace whose list order is its declared step order."""

    trace_id: str
    events: tuple[Event, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "format": TRACE_FORMAT,
            "trace_id": self.trace_id,
            "events": [event.to_dict() for event in self.events],
        }


def _as_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _exact_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        difference = sorted(actual ^ expected)
        raise ContractError(f"{label} fields differ: {difference}")


def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ContractError(f"{label} must match {_NAME.pattern}")
    return value


def _optional_name(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _name(value, label)


def _step(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_EVENTS:
        raise ContractError(f"{label} must be an integer in 1..{MAX_EVENTS}")
    return value


def _context(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ContractError(f"{label} must be a list")
    names = tuple(_name(item, f"{label} item") for item in value)
    if len(names) != len(set(names)):
        raise ContractError(f"{label} contains duplicates")
    if names != tuple(sorted(names)):
        raise ContractError(f"{label} must be sorted")
    return names


def parse_trace(document: object) -> Trace:
    """Validate and normalize a complete trace."""

    root = _as_object(document, "trace")
    _exact_keys(root, _TRACE_KEYS, "trace")
    if root["format"] != TRACE_FORMAT:
        raise ContractError(f"trace format must be {TRACE_FORMAT}")
    trace_id = _name(root["trace_id"], "trace_id")
    raw_events = root["events"]
    if not isinstance(raw_events, list) or not 1 <= len(raw_events) <= MAX_EVENTS:
        raise ContractError(f"events must contain 1..{MAX_EVENTS} entries")

    events: list[Event] = []
    for index, raw_event in enumerate(raw_events):
        value = _as_object(raw_event, f"events[{index}]")
        _exact_keys(value, _EVENT_KEYS, f"events[{index}]")
        kind = value["kind"]
        if kind not in {"read", "write"}:
            raise ContractError(f"events[{index}].kind must be read or write")
        observed = _optional_name(value["observed"], f"events[{index}].observed")
        if kind == "write" and observed is not None:
            raise ContractError(f"write {value['event_id']} cannot observe a version")
        events.append(
            Event(
                event_id=_name(value["event_id"], f"events[{index}].event_id"),
                step=_step(value["step"], f"events[{index}].step"),
                region=_name(value["region"], f"events[{index}].region"),
                session=_name(value["session"], f"events[{index}].session"),
                kind=cast(str, kind),
                key=_name(value["key"], f"events[{index}].key"),
                observed=observed,
                context=_context(value["context"], f"events[{index}].context"),
            )
        )

    expected_steps = list(range(1, len(events) + 1))
    if [event.step for event in events] != expected_steps:
        raise ContractError("event steps must be contiguous and match list order")
    event_ids = [event.event_id for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ContractError("event_id values must be unique")

    writes = {event.event_id: event for event in events if event.kind == "write"}
    for event in events:
        references = list(event.context)
        if event.observed is not None:
            references.append(event.observed)
        for reference in references:
            target = writes.get(reference)
            if target is None:
                raise ContractError(f"{event.event_id} references non-write {reference}")
            if target.step >= event.step:
                raise ContractError(f"{event.event_id} references non-prior write {reference}")
        if event.observed is not None and writes[event.observed].key != event.key:
            raise ContractError(f"{event.event_id} observes a version for another key")
    return Trace(trace_id=trace_id, events=tuple(events))
