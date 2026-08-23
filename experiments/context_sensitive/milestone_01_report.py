#!/usr/bin/env python3
"""Generate the milestone-01 Stick context-frequency diagnostic."""

from __future__ import annotations

from html import escape
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wfc_to_sat.context_frequency import UNK, ContextFrequencies, masked_contexts


SOURCE_PATH = ROOT / "examples" / "context-sensitive" / "stick.txt"
DEFAULT_OUTPUT = ROOT / "context-sensitive-results" / "milestone-01" / "index.html"


def read_source() -> tuple[tuple[str, ...], ...]:
    rows = tuple(tuple(line.strip()) for line in SOURCE_PATH.read_text().splitlines() if line.strip())
    if len(rows) != 7 or any(len(row) != 7 for row in rows):
        raise ValueError("Stick source must be 7x7")
    return rows


def label(value: object) -> str:
    return "UNK" if value is UNK else str(value)


def context_markup(context) -> str:
    north, east, south, west = context
    cells = ("", north, "", west, "x", east, "", south, "")
    return '<span class="context">' + "".join(
        f'<span class="value {"unknown" if value is UNK else ""}">{escape(label(value))}</span>'
        for value in cells
    ) + "</span>"


def build_report() -> str:
    source = read_source()
    table = ContextFrequencies(source)
    source_cells = []
    for y, row in enumerate(source):
        for x, tile in enumerate(row):
            source_cells.append(
                f'<div class="tile tile-{tile}" title="({x},{y}) = {tile}"><small>{x},{y}</small>{tile}</div>'
            )

    examples = []
    requested = (
        (3, 3, "complete interior context"),
        (3, 1, "complete context beside the top of the stick"),
        (0, 0, "boundary context"),
    )
    for x, y, description in requested:
        tile, complete = table.complete_contexts[y * table.width + x]
        variants = masked_contexts(complete)
        chosen = (complete, variants[-1]) if complete != variants[-1] else (complete,)
        for context in chosen:
            examples.append(
                "<tr>"
                f"<td>({x},{y})</td><td>{escape(description)}</td><td>{tile}</td>"
                f"<td>{context_markup(context)}<code>({', '.join(label(v) for v in context)})</code></td>"
                f"<td>{table.frequency(tile, context)}</td>"
                "</tr>"
            )

    all_unknown = (UNK, UNK, UNK, UNK)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Stick context-frequency diagnostic</title>
<style>
body{{font:16px/1.45 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033;background:#f6f8fb}}
h1,h2{{line-height:1.15}} code{{white-space:nowrap}} .layout{{display:flex;gap:2rem;align-items:flex-start;flex-wrap:wrap}}
.source{{display:grid;grid-template-columns:repeat(7,58px);border:2px solid #172033;background:#172033;gap:2px}}
.tile{{height:58px;display:flex;align-items:center;justify-content:center;position:relative;font-weight:700}}
.tile small{{position:absolute;left:3px;top:2px;font-size:10px;color:#64748b}} .tile-B{{background:#18181b;color:white}} .tile-B small{{color:#a1a1aa}} .tile-W{{background:white;color:#172033}}
table{{border-collapse:collapse;background:white;width:100%}} th,td{{border:1px solid #cbd5e1;padding:.55rem;text-align:left;vertical-align:middle}} th{{background:#e2e8f0}}
.context{{display:inline-grid;grid-template-columns:repeat(3,2rem);grid-template-rows:repeat(3,2rem);gap:2px;vertical-align:middle;margin-right:.75rem}}
.value{{display:flex;align-items:center;justify-content:center;background:#dbeafe;font-size:.72rem}} .value:empty{{background:transparent}} .value.unknown{{background:#fef3c7;color:#92400e}} .note{{background:#e0f2fe;border-left:4px solid #0284c7;padding:.8rem 1rem}}
</style></head><body>
<h1>Milestone 01: Stick context-frequency preprocessing</h1>
<p class="note">This validates preprocessing only. It does not claim reproduction of the paper's generated WFC outputs.</p>
<div class="layout"><section><h2>Paper Stick source</h2><div class="source">{''.join(source_cells)}</div>
<p>Coordinates are <code>x,y</code>, with <code>(0,0)</code> at top left. The fourth column contains five white tiles. Counts: <strong>B = {table.tile_frequency('B')}</strong>, <strong>W = {table.tile_frequency('W')}</strong>.</p></section>
<section><h2>How a context is read</h2>{context_markup(('N','E','S','W'))}<p>Tuple order is <strong>(north, east, south, west)</strong>. <code>x</code> marks the candidate cell. Boundary or undecided neighbors use <strong>UNK</strong>.</p></section></div>
<h2>Representative counts</h2><table><thead><tr><th>Source coordinate</th><th>Case</th><th>x</th><th>c</th><th>freq(x,c)</th></tr></thead><tbody>{''.join(examples)}</tbody></table>
<h2>All-UNK sanity check</h2><p>Every source occurrence contributes its all-UNK masked context. Therefore <code>freq(B,(UNK,UNK,UNK,UNK)) = {table.frequency('B', all_unknown)}</code> and <code>freq(W,(UNK,UNK,UNK,UNK)) = {table.frequency('W', all_unknown)}</code>, exactly matching source multiplicities.</p>
<h2>Counting rule</h2><p>For each source cell, preprocessing records its complete four-neighbor context, using UNK at the source boundary. It then independently keeps or masks each known neighbor. Four known neighbors yield 16 unique variants; two known boundary neighbors yield 4. Identical <code>(x,c)</code> keys from different coordinates accumulate multiplicity.</p>
</body></html>"""


def main() -> None:
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(build_report(), encoding="utf-8")
    print(DEFAULT_OUTPUT)


if __name__ == "__main__":
    main()
