"""CausalFence command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from causalfence.canonical import (
    MAX_RECEIPT_BYTES,
    MAX_TRACE_BYTES,
    load_json,
    pretty_json,
)
from causalfence.engine import analyze_document
from causalfence.errors import CausalFenceError
from causalfence.report import render_report
from causalfence.verify import verify_receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="causalfence",
        description="Analyze and independently verify bounded distributed traces.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser("analyze", help="create a deterministic receipt")
    analyze.add_argument("trace", type=Path)
    analyze.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify", help="independently replay a receipt")
    verify.add_argument("receipt", type=Path)

    inspect = commands.add_parser("inspect", help="print bounded violation witnesses")
    inspect.add_argument("receipt", type=Path)

    report = commands.add_parser("report", help="render a self-contained HTML report")
    report.add_argument("receipt", type=Path)
    report.add_argument("--output", type=Path, required=True)
    return parser


def _write_new(path: Path, content: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise CausalFenceError(f"refusing to replace existing file: {path}") from exc
    except OSError as exc:
        raise CausalFenceError(f"cannot write {path}") from exc


def _load_receipt(path: Path) -> dict[str, object]:
    document = load_json(path, max_bytes=MAX_RECEIPT_BYTES)
    verify_receipt(document)
    return cast(dict[str, object], document)


def _analyze(trace_path: Path, output: Path) -> None:
    trace = load_json(trace_path, max_bytes=MAX_TRACE_BYTES)
    receipt = analyze_document(trace)
    _write_new(output, pretty_json(receipt))
    summary = cast(dict[str, object], receipt["summary"])
    print(
        f"analyzed {summary['events']} events across {summary['regions']} regions / "
        f"{summary['sessions']} sessions"
    )
    print(
        f"findings {summary['findings']} across {summary['violating_events']} events; "
        f"conformant {summary['conformant_events']}"
    )
    print(f"trace sha256   {receipt['trace_sha256']}")
    print(f"ledger root    {receipt['ledger_root_sha256']}")
    print(f"receipt sha256 {receipt['receipt_sha256']}")


def _verify(path: Path) -> None:
    receipt = _load_receipt(path)
    summary = cast(dict[str, object], receipt["summary"])
    print(
        f"verified {summary['events']} events; {summary['findings']} findings; "
        f"{summary['conformant_events']} conformant events"
    )
    print(f"ledger root    {receipt['ledger_root_sha256']}")
    print(f"receipt sha256 {receipt['receipt_sha256']}")


def _inspect(path: Path) -> None:
    receipt = _load_receipt(path)
    findings = cast(list[dict[str, object]], receipt["findings"])
    print("ID               RULE                  AT    WITNESS           MISSING")
    print("-" * 78)
    for finding in findings:
        witness = ",".join(cast(list[str], finding["witness_events"]))
        missing = ",".join(cast(list[str], finding["missing_versions"]))
        print(
            f"{finding['finding_id']!s:<16} {finding['rule']!s:<21} "
            f"{finding['at_event']!s:<5} {witness:<17} {missing}"
        )


def _report(path: Path, output: Path) -> None:
    receipt = _load_receipt(path)
    _write_new(output, render_report(receipt))
    print(f"wrote verified report {output}")
    print(f"receipt sha256 {receipt['receipt_sha256']}")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "analyze":
            _analyze(arguments.trace, arguments.output)
        elif arguments.command == "verify":
            _verify(arguments.receipt)
        elif arguments.command == "inspect":
            _inspect(arguments.receipt)
        else:
            _report(arguments.receipt, arguments.output)
    except (CausalFenceError, OSError, ValueError) as exc:
        print(f"causalfence: {exc}", file=sys.stderr)
        return 2
    return 0
