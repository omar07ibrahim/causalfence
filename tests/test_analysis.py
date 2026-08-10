"""Analyzer semantics and receipt determinism."""

from __future__ import annotations

from typing import cast

from causalfence.analyze import RULES
from causalfence.engine import analyze_document
from causalfence.verify import verify_receipt


def _findings(receipt: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], receipt["findings"])


def _summary(receipt: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], receipt["summary"])


def _clean_trace() -> dict[str, object]:
    return {
        "format": "causalfence.trace.v1",
        "trace_id": "clean-session",
        "events": [
            {
                "event_id": "w1",
                "step": 1,
                "region": "r1",
                "session": "s1",
                "kind": "write",
                "key": "alpha",
                "observed": None,
                "context": [],
            },
            {
                "event_id": "r1",
                "step": 2,
                "region": "r2",
                "session": "s1",
                "kind": "read",
                "key": "alpha",
                "observed": "w1",
                "context": [],
            },
            {
                "event_id": "w2",
                "step": 3,
                "region": "r2",
                "session": "s1",
                "kind": "write",
                "key": "beta",
                "observed": None,
                "context": ["w1"],
            },
            {
                "event_id": "r2",
                "step": 4,
                "region": "r2",
                "session": "s1",
                "kind": "read",
                "key": "beta",
                "observed": "w2",
                "context": ["w1"],
            },
        ],
    }


def test_incident_summary_is_exact(incident: dict[str, object]) -> None:
    summary = _summary(analyze_document(incident))
    assert summary == {
        "events": 16,
        "writes": 8,
        "reads": 8,
        "sessions": 5,
        "regions": 3,
        "trace_edges": 26,
        "version_edges": 5,
        "findings": 9,
        "violating_events": 5,
        "conformant_events": 11,
        "rule_counts": {
            "CAUSAL_CLOSURE": 1,
            "READ_YOUR_WRITES": 2,
            "MONOTONIC_READS": 2,
            "WRITES_FOLLOW_READS": 2,
            "MONOTONIC_WRITES": 2,
        },
    }


def test_incident_finding_order_and_events(incident: dict[str, object]) -> None:
    findings = _findings(analyze_document(incident))
    assert [(item["at_event"], item["rule"]) for item in findings] == [
        ("r04", "READ_YOUR_WRITES"),
        ("r04", "MONOTONIC_READS"),
        ("w04", "WRITES_FOLLOW_READS"),
        ("w04", "MONOTONIC_WRITES"),
        ("w06", "WRITES_FOLLOW_READS"),
        ("w06", "MONOTONIC_WRITES"),
        ("r06", "READ_YOUR_WRITES"),
        ("r06", "MONOTONIC_READS"),
        ("r07", "CAUSAL_CLOSURE"),
    ]


def test_all_five_rules_have_evidence(incident: dict[str, object]) -> None:
    findings = _findings(analyze_document(incident))
    assert {item["rule"] for item in findings} == set(RULES)


def test_finding_ids_are_unique_and_content_bound(incident: dict[str, object]) -> None:
    findings = _findings(analyze_document(incident))
    identifiers = [str(item["finding_id"]) for item in findings]
    assert len(identifiers) == len(set(identifiers))
    assert all(identifier.startswith("CF-") and len(identifier) == 15 for identifier in identifiers)


def test_relation_exposes_expected_version_ancestry(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    relation = cast(dict[str, object], receipt["relation"])
    ancestors = cast(dict[str, list[str]], relation["version_ancestors"])
    assert ancestors["w03"] == ["w01", "w02"]
    assert ancestors["w08"] == ["w07"]
    assert ancestors["w04"] == ["w01"]


def test_ledger_contains_events_then_findings(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    ledger = cast(list[dict[str, object]], receipt["ledger"])
    assert len(ledger) == 25
    assert [entry["kind"] for entry in ledger[:16]] == ["event"] * 16
    assert [entry["kind"] for entry in ledger[16:]] == ["finding"] * 9
    assert ledger[0]["previous_sha256"] == "0" * 64
    assert ledger[-1]["entry_sha256"] == receipt["ledger_root_sha256"]


def test_analysis_is_byte_deterministic(incident: dict[str, object]) -> None:
    assert analyze_document(incident) == analyze_document(incident)


def test_independent_verifier_matches_summary(incident: dict[str, object]) -> None:
    receipt = analyze_document(incident)
    assert verify_receipt(receipt) == receipt["summary"]


def test_clean_trace_has_no_findings() -> None:
    receipt = analyze_document(_clean_trace())
    summary = _summary(receipt)
    assert summary["findings"] == 0
    assert summary["conformant_events"] == 4
    assert _findings(receipt) == []
    assert verify_receipt(receipt) == summary
