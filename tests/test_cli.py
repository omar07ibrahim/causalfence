"""Installed-style CLI workflow tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import SCENARIO

from causalfence.cli import main


def test_complete_cli_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt = tmp_path / "receipt.json"
    report = tmp_path / "report.html"

    assert main(["analyze", str(SCENARIO), "--output", str(receipt)]) == 0
    analyze_output = capsys.readouterr().out
    assert "analyzed 16 events across 3 regions / 5 sessions" in analyze_output
    assert "findings 9 across 5 events; conformant 11" in analyze_output

    assert main(["verify", str(receipt)]) == 0
    assert "verified 16 events; 9 findings; 11 conformant events" in capsys.readouterr().out

    assert main(["inspect", str(receipt)]) == 0
    inspect_output = capsys.readouterr().out
    assert "READ_YOUR_WRITES" in inspect_output
    assert "CAUSAL_CLOSURE" in inspect_output
    assert inspect_output.count("CF-") == 9

    assert main(["report", str(receipt), "--output", str(report)]) == 0
    assert "wrote verified report" in capsys.readouterr().out
    html = report.read_text(encoding="utf-8")
    assert "Consistency failures" in html
    assert "Floyd–Warshall verifier passed" in html
    assert "synthetic fixture" in html
    assert str(tmp_path) not in html


def test_analyze_refuses_to_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("occupied", encoding="utf-8")
    assert main(["analyze", str(SCENARIO), "--output", str(output)]) == 2
    assert "refusing to replace" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "occupied"


def test_invalid_json_returns_bounded_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bad.json"
    source.write_text("{", encoding="utf-8")
    assert main(["analyze", str(source), "--output", str(tmp_path / "out.json")]) == 2
    assert "invalid JSON document" in capsys.readouterr().err


def test_verify_rejects_tampered_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "not-receipt.json"
    source.write_text('{"format":"wrong"}', encoding="utf-8")
    assert main(["verify", str(source)]) == 2
    assert "receipt format" in capsys.readouterr().err
