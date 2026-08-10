"""Strict trace schema and reference-integrity tests."""

from __future__ import annotations

from typing import cast

import pytest

from causalfence.errors import ContractError
from causalfence.model import TRACE_FORMAT, parse_trace
from conftest import cloned


def _events(document: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], document["events"])


def test_fixture_normalizes_without_change(incident: dict[str, object]) -> None:
    trace = parse_trace(incident)
    assert trace.to_dict() == incident
    assert trace.trace_id == "synthetic-three-region-incident-v1"
    assert len(trace.events) == 16


def test_trace_is_immutable(incident: dict[str, object]) -> None:
    trace = parse_trace(incident)
    with pytest.raises((AttributeError, TypeError)):
        trace.events[0].step = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("format", "other", "trace format"),
        ("trace_id", "UPPER", "trace_id"),
        ("trace_id", "", "trace_id"),
    ],
)
def test_trace_header_mutations_are_rejected(
    incident: dict[str, object], field: str, value: object, message: str
) -> None:
    document = cloned(incident)
    document[field] = value
    with pytest.raises(ContractError, match=message):
        parse_trace(document)


def test_trace_extra_field_is_rejected(incident: dict[str, object]) -> None:
    document = cloned(incident)
    document["unexpected"] = True
    with pytest.raises(ContractError, match="fields differ"):
        parse_trace(document)


def test_empty_event_list_is_rejected(incident: dict[str, object]) -> None:
    document = cloned(incident)
    document["events"] = []
    with pytest.raises(ContractError, match="events must contain"):
        parse_trace(document)


@pytest.mark.parametrize(
    ("index", "field", "value", "message"),
    [
        (0, "kind", "delete", "kind"),
        (0, "step", True, "integer"),
        (0, "event_id", "W01", "must match"),
        (0, "region", "us east", "must match"),
        (0, "observed", "w01", "cannot observe"),
        (4, "context", ["w02", "w01"], "must be sorted"),
        (4, "context", ["w01", "w01"], "contains duplicates"),
        (3, "context", ["r01"], "non-write"),
        (1, "context", ["w02"], "non-prior"),
        (1, "observed", "w02", "another key"),
    ],
)
def test_event_mutations_are_rejected(
    incident: dict[str, object],
    index: int,
    field: str,
    value: object,
    message: str,
) -> None:
    document = cloned(incident)
    _events(document)[index][field] = value
    with pytest.raises(ContractError, match=message):
        parse_trace(document)


def test_event_extra_field_is_rejected(incident: dict[str, object]) -> None:
    document = cloned(incident)
    _events(document)[0]["wall_clock"] = "untrusted"
    with pytest.raises(ContractError, match="fields differ"):
        parse_trace(document)


def test_duplicate_event_id_is_rejected(incident: dict[str, object]) -> None:
    document = cloned(incident)
    _events(document)[1]["event_id"] = "w01"
    with pytest.raises(ContractError, match="unique"):
        parse_trace(document)


def test_non_contiguous_steps_are_rejected(incident: dict[str, object]) -> None:
    document = cloned(incident)
    _events(document)[4]["step"] = 9
    with pytest.raises(ContractError, match="contiguous"):
        parse_trace(document)


def test_context_must_be_a_list(incident: dict[str, object]) -> None:
    document = cloned(incident)
    _events(document)[0]["context"] = "w01"
    with pytest.raises(ContractError, match="must be a list"):
        parse_trace(document)


def test_format_constant_is_explicit() -> None:
    assert TRACE_FORMAT == "causalfence.trace.v1"
