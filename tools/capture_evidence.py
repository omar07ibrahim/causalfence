"""Generate and verify source-bound CausalFence portfolio evidence."""

# ruff: noqa: E501 -- deterministic SVG, CSS, and evidence contracts stay reviewable

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import shutil
import struct
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, cast

FORMAT = "causalfence.evidence.v1"
EVIDENCE_DIRECTORY = Path("docs/evidence")
MANIFEST_NAME = "causalfence-evidence.json"
CONTAINER_IMAGE = (
    "mcr.microsoft.com/playwright/python@"
    "sha256:51d31fdfacb0cff99a1a724152e34ae408d2bd4e7da310ff157450f49261cc59"
)
EXPECTED_FILES = {
    "architecture.svg",
    "causalfence-cli.png",
    "causalfence-cli.txt",
    "causalfence-demo.gif",
    "causalfence-receipt.json",
    "causalfence-report-full.png",
    "causalfence-report-mobile.png",
    "causalfence-report.html",
    "causalfence-report.png",
    "consistency-model.svg",
    "finding-distribution.svg",
    "incident-timeline.svg",
}
MEDIA_TYPES = {
    ".gif": "image/gif",
    ".html": "text/html",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
}
FORBIDDEN_TEXT = (
    "/home/",
    "/Users/",
    "github_pat_",
    "gho_",
    "ghp_",
    "sk-proj-",
    "BEGIN PRIVATE KEY",
    "Authorization: Bearer",
)
RULE_LABELS = {
    "CAUSAL_CLOSURE": "Causal closure",
    "READ_YOUR_WRITES": "Read your writes",
    "MONOTONIC_READS": "Monotonic reads",
    "WRITES_FOLLOW_READS": "Writes follow reads",
    "MONOTONIC_WRITES": "Monotonic writes",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--root", type=Path, required=True)
    prepare_parser.add_argument("--receipt", type=Path, required=True)
    prepare_parser.add_argument("--report", type=Path, required=True)
    prepare_parser.add_argument("--cli", type=Path, required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)

    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--output-root", type=Path, required=True)
    capture_parser.add_argument("--container-image", required=True)

    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("--root", type=Path, required=True)
    finalize_parser.add_argument("--output-root", type=Path, required=True)
    finalize_parser.add_argument("--source-revision", required=True)
    finalize_parser.add_argument("--source-tree", required=True)
    finalize_parser.add_argument("--container-image", required=True)
    finalize_parser.add_argument("--browser", required=True)
    finalize_parser.add_argument("--playwright", required=True)
    finalize_parser.add_argument("--pillow", required=True)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--output-root", type=Path, required=True)
    verify_parser.add_argument("--source-revision", required=True)
    verify_parser.add_argument("--source-tree", required=True)
    verify_parser.add_argument("--container-image", required=True)

    visual_parser = commands.add_parser("verify-visuals")
    visual_parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "prepare":
        prepare(
            arguments.root,
            arguments.receipt,
            arguments.report,
            arguments.cli,
            arguments.output_root,
        )
    elif arguments.command == "capture":
        capture(arguments.output_root, arguments.container_image)
    elif arguments.command == "finalize":
        finalize(
            arguments.root,
            arguments.output_root,
            arguments.source_revision,
            arguments.source_tree,
            arguments.container_image,
            arguments.browser,
            arguments.playwright,
            arguments.pillow,
        )
    elif arguments.command == "verify":
        verify(
            arguments.root,
            arguments.output_root,
            arguments.source_revision,
            arguments.source_tree,
            arguments.container_image,
        )
    else:
        verify_visuals(arguments.output_root)
    return 0


def prepare(
    root: Path,
    receipt_path: Path,
    report_path: Path,
    cli_path: Path,
    output_root: Path,
) -> None:
    root = root.resolve()
    if output_root.exists():
        raise ValueError("evidence output root already exists")
    evidence = output_root / EVIDENCE_DIRECTORY
    evidence.mkdir(parents=True)

    from causalfence.canonical import MAX_RECEIPT_BYTES, load_json, pretty_json
    from causalfence.report import render_report
    from causalfence.verify import verify_receipt

    document = load_json(receipt_path, max_bytes=MAX_RECEIPT_BYTES)
    if not isinstance(document, dict):
        raise ValueError("evidence receipt must be an object")
    receipt = cast(dict[str, object], document)
    summary = verify_receipt(receipt)
    report = report_path.read_text(encoding="utf-8")
    if report != render_report(receipt):
        raise ValueError("CLI report differs from verified library rendering")
    cli = cli_path.read_text(encoding="utf-8")
    _reject_sensitive_text(cli)
    if not cli.startswith("$ causalfence analyze trace.json --output receipt.json"):
        raise ValueError("CLI transcript does not begin with the executed analyze command")
    if str(receipt["receipt_sha256"]) not in cli:
        raise ValueError("CLI transcript does not expose the receipt digest")
    if f"verified {summary['events']} events; {summary['findings']} findings" not in cli:
        raise ValueError("CLI transcript does not include independent replay")

    _write_text(evidence / "causalfence-receipt.json", pretty_json(receipt))
    _write_text(evidence / "causalfence-report.html", report)
    _write_text(evidence / "causalfence-cli.txt", cli)
    _write_text(evidence / "architecture.svg", _architecture_svg(receipt))
    _write_text(evidence / "consistency-model.svg", _consistency_svg(receipt))
    _write_text(evidence / "incident-timeline.svg", _timeline_svg(receipt))
    _write_text(evidence / "finding-distribution.svg", _distribution_svg(receipt))
    _write_text(output_root / "terminal.html", _terminal_html(cli))


def capture(output_root: Path, container_image: str) -> None:
    if container_image != CONTAINER_IMAGE:
        raise ValueError("unpinned evidence container")
    from PIL import Image
    from playwright.sync_api import sync_playwright

    evidence = output_root / EVIDENCE_DIRECTORY
    report_uri = (evidence / "causalfence-report.html").resolve().as_uri()
    terminal_uri = (output_root / "terminal.html").resolve().as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        desktop = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = desktop.new_page()
        page.goto(report_uri, wait_until="load")
        page.screenshot(path=evidence / "causalfence-report.png")
        page.screenshot(path=evidence / "causalfence-report-full.png", full_page=True)
        desktop.close()

        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = mobile.new_page()
        page.goto(report_uri, wait_until="load")
        page.screenshot(path=evidence / "causalfence-report-mobile.png")
        mobile.close()

        terminal = browser.new_context(
            viewport={"width": 1180, "height": 650},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = terminal.new_page()
        page.goto(terminal_uri, wait_until="load")
        page.screenshot(path=evidence / "causalfence-cli.png")
        terminal.close()

        demo = browser.new_context(
            viewport={"width": 1120, "height": 820},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = demo.new_page()
        page.goto(report_uri, wait_until="load")
        frames = []
        for selector in ("header", "#findings", "#receipt"):
            page.locator(selector).scroll_into_view_if_needed()
            image = Image.open(BytesIO(page.screenshot())).convert("RGB")
            frames.append(
                image.quantize(
                    colors=128,
                    method=Image.Quantize.MEDIANCUT,
                    dither=Image.Dither.NONE,
                )
            )
        frames[0].save(
            evidence / "causalfence-demo.gif",
            save_all=True,
            append_images=frames[1:],
            duration=(1400, 1700, 1700),
            loop=0,
            disposal=2,
            optimize=False,
        )
        demo.close()
        browser.close()


def finalize(
    root: Path,
    output_root: Path,
    source_revision: str,
    source_tree: str,
    container_image: str,
    browser: str,
    playwright: str,
    pillow: str,
) -> None:
    _validate_oid(source_revision, "source revision")
    _validate_oid(source_tree, "source tree")
    if container_image != CONTAINER_IMAGE:
        raise ValueError("evidence container mismatch")
    evidence = output_root / EVIDENCE_DIRECTORY
    receipt = json.loads((evidence / "causalfence-receipt.json").read_text(encoding="utf-8"))
    from causalfence.verify import verify_receipt

    summary = verify_receipt(receipt)
    manifest = {
        "format": FORMAT,
        "source_revision": source_revision,
        "source_tree": source_tree,
        "generation": {
            "container_image": container_image,
            "browser": browser,
            "playwright": playwright,
            "pillow": pillow,
            "python": platform.python_version(),
            "network": "disabled during browser capture",
            "filesystem": "read-only source mount",
        },
        "trace_sha256": receipt["trace_sha256"],
        "ledger_root_sha256": receipt["ledger_root_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
        "result": _result(summary),
        "sources": [_file_record(path, root) for path in _source_paths(root)],
        "files": [
            _evidence_record(path, output_root)
            for path in sorted(evidence.iterdir())
            if path.name != MANIFEST_NAME
        ],
    }
    _write_text(
        evidence / MANIFEST_NAME,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def verify(
    root: Path,
    output_root: Path,
    source_revision: str,
    source_tree: str,
    container_image: str,
) -> None:
    _validate_oid(source_revision, "source revision")
    _validate_oid(source_tree, "source tree")
    evidence = output_root / EVIDENCE_DIRECTORY
    actual = {path.name for path in evidence.iterdir() if path.is_file()}
    expected = EXPECTED_FILES | {MANIFEST_NAME}
    if actual != expected:
        raise ValueError(f"evidence file set differs: {sorted(actual ^ expected)}")
    manifest = json.loads((evidence / MANIFEST_NAME).read_text(encoding="utf-8"))
    if manifest["format"] != FORMAT:
        raise ValueError("evidence format mismatch")
    if manifest["source_revision"] != source_revision or manifest["source_tree"] != source_tree:
        raise ValueError("evidence source binding mismatch")
    if manifest["generation"]["container_image"] != container_image:
        raise ValueError("evidence container mismatch")
    if manifest["generation"]["python"] != "3.14.6":
        raise ValueError("evidence Python runtime mismatch")
    if manifest["sources"] != [_file_record(path, root) for path in _source_paths(root)]:
        raise ValueError("evidence source hashes differ")
    expected_files = [
        _evidence_record(path, output_root)
        for path in sorted(evidence.iterdir())
        if path.name != MANIFEST_NAME
    ]
    if manifest["files"] != expected_files:
        raise ValueError("evidence file hashes or dimensions differ")

    from causalfence.canonical import MAX_RECEIPT_BYTES, load_json
    from causalfence.report import render_report
    from causalfence.verify import verify_receipt

    document = load_json(
        evidence / "causalfence-receipt.json",
        max_bytes=MAX_RECEIPT_BYTES,
    )
    if not isinstance(document, dict):
        raise ValueError("evidence receipt must be an object")
    receipt = cast(dict[str, object], document)
    summary = verify_receipt(receipt)
    if (evidence / "causalfence-report.html").read_text(encoding="utf-8") != render_report(receipt):
        raise ValueError("checked-in report does not replay")
    if manifest["result"] != _result(summary):
        raise ValueError("manifest result does not match independent replay")
    for key in ("trace_sha256", "ledger_root_sha256", "receipt_sha256"):
        if manifest[key] != receipt[key]:
            raise ValueError(f"manifest {key} mismatch")

    for path in evidence.iterdir():
        if path.suffix in {".html", ".json", ".svg", ".txt"}:
            _reject_sensitive_text(path.read_text(encoding="utf-8"))
        if path.suffix == ".svg":
            _verify_svg(path)


def verify_visuals(output_root: Path) -> None:
    from PIL import Image, ImageSequence

    evidence = output_root / EVIDENCE_DIRECTORY
    expected_png = {
        "causalfence-report.png": (1440, 1000),
        "causalfence-report-mobile.png": (390, 844),
        "causalfence-cli.png": (1180, 650),
    }
    for name, dimensions in expected_png.items():
        with Image.open(evidence / name) as image:
            if image.format != "PNG" or image.size != dimensions:
                raise ValueError(
                    f"unexpected raster contract for {name}: {image.format} {image.size}"
                )
            _reject_blank_image(image, name)
    with Image.open(evidence / "causalfence-report-full.png") as image:
        if image.format != "PNG" or image.width != 1440 or image.height < 1_800:
            raise ValueError(f"unexpected full-page raster: {image.format} {image.size}")
        _reject_blank_image(image, "causalfence-report-full.png")
    with Image.open(evidence / "causalfence-demo.gif") as image:
        frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(image)]
        if image.format != "GIF" or image.size != (1120, 820) or len(frames) != 3:
            raise ValueError(
                f"unexpected GIF contract: {image.format} {image.size} {len(frames)}"
            )
        digests = set()
        for index, frame in enumerate(frames):
            _reject_blank_image(frame, f"causalfence-demo.gif frame {index}")
            digests.add(hashlib.sha256(frame.tobytes()).hexdigest())
        if len(digests) != 3:
            raise ValueError("GIF frames are not visually distinct")


def _reject_blank_image(image: Any, label: str) -> None:
    converted = image.convert("RGB")
    extrema = converted.getextrema()
    if all(low == high for low, high in extrema):
        raise ValueError(f"blank evidence image: {label}")
    colors = converted.resize((160, 100)).getcolors(maxcolors=20_000)
    if colors is None or len(colors) < 12:
        raise ValueError(f"insufficient visual detail: {label}")


def _result(summary: dict[str, object]) -> dict[str, object]:
    keys = (
        "events",
        "writes",
        "reads",
        "sessions",
        "regions",
        "trace_edges",
        "version_edges",
        "findings",
        "violating_events",
        "conformant_events",
        "rule_counts",
    )
    return {key: summary[key] for key in keys}


def _architecture_svg(receipt: dict[str, object]) -> str:
    summary = cast(dict[str, object], receipt["summary"])
    labels = (
        ("01", "TRACE CONTRACT", "bounded, typed operations"),
        ("02", "VERSION DAG", f"{summary['version_edges']} declared dependencies"),
        ("03", "ANALYZER", "memoized predecessor walks"),
        ("04", "RECEIPT", f"{summary['findings']} content-bound findings"),
        ("05", "VERIFIER", "independent matrix closure"),
    )
    boxes = "".join(
        f"""<g transform="translate({45 + index * 230} 175)">
<rect width="195" height="190" rx="24" fill="#102940" stroke="{'#ff6d7d' if index == 0 else '#51d2c8'}" stroke-width="2"/>
<text x="20" y="35" fill="#78e7df" font-size="13" font-weight="800">{number}</text>
<text x="20" y="78" fill="#fff" font-size="15" font-weight="800">{title}</text>
<text x="20" y="116" fill="#bfd0df" font-size="12">{detail}</text>
</g>"""
        for index, (number, title, detail) in enumerate(labels)
    )
    arrows = "".join(
        f'<path d="M {240 + index * 230} 270 H {275 + index * 230}" stroke="#78e7df" stroke-width="3" marker-end="url(#a)"/>'
        for index in range(4)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 530">
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#06121f"/><stop offset="1" stop-color="#124357"/></linearGradient><marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="#78e7df"/></marker></defs>
<rect width="1200" height="530" rx="28" fill="url(#bg)"/>
<text x="45" y="62" fill="#78e7df" font-size="14" font-weight="800" letter-spacing="2">CAUSALFENCE / DUAL-ALGORITHM WORKFLOW</text>
<text x="45" y="108" fill="#fff" font-size="33" font-weight="800">A trace is evidence only after independent replay</text>
{boxes}{arrows}
<text x="45" y="440" fill="#aec2d3" font-size="13">Trace {str(receipt['trace_sha256'])[:18]}… · Ledger {str(receipt['ledger_root_sha256'])[:18]}…</text>
<text x="45" y="474" fill="#e0ebf3" font-size="14">Analyzer and verifier share the trace contract—not the graph implementation.</text>
</svg>
"""


def _consistency_svg(receipt: dict[str, object]) -> str:
    relation = cast(dict[str, object], receipt["relation"])
    edges = cast(list[dict[str, str]], relation["version_edges"])
    findings = cast(list[dict[str, object]], receipt["findings"])
    positions = {
        "w01": (95, 250),
        "w02": (300, 150),
        "w03": (510, 235),
        "w04": (735, 125),
        "w05": (110, 450),
        "w06": (350, 450),
        "w07": (700, 430),
        "w08": (945, 430),
    }
    paths = "".join(
        f'<path d="M {positions[edge["source"]][0] + 52} {positions[edge["source"]][1]} L {positions[edge["target"]][0] - 52} {positions[edge["target"]][1]}" stroke="#38bfae" stroke-width="4" marker-end="url(#ok)"/>'
        for edge in edges
    )
    missing_edges = []
    for finding in findings:
        if finding["rule"] == "MONOTONIC_WRITES":
            missing = cast(list[str], finding["missing_versions"])[0]
            missing_edges.append((missing, str(finding["at_event"])))
    dashed = "".join(
        f'<path d="M {positions[source][0] + 50} {positions[source][1]} L {positions[target][0] - 50} {positions[target][1]}" stroke="#e9566d" stroke-width="3" stroke-dasharray="9 8" marker-end="url(#bad)"/>'
        for source, target in missing_edges
    )
    nodes = "".join(
        f"""<g><circle cx="{x}" cy="{y}" r="46" fill="#102d4b" stroke="#78e7df" stroke-width="2"/>
<text x="{x}" y="{y + 6}" text-anchor="middle" fill="#fff" font-size="17" font-weight="800">{version}</text></g>"""
        for version, (x, y) in positions.items()
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 610">
<defs><marker id="ok" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="#38bfae"/></marker><marker id="bad" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="#e9566d"/></marker></defs>
<rect width="1200" height="610" rx="28" fill="#f5f8fb"/>
<text x="50" y="62" fill="#102d4b" font-size="32" font-weight="800">Declared version DAG and missing session carries</text>
<text x="50" y="94" fill="#63788d" font-size="14">Solid teal: declared dependency · dashed red: expected monotonic-write edge absent from the trace.</text>
{paths}{dashed}{nodes}
<rect x="835" y="110" width="310" height="170" rx="20" fill="#fff" stroke="#dae3ec"/>
<text x="865" y="150" fill="#102d4b" font-size="16" font-weight="800">Independent result</text>
<text x="865" y="190" fill="#e9566d" font-size="42" font-weight="800">{len(findings)}</text>
<text x="925" y="187" fill="#63788d" font-size="14">findings</text>
<text x="865" y="230" fill="#36536e" font-size="13">Receipt {str(receipt['receipt_sha256'])[:18]}…</text>
</svg>
"""


def _timeline_svg(receipt: dict[str, object]) -> str:
    trace = cast(dict[str, object], receipt["trace"])
    events = cast(list[dict[str, object]], trace["events"])
    findings = cast(list[dict[str, object]], receipt["findings"])
    affected = {str(item["at_event"]) for item in findings}
    cards = "".join(
        f"""<g transform="translate({50 + (index % 8) * 140} {145 + (index // 8) * 190})">
<rect width="118" height="132" rx="17" fill="{'#fff0f2' if event['event_id'] in affected else '#eaf8f5'}" stroke="{'#e9566d' if event['event_id'] in affected else '#2baa91'}" stroke-width="2"/>
<text x="14" y="27" fill="#718296" font-size="11">STEP {event['step']}</text>
<text x="14" y="59" fill="#102d4b" font-size="18" font-weight="800">{event['event_id']}</text>
<text x="14" y="85" fill="#3f5a72" font-size="12">{event['kind']} · {event['key']}</text>
<text x="14" y="108" fill="#718296" font-size="10">{event['region']}</text>
</g>"""
        for index, event in enumerate(events)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 570">
<rect width="1200" height="570" rx="28" fill="#fff"/>
<text x="50" y="60" fill="#102d4b" font-size="32" font-weight="800">Synthetic multi-region incident timeline</text>
<text x="50" y="95" fill="#63788d" font-size="14">16 ordered client observations · red marks one or more independently replayed witnesses.</text>
{cards}
<text x="50" y="525" fill="#63788d" font-size="13">List order is evidence order. Wall clocks are intentionally absent from the proof relation.</text>
</svg>
"""


def _distribution_svg(receipt: dict[str, object]) -> str:
    summary = cast(dict[str, object], receipt["summary"])
    counts = cast(dict[str, int], summary["rule_counts"])
    maximum = max(counts.values())
    bars = "".join(
        f"""<text x="65" y="{165 + index * 70}" fill="#29445f" font-size="14">{RULE_LABELS[rule]}</text>
<rect x="260" y="{142 + index * 70}" width="650" height="32" rx="16" fill="#e8eef4"/>
<rect x="260" y="{142 + index * 70}" width="{650 * count / maximum:.1f}" height="32" rx="16" fill="{'#e9566d' if count else '#43b9a8'}"/>
<text x="940" y="{166 + index * 70}" fill="#102d4b" font-size="18" font-weight="800">{count}</text>"""
        for index, (rule, count) in enumerate(counts.items())
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 570">
<rect width="1200" height="570" rx="28" fill="#f6f8fb"/>
<text x="50" y="58" fill="#102d4b" font-size="32" font-weight="800">Finding distribution for the checked-in fixture</text>
<text x="50" y="92" fill="#63788d" font-size="14">Counts are deterministic findings—not an error rate, benchmark, or production measurement.</text>
{bars}
<rect x="1010" y="135" width="140" height="270" rx="22" fill="#102d4b"/>
<text x="1080" y="180" text-anchor="middle" fill="#78e7df" font-size="12" font-weight="800">EVENTS</text>
<text x="1080" y="245" text-anchor="middle" fill="#fff" font-size="42" font-weight="800">{summary['conformant_events']}</text>
<text x="1080" y="270" text-anchor="middle" fill="#bfd0df" font-size="11">conformant</text>
<text x="1080" y="340" text-anchor="middle" fill="#ff98a5" font-size="42" font-weight="800">{summary['violating_events']}</text>
<text x="1080" y="365" text-anchor="middle" fill="#bfd0df" font-size="11">affected</text>
<text x="50" y="520" fill="#63788d" font-size="13">Synthetic trace · {summary['regions']} regions · {summary['sessions']} sessions · independent matrix replay passed.</text>
</svg>
"""


def _terminal_html(cli: str) -> str:
    escaped = html.escape(cli)
    return f"""<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;background:#071019;color:#dce8f2}}body{{padding:34px;font:15px/1.48 ui-monospace,SFMono-Regular,Consolas,monospace}}
.window{{border:1px solid #294158;border-radius:18px;overflow:hidden;box-shadow:0 24px 70px #0008}}
.bar{{height:46px;background:#101e2c;border-bottom:1px solid #294158;display:flex;align-items:center;padding:0 18px;gap:9px}}
.dot{{width:12px;height:12px;border-radius:50%}}.r{{background:#ff6b6b}}.y{{background:#f4d35e}}.g{{background:#52d6a6}}
pre{{margin:0;padding:24px 28px;white-space:pre-wrap;overflow-wrap:anywhere}}
</style><div class="window"><div class="bar"><i class="dot r"></i><i class="dot y"></i><i class="dot g"></i></div><pre>{escaped}</pre></div>"""


def _source_paths(root: Path) -> list[Path]:
    paths = [
        root / ".github/workflows/evidence.yml",
        root / "pyproject.toml",
        root / "requirements/evidence-browser-image.lock.json",
        root / "requirements/evidence-browser.txt",
        root / "requirements/quality.in",
        root / "requirements/quality.txt",
        root / "scenarios/multi-region-incident.json",
        root / "tools/capture_evidence.py",
    ]
    paths.extend(sorted((root / "src/causalfence").glob("*.py")))
    paths.append(root / "src/causalfence/py.typed")
    return paths


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _evidence_record(path: Path, root: Path) -> dict[str, Any]:
    record = _file_record(path, root)
    record["media_type"] = MEDIA_TYPES[path.suffix]
    if path.suffix == ".png":
        record["dimensions"] = list(_png_dimensions(path))
    elif path.suffix == ".gif":
        record["dimensions"] = list(_gif_dimensions(path))
        record["frames"] = 3
    return record


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"invalid PNG: {path}")
    return struct.unpack(">II", data[16:24])


def _gif_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:10]
    if len(data) != 10 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError(f"invalid GIF: {path}")
    return struct.unpack("<HH", data[6:10])


def _validate_oid(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"invalid {label}")


def _verify_svg(path: Path) -> None:
    root = ET.parse(path).getroot()
    if not root.tag.endswith("svg") or root.get("viewBox") is None:
        raise ValueError(f"invalid SVG structure: {path}")
    if len(list(root.iter())) < 8:
        raise ValueError(f"SVG lacks detail: {path}")


def _reject_sensitive_text(value: str) -> None:
    for marker in FORBIDDEN_TEXT:
        if marker in value:
            raise ValueError(f"evidence contains forbidden marker: {marker}")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
