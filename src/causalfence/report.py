"""Render a source-free, self-contained incident report."""

from __future__ import annotations

import html
from typing import cast

from causalfence.verify import verify_receipt

_RULE_LABELS = {
    "CAUSAL_CLOSURE": "Causal closure",
    "READ_YOUR_WRITES": "Read your writes",
    "MONOTONIC_READS": "Monotonic reads",
    "WRITES_FOLLOW_READS": "Writes follow reads",
    "MONOTONIC_WRITES": "Monotonic writes",
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_report(receipt: dict[str, object]) -> str:
    """Verify first, then render only canonical receipt fields."""

    summary = verify_receipt(receipt)
    trace = cast(dict[str, object], receipt["trace"])
    events = cast(list[dict[str, object]], trace["events"])
    findings = cast(list[dict[str, object]], receipt["findings"])
    counts = cast(dict[str, int], summary["rule_counts"])
    maximum = max(1, max(counts.values()))

    metrics = (
        ("Events", summary["events"], "bounded trace"),
        ("Findings", summary["findings"], "five guarantees"),
        ("Affected", summary["violating_events"], "unique events"),
        ("Conformant", summary["conformant_events"], "no finding"),
    )
    metric_cards = "".join(
        f"""<article class="metric"><span>{_escape(label)}</span>
<strong>{_escape(value)}</strong><small>{_escape(note)}</small></article>"""
        for label, value, note in metrics
    )
    bars = "".join(
        f"""<div class="bar-row"><span>{_escape(_RULE_LABELS[rule])}</span>
<div class="track"><i style="width:{100 * count / maximum:.1f}%"></i></div>
<strong>{count}</strong></div>"""
        for rule, count in counts.items()
    )
    event_rows = "".join(
        f"""<tr class="event-row" data-event="{_escape(event["event_id"])}">
<td>{event["step"]}</td><td><code>{_escape(event["event_id"])}</code></td>
<td><span class="op {_escape(event["kind"])}">{_escape(event["kind"])}</span></td>
<td>{_escape(event["region"])}</td><td>{_escape(event["session"])}</td>
<td>{_escape(event["key"])}</td><td><code>{_escape(event["observed"] or "∅")}</code></td>
<td><code>{_escape(", ".join(cast(list[str], event["context"])) or "∅")}</code></td></tr>"""
        for event in events
    )
    finding_rows = "".join(
        f"""<tr><td><code>{_escape(finding["finding_id"])}</code></td>
<td><span class="rule">{_escape(_RULE_LABELS[str(finding["rule"])])}</span></td>
<td><code>{_escape(finding["at_event"])}</code></td>
<td><code>{_escape(" → ".join(cast(list[str], finding["witness_events"])))}</code></td>
<td>{_escape(finding["explanation"])}</td></tr>"""
        for finding in findings
    )
    timeline = "".join(
        f"""<div class="tick {"bad" if any(item['at_event"] == event["event_id"] for item in findings) else "ok"}">
<span>{event["step"]}</span><b>{_escape(event["event_id"])}</b>
<small>{_escape(event["region"])} · {_escape(event["kind"])}</small></div>"""
        for event in events
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CausalFence · {_escape(trace["trace_id"])}</title>
<style>
:root{{--ink:#14253a;--muted:#637287;--paper:#f5f7fb;--card:#fff;--navy:#0b1f35;
--cyan:#54d6ce;--blue:#4d7df3;--red:#ef6674;--amber:#f3b64b;--line:#dfe6ef}}
*{{box-sizing:border-box}}html{{background:var(--paper);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}
body{{margin:0}}header{{background:radial-gradient(circle at 85% 10%,#174e67 0,transparent 34%),linear-gradient(135deg,#071522,#102c47);color:#fff;padding:54px max(5vw,28px) 48px}}
.eyebrow{{color:var(--cyan);font-size:12px;font-weight:800;letter-spacing:.18em;text-transform:uppercase}}
h1{{font-size:clamp(38px,6vw,72px);line-height:1;margin:14px 0 18px;letter-spacing:-.04em}}
.lead{{max-width:820px;color:#c7d6e6;font-size:18px}}.badges{{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}}
.badge{{border:1px solid #ffffff2d;border-radius:999px;padding:7px 12px;background:#ffffff0d;color:#d8e8f6;font-size:12px}}
main{{max-width:1240px;margin:auto;padding:32px 28px 70px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:-66px}}
.metric{{background:var(--card);border:1px solid var(--line);box-shadow:0 18px 44px #233d5a12;border-radius:18px;padding:22px}}
.metric span,.metric small{{display:block;color:var(--muted)}}.metric strong{{display:block;font-size:36px;line-height:1.1;margin:8px 0;color:var(--navy)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:26px;margin-top:22px;overflow:hidden}}
h2{{font-size:24px;margin:0 0 6px;letter-spacing:-.02em}}.sub{{color:var(--muted);margin:0 0 22px}}
.overview{{display:grid;grid-template-columns:1.15fr .85fr;gap:22px}}.overview section{{margin:0}}
.bar-row{{display:grid;grid-template-columns:145px 1fr 30px;align-items:center;gap:12px;margin:14px 0}}
.track{{height:12px;background:#edf1f6;border-radius:99px;overflow:hidden}}.track i{{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,var(--blue),var(--cyan))}}
.timeline{{display:grid;grid-template-columns:repeat(8,1fr);gap:9px}}.tick{{border:1px solid var(--line);border-top:4px solid var(--cyan);border-radius:12px;padding:10px;min-width:0}}
.tick.bad{{border-top-color:var(--red);background:#fff8f8}}.tick span,.tick small{{display:block;color:var(--muted);font-size:11px}}.tick b{{display:block;font:700 14px ui-monospace,monospace;margin:3px 0}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px}}table{{width:100%;border-collapse:collapse;min-width:900px}}
th,td{{padding:12px 13px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);background:#f8fafc}}
tr:last-child td{{border-bottom:0}}code{{font:12px ui-monospace,SFMono-Regular,Consolas,monospace}}.op,.rule{{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:800}}
.op.write{{background:#e9f0ff;color:#315ec4}}.op.read{{background:#e8faf5;color:#147561}}.rule{{background:#fff0f1;color:#a83447}}
.digest{{display:grid;grid-template-columns:170px 1fr;gap:10px 18px}}.digest code{{overflow-wrap:anywhere;color:#344d68}}
footer{{color:var(--muted);font-size:12px;margin-top:24px;padding:0 6px}}
@media(max-width:850px){{header{{padding-bottom:88px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.overview{{grid-template-columns:1fr}}.timeline{{grid-template-columns:repeat(4,1fr)}}}}
@media(max-width:480px){{main{{padding:20px 14px 50px}}header{{padding:38px 18px 82px}}.metrics{{gap:9px}}.metric{{padding:15px}}.metric strong{{font-size:28px}}section{{padding:18px}}.timeline{{grid-template-columns:repeat(2,1fr)}}.bar-row{{grid-template-columns:120px 1fr 24px}}.digest{{grid-template-columns:1fr;gap:3px}}}}
</style></head><body>
<header><div class="eyebrow">CausalFence / independently replayed receipt</div>
<h1>Consistency failures,<br>made answerable.</h1>
<p class="lead">A deterministic analysis of declared version dependencies, causal closure,
and four client-session guarantees. Wall clocks are display metadata—not proof.</p>
<div class="badges"><span class="badge">synthetic fixture</span><span class="badge">{summary["regions"]} regions</span>
<span class="badge">{summary["sessions"]} sessions</span><span class="badge">Floyd–Warshall verifier passed</span></div></header>
<main><div class="metrics">{metric_cards}</div>
<div class="overview"><section><h2>Rule outcomes</h2><p class="sub">Finding count, not a production error rate.</p>{bars}</section>
<section><h2>Evidence boundary</h2><p class="sub">The receipt proves deterministic replay of this bounded synthetic trace.
It does not prove a database implementation, SLA, performance, or production correctness.</p>
<p><strong>{summary["trace_edges"]}</strong> trace edges · <strong>{summary["version_edges"]}</strong> declared version edges</p></section></div>
<section id="timeline"><h2>Incident timeline</h2><p class="sub">Red ticks have at least one bounded witness.</p>
<div class="timeline">{timeline}</div></section>
<section id="findings"><h2>Minimal local witnesses</h2><p class="sub">Each finding names the operation pair and missing version needed for independent replay.</p>
<div class="table-wrap"><table><thead><tr><th>ID</th><th>Guarantee</th><th>At</th><th>Witness</th><th>Explanation</th></tr></thead>
<tbody>{finding_rows}</tbody></table></div></section>
<section id="trace"><h2>Normalized trace</h2><p class="sub">Strict input order, declared context, and observed versions.</p>
<div class="table-wrap"><table><thead><tr><th>Step</th><th>Event</th><th>Op</th><th>Region</th><th>Session</th><th>Key</th><th>Observed</th><th>Context</th></tr></thead>
<tbody>{event_rows}</tbody></table></div></section>
<section id="receipt"><h2>Receipt integrity</h2><p class="sub">Canonical SHA-256 binds the trace, analysis fields, and append-only ledger.</p>
<div class="digest"><strong>Trace SHA-256</strong><code>{_escape(receipt["trace_sha256"])}</code>
<strong>Ledger root</strong><code>{_escape(receipt["ledger_root_sha256"])}</code>
<strong>Receipt SHA-256</strong><code>{_escape(receipt["receipt_sha256"])}</code></div></section>
<footer>Generated deterministically by CausalFence v0.1.0 · no network, database, or model required.</footer>
</main></body></html>
"""
