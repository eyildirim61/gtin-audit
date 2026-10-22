"""Write audit results as CSV and as a self-contained HTML report."""

from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

from . import __version__
from .checks import RULES, SEVERITY_ORDER, Issue, Record, summarize

CSV_COLUMNS = ("row", "severity", "code", "field", "value", "ref", "name", "message")


def write_csv(issues: Sequence[Issue], path) -> Path:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:  # BOM so Excel shows Turkish chars
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for i in issues:
            writer.writerow([getattr(i, c) for c in CSV_COLUMNS])
    return path


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def render_html(
    issues: Sequence[Issue],
    records: Sequence[Record],
    source_name: str,
    columns: Dict[str, str],
) -> str:
    summary = summarize(issues)
    sev = summary["by_severity"]
    products = len({r.group for r in records})
    affected = len({i.row for i in issues if i.severity == "error"})
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    rule_rows = []
    for code, (severity, desc) in sorted(RULES.items(), key=lambda kv: (SEVERITY_ORDER[kv[1][0]], kv[0])):
        count = summary["by_code"].get(code, 0)
        rule_rows.append(
            f'<tr class="{"" if count else "zero"}"><td><span class="pill {severity}">{severity}</span></td>'
            f"<td><code>{code}</code></td><td>{_e(desc)}</td><td class=num>{count}</td></tr>"
        )

    issue_rows = []
    for i in issues:
        haystack = " ".join([i.code, i.ref, i.name, i.value, i.message]).lower()
        issue_rows.append(
            f'<tr data-sev="{i.severity}" data-text="{_e(haystack)}">'
            f"<td class=num>{i.row}</td>"
            f'<td><span class="pill {i.severity}">{i.severity}</span></td>'
            f"<td><code>{i.code}</code></td>"
            f"<td class=nowrap>{_e(i.ref)}</td><td>{_e(i.name)}</td>"
            f"<td>{_e(i.field)}</td><td><code>{_e(i.value)}</code></td>"
            f"<td>{_e(i.message)}</td></tr>"
        )

    mapping_text = ", ".join(f"{_e(f)} ← <b>{_e(h)}</b>" for f, h in columns.items())
    empty_state = (
        '<p class="empty">No issues found. Every barcode passed all checks.</p>' if not issues else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GTIN Audit Report</title>
<style>
:root {{
  --bg: #f7f7f5; --panel: #ffffff; --ink: #1d1d1b; --muted: #6b6b66; --line: #e4e3df;
  --error: #b42318; --error-bg: #fdecea; --warning: #9a6700; --warning-bg: #fff4d6;
  --info: #175cd3; --info-bg: #e8f0fe;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #161615; --panel: #1f1f1d; --ink: #ecebe7; --muted: #a09f99; --line: #33332f;
    --error: #ff8a80; --error-bg: #3a1714; --warning: #f5c451; --warning-bg: #352a10;
    --info: #8ab4f8; --info-bg: #13243f;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 1200px; margin: 0 auto; padding: 32px 16px 64px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
h2 {{ font-size: 15px; margin: 32px 0 12px; }}
.meta {{ color: var(--muted); font-size: 13px; }}
.cards {{ display: flex; flex-wrap: wrap; margin: 20px -6px 0; }}
.card {{ flex: 1 1 150px; margin: 6px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }}
td.nowrap {{ white-space: nowrap; }}
.card .n {{ font-size: 26px; font-weight: 650; font-variant-numeric: tabular-nums; }}
.card .l {{ color: var(--muted); font-size: 12px; }}
.card.error .n {{ color: var(--error); }} .card.warning .n {{ color: var(--warning); }} .card.info .n {{ color: var(--info); }}
.wrap {{ overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ font-size: 12px; color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--panel); }}
tr:last-child td {{ border-bottom: 0; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tr.zero {{ opacity: .45; }}
code {{ font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; }}
.pill {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }}
.pill.error {{ color: var(--error); background: var(--error-bg); }}
.pill.warning {{ color: var(--warning); background: var(--warning-bg); }}
.pill.info {{ color: var(--info); background: var(--info-bg); }}
.toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; align-items: center; }}
.toolbar button {{ border: 1px solid var(--line); background: var(--panel); color: var(--ink);
  border-radius: 999px; padding: 4px 12px; cursor: pointer; font: inherit; font-size: 13px; }}
.toolbar button.on {{ border-color: var(--ink); font-weight: 600; }}
.toolbar input {{ flex: 1; min-width: 180px; border: 1px solid var(--line); background: var(--panel);
  color: var(--ink); border-radius: 8px; padding: 6px 10px; font: inherit; }}
.empty {{ padding: 24px; text-align: center; color: var(--muted); }}
footer {{ margin-top: 32px; color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<main>
  <h1>GTIN Audit Report</h1>
  <div class="meta">{_e(source_name)} · {generated} · columns: {mapping_text}</div>

  <div class="cards">
    <div class="card"><div class="n">{len(records)}</div><div class="l">rows checked</div></div>
    <div class="card"><div class="n">{products}</div><div class="l">products</div></div>
    <div class="card error"><div class="n">{sev['error']}</div><div class="l">errors ({affected} rows)</div></div>
    <div class="card warning"><div class="n">{sev['warning']}</div><div class="l">warnings</div></div>
    <div class="card info"><div class="n">{sev['info']}</div><div class="l">info</div></div>
  </div>

  <h2>Rules</h2>
  <div class="wrap"><table>
    <thead><tr><th>Severity</th><th>Code</th><th>What it means</th><th class=num>Count</th></tr></thead>
    <tbody>{''.join(rule_rows)}</tbody>
  </table></div>

  <h2>Issues</h2>
  <div class="toolbar">
    <button class="on" data-filter="all">All</button>
    <button data-filter="error">Errors</button>
    <button data-filter="warning">Warnings</button>
    <button data-filter="info">Info</button>
    <input id="q" type="search" placeholder="Search code, reference, name, barcode…">
  </div>
  <div class="wrap">
    <table id="issues">
      <thead><tr><th class=num>Row</th><th>Severity</th><th>Code</th><th>Ref</th><th>Name</th>
      <th>Field</th><th>Value</th><th>Detail</th></tr></thead>
      <tbody>{''.join(issue_rows)}</tbody>
    </table>
    {empty_state}
  </div>
  <footer>Generated by gtin-audit {__version__}. Row numbers match the spreadsheet (header is row 1).</footer>
</main>
<script>
(function () {{
  var filter = "all", q = document.getElementById("q");
  var rows = Array.prototype.slice.call(document.querySelectorAll("#issues tbody tr"));
  function apply() {{
    var term = q.value.trim().toLowerCase();
    rows.forEach(function (r) {{
      var ok = (filter === "all" || r.dataset.sev === filter) && (!term || r.dataset.text.indexOf(term) !== -1);
      r.style.display = ok ? "" : "none";
    }});
  }}
  document.querySelectorAll(".toolbar button").forEach(function (b) {{
    b.addEventListener("click", function () {{
      document.querySelectorAll(".toolbar button").forEach(function (x) {{ x.classList.remove("on"); }});
      b.classList.add("on"); filter = b.dataset.filter; apply();
    }});
  }});
  q.addEventListener("input", apply);
}})();
</script>
</body>
</html>
"""


def write_html(issues, records, source_name, columns, path) -> Path:
    path = Path(path)
    path.write_text(render_html(issues, records, source_name, columns), encoding="utf-8")
    return path
