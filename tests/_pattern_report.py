"""Self-contained HTML reporting for pattern and overlap validation."""

import base64
from collections import Counter
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path


def _color(value):
    """Return a stable, readable color derived from an arbitrary cell value."""
    if (
        isinstance(value, tuple)
        and len(value) in {3, 4}
        and all(isinstance(channel, int) and 0 <= channel <= 255 for channel in value)
    ):
        if len(value) == 4:
            red, green, blue, alpha = value
            return f"rgba({red},{green},{blue},{alpha / 255:.3f})"
        return f"rgb({value[0]},{value[1]},{value[2]})"
    digest = sha256(str(value).encode("utf-8")).digest()
    return f"rgb({96 + digest[0] % 128},{96 + digest[1] % 128},{96 + digest[2] % 128})"


def _svg(rows, cell_size=32):
    """Render a text grid as an inline SVG tile image."""
    height = len(rows)
    width = len(rows[0])
    parts = [
        f'<svg class="tile" viewBox="0 0 {width * cell_size} {height * cell_size}" '
        f'role="img" aria-label="{escape(str(rows))}">'
    ]
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            parts.append(
                f'<rect x="{x * cell_size}" y="{y * cell_size}" '
                f'width="{cell_size}" height="{cell_size}" '
                f'fill="{_color(value)}" stroke="#222"/>'
            )
            parts.append(
                f'<text x="{x * cell_size + cell_size / 2}" '
                f'y="{y * cell_size + cell_size * 0.68}" '
                f'text-anchor="middle">{escape(str(value)) if isinstance(value, str) else ""}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _window_at(text_grid, pattern_size, origin_x, origin_y):
    """Read a source window by coordinates for report frequency accounting."""
    rows = []
    for y in range(pattern_size):
        cells = tuple(
            text_grid[origin_y + y][origin_x + x]
            for x in range(pattern_size)
        )
        rows.append("".join(cells) if isinstance(text_grid[origin_y + y], str) else cells)
    return tuple(rows)


def build_pattern_id_grid(text_grid, pattern_size, patterns):
    """Return the production-ID value at each extracted window position."""
    ids_by_rows = {pattern.rows: pattern.id for pattern in patterns}
    height = len(text_grid) - pattern_size + 1
    width = len(text_grid[0]) - pattern_size + 1
    return tuple(
        tuple(
            ids_by_rows[_window_at(text_grid, pattern_size, x, y)]
            for x in range(width)
        )
        for y in range(height)
    )


def _id_color(pattern_id):
    """Return a stable high-contrast RGB color for a pattern ID."""
    digest = sha256(f"pattern-{pattern_id}".encode("ascii")).digest()
    return tuple(55 + channel % 166 for channel in digest[:3])


def _heat_map_svg(id_grid, cell_size=42):
    """Render a labelled pattern-ID grid as inline SVG."""
    height, width = len(id_grid), len(id_grid[0])
    parts = [
        f'<svg class="heat-map" viewBox="0 0 {width * cell_size} {height * cell_size}" '
        'role="img" aria-label="Source-position pattern ID heat map">'
    ]
    for y, row in enumerate(id_grid):
        for x, pattern_id in enumerate(row):
            red, green, blue = _id_color(pattern_id)
            luminance = 0.299 * red + 0.587 * green + 0.114 * blue
            text_color = "#111" if luminance > 150 else "#fff"
            parts.append(
                f'<rect x="{x * cell_size}" y="{y * cell_size}" '
                f'width="{cell_size}" height="{cell_size}" '
                f'fill="rgb({red},{green},{blue})" stroke="#fff"/>'
                f'<text x="{x * cell_size + cell_size / 2}" '
                f'y="{y * cell_size + cell_size * .65}" text-anchor="middle" '
                f'fill="{text_color}">{pattern_id}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def write_heat_map_png(id_grid, output_path, cell_size=52):
    """Write a standalone labelled pattern-ID heat map PNG."""
    from PIL import Image, ImageDraw, ImageFont

    height, width = len(id_grid), len(id_grid[0])
    image = Image.new("RGB", (width * cell_size, height * cell_size), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for y, row in enumerate(id_grid):
        for x, pattern_id in enumerate(row):
            color = _id_color(pattern_id)
            box = (
                x * cell_size,
                y * cell_size,
                (x + 1) * cell_size - 1,
                (y + 1) * cell_size - 1,
            )
            draw.rectangle(box, fill=color, outline="white", width=2)
            label = str(pattern_id)
            label_box = draw.textbbox((0, 0), label, font=font)
            label_width = label_box[2] - label_box[0]
            label_height = label_box[3] - label_box[1]
            luminance = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
            draw.text(
                (
                    x * cell_size + (cell_size - label_width) / 2,
                    y * cell_size + (cell_size - label_height) / 2,
                ),
                label,
                fill="black" if luminance > 150 else "white",
                font=font,
            )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def _image_data_uri(image_path):
    """Embed the source image so the comparison report is self-contained."""
    encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _source_grid_explorer(text_grid, pattern_sizes=(3, 4), cell_size=36):
    """Render a labelled pixel grid with a row-major extraction-window explorer."""
    from wfc_to_sat.patterns import extract_patterns

    height, width = len(text_grid), len(text_grid[0])
    label_size = cell_size
    svg_width = label_size + width * cell_size
    svg_height = label_size + height * cell_size
    parts = [
        f'<svg id="source-grid" class="source-grid" viewBox="0 0 {svg_width} {svg_height}" '
        'role="img" aria-label="Simple Knot 11 by 11 source pixel grid with extraction window">'
    ]
    for x in range(width):
        parts.append(
            f'<text class="axis-label" x="{label_size + (x + .5) * cell_size}" '
            f'y="{label_size * .68}" text-anchor="middle">{x}</text>'
        )
    for y, row in enumerate(text_grid):
        parts.append(
            f'<text class="axis-label" x="{label_size * .55}" '
            f'y="{label_size + (y + .67) * cell_size}" text-anchor="middle">{y}</text>'
        )
        for x, value in enumerate(row):
            parts.append(
                f'<rect class="source-pixel" x="{label_size + x * cell_size}" '
                f'y="{label_size + y * cell_size}" width="{cell_size}" '
                f'height="{cell_size}" fill="{_color(value)}"/>'
            )
    parts.append(
        f'<rect id="extraction-window" class="extraction-window" '
        f'x="{label_size}" y="{label_size}" width="{3 * cell_size}" '
        f'height="{3 * cell_size}"/>'
    )
    parts.append('</svg>')

    explorer_data = {}
    for pattern_size in pattern_sizes:
        patterns = extract_patterns(text_grid, pattern_size)
        patterns_by_id = {pattern.id: pattern for pattern in patterns}
        id_grid = build_pattern_id_grid(text_grid, pattern_size, patterns)
        explorer_data[str(pattern_size)] = [
            {
                "x": x,
                "y": y,
                "id": pattern_id,
                "frequency": patterns_by_id[pattern_id].frequency,
            }
            for y, row in enumerate(id_grid)
            for x, pattern_id in enumerate(row)
        ]

    sizes = "".join(
        f'<option value="{pattern_size}">{pattern_size}</option>'
        for pattern_size in pattern_sizes
    )
    initial = explorer_data[str(pattern_sizes[0])][0]
    initial_count = len(explorer_data[str(pattern_sizes[0])])
    initial_details = (
        f"Origin ({initial['x']},{initial['y']}) · Pattern {initial['id']} · "
        f"Frequency {initial['frequency']} · Window 1/{initial_count}"
    )
    data = json.dumps(explorer_data, separators=(",", ":"))
    return f"""
<section class="source-explorer" aria-labelledby="source-grid-heading">
<h2 id="source-grid-heading">Source image and extraction scan</h2>
<p>Each outlined square is exactly one source pixel. The extraction window starts at
<strong>(0,0)</strong> and scans <strong>left-to-right, then top-to-bottom</strong>.</p>
<div class="explorer-controls">
<label>Pattern size <select id="pattern-size">{sizes}</select></label>
<button id="previous-origin" type="button" disabled>Previous</button>
<button id="next-origin" type="button">Next</button>
<output id="window-details" aria-live="polite">{initial_details}</output>
</div>
<div class="source-grid-wrap">{''.join(parts)}</div>
</section>
<script>
(() => {{
  const scans = {data};
  const cell = {cell_size};
  const label = {label_size};
  const sizeSelect = document.getElementById('pattern-size');
  const previous = document.getElementById('previous-origin');
  const next = document.getElementById('next-origin');
  const details = document.getElementById('window-details');
  const windowRect = document.getElementById('extraction-window');
  let index = 0;

  function render() {{
    const size = Number(sizeSelect.value);
    const origins = scans[size];
    const origin = origins[index];
    windowRect.setAttribute('x', label + origin.x * cell);
    windowRect.setAttribute('y', label + origin.y * cell);
    windowRect.setAttribute('width', size * cell);
    windowRect.setAttribute('height', size * cell);
    details.textContent = `Origin (${{origin.x}},${{origin.y}}) · Pattern ${{origin.id}} · Frequency ${{origin.frequency}} · Window ${{index + 1}}/${{origins.length}}`;
    previous.disabled = index === 0;
    next.disabled = index === origins.length - 1;
  }}
  sizeSelect.addEventListener('change', () => {{ index = 0; render(); }});
  previous.addEventListener('click', () => {{ if (index > 0) index -= 1; render(); }});
  next.addEventListener('click', () => {{
    if (index < scans[sizeSelect.value].length - 1) index += 1;
    render();
  }});
  render();
}})();
</script>"""


def build_comparison_report(image_path, text_grid, validated_cases):
    """Build the N=3/N=4 catalogue, heat-map, and frequency comparison."""
    from wfc_to_sat.patterns import extract_patterns

    sections = []
    for pattern_size, validation in validated_cases:
        patterns = extract_patterns(text_grid, pattern_size)
        id_grid = build_pattern_id_grid(text_grid, pattern_size, patterns)
        frequencies = sorted(patterns, key=lambda pattern: (-pattern.frequency, pattern.id))
        maximum = frequencies[0].frequency
        frequency_rows = "".join(
            '<div class="frequency-row">'
            f'<span class="frequency-label">Pattern {pattern.id}</span>'
            f'<span class="bar" style="width:{100 * pattern.frequency / maximum:.2f}%"></span>'
            f'<strong>{pattern.frequency}</strong></div>'
            for pattern in frequencies
        )
        catalogue = "".join(
            '<article class="pattern-card">'
            f'<h4>Pattern {pattern.id}</h4>{_svg(pattern.rows, cell_size=24)}'
            f'<p>Frequency: <strong>{pattern.frequency}</strong></p></article>'
            for pattern in patterns
        )
        sections.append(
            f'<section id="size-{pattern_size}"><h2>Pattern size {pattern_size}</h2>'
            '<div class="metrics">'
            f'<span>Windows <strong>{validation.windows}</strong></span>'
            f'<span>Unique patterns <strong>{validation.unique_patterns}</strong></span>'
            f'<span>Duplicate occurrences <strong>{validation.duplicate_occurrences}</strong></span>'
            '</div><p class="pass">Validation: PASS — extraction and overlaps match the '
            'independent oracle; repeated windows share one ID; frequencies match; '
            'frequency sum equals window count.</p>'
            f'<h3>Source-position heat map ({len(id_grid[0])}×{len(id_grid)})</h3>'
            '<p>Each cell is a source-window origin and displays its unique pattern ID.</p>'
            f'{_heat_map_svg(id_grid)}'
            '<h3>Frequency by unique pattern</h3>'
            f'<div class="frequencies">{frequency_rows}</div>'
            f'<details><summary>Catalogue ({len(patterns)} unique patterns)</summary>'
            f'<div class="catalogue">{catalogue}</div></details></section>'
        )

    source_explorer = _source_grid_explorer(text_grid)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simple Knot pattern comparison: N=3 and N=4</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1180px;margin:auto;padding:2rem;color:#20242a;background:#f5f7fa}}
h1,h2,h3{{line-height:1.15}}section{{background:white;padding:1.5rem;margin:1.5rem 0;border-radius:.6rem;box-shadow:0 1px 5px #ccd}}
.source-grid-wrap{{max-width:720px;overflow-x:auto}}.source-grid{{display:block;width:min(100%,600px);height:auto}}
.source-pixel{{stroke:#68717d;stroke-width:1;shape-rendering:crispEdges}}
.axis-label{{font:600 13px ui-monospace,monospace;fill:#303843}}
.extraction-window{{fill:#ffbd2e;fill-opacity:.18;stroke:#e4312b;stroke-width:4;vector-effect:non-scaling-stroke;pointer-events:none}}
.explorer-controls{{display:flex;flex-wrap:wrap;align-items:center;gap:.7rem;margin:1rem 0}}
.explorer-controls button,.explorer-controls select{{font:inherit;padding:.35rem .65rem}}
.explorer-controls output{{font-weight:700;flex-basis:100%}}
.metrics{{display:flex;flex-wrap:wrap;gap:.7rem}}.metrics span{{padding:.6rem .8rem;background:#edf2f7;border-radius:.35rem}}
.pass{{border-left:5px solid #16834a;padding:.65rem;background:#eaf8f0}}.heat-map{{width:min(100%,650px);height:auto;background:#ddd}}
.heat-map text{{font:bold 13px ui-monospace,monospace}}.frequencies{{max-width:720px}}
.frequency-row{{display:grid;grid-template-columns:90px 1fr 36px;align-items:center;gap:.7rem;margin:.3rem 0}}
.frequency-label{{font-size:.85rem}}.bar{{display:block;min-width:3px;height:1rem;background:#3769b0;border-radius:2px}}
.catalogue{{display:flex;flex-wrap:wrap;gap:.7rem;margin-top:1rem}}.pattern-card{{border:1px solid #ccd;padding:.5rem;border-radius:.35rem;background:#fafbfd}}
.pattern-card h4,.pattern-card p{{margin:.25rem 0}}.pattern-card .tile{{height:96px;width:auto}}summary{{cursor:pointer;font-weight:700;margin-top:1.5rem}}
</style></head><body><h1>Simple Knot validated pattern comparison</h1>
<p>Source: {escape(Path(image_path).name)} (11×11 pixels). Pattern IDs use the current local extractor's first-occurrence order.</p>
{source_explorer}
{''.join(sections)}</body></html>\n"""


def _observed_adjacencies(text_grid, pattern_size, direction):
    """Count ordered adjacent-window pairs occurring in the source grid."""
    window_height = len(text_grid) - pattern_size + 1
    window_width = len(text_grid[0]) - pattern_size + 1
    offset_x, offset_y = ((1, 0) if direction == "right" else (0, 1))
    counts = Counter()

    for y in range(window_height):
        for x in range(window_width):
            neighbor_x = x + offset_x
            neighbor_y = y + offset_y
            if neighbor_x >= window_width or neighbor_y >= window_height:
                continue
            first = _window_at(text_grid, pattern_size, x, y)
            second = _window_at(
                text_grid,
                pattern_size,
                neighbor_x,
                neighbor_y,
            )
            counts[(first, second)] += 1
    return counts


def _merged_rows(first, second, direction):
    """Compose two compatible patterns into their combined output footprint."""
    if direction == "right":
        rows = []
        for y in range(len(first.rows)):
            final_cell = second.rows[y][-1]
            if isinstance(first.rows[y], str):
                rows.append(first.rows[y] + final_cell)
            else:
                rows.append(first.rows[y] + (final_cell,))
        return tuple(rows)
    return first.rows + (second.rows[-1],)


def build_pattern_report(cases):
    """Build a self-contained HTML report for validated extraction cases."""
    from wfc_to_sat.compatibility import build_compatibility
    from wfc_to_sat.patterns import extract_patterns

    sections = []
    for name, text_grid, pattern_size in cases:
        patterns = extract_patterns(text_grid, pattern_size)
        by_id = {pattern.id: pattern for pattern in patterns}
        allowed = build_compatibility(patterns)
        pattern_cards = []
        for pattern in patterns:
            pattern_cards.append(
                '<article class="card">'
                f"<h3>Pattern {pattern.id}</h3>{_svg(pattern.rows)}"
                f"<p>Frequency: <strong>{pattern.frequency}</strong></p>"
                f"<code>{escape(str(pattern.rows))}</code>"
                "</article>"
            )

        overlap_groups = []
        for direction in ("right", "down"):
            observed = _observed_adjacencies(text_grid, pattern_size, direction)
            overlap_cards = []
            for first in patterns:
                for second_id in allowed[direction][first.id]:
                    second = by_id[second_id]
                    frequency = observed[(first.rows, second.rows)]
                    overlap_cards.append(
                        '<article class="card">'
                        f"<h3>{first.id} → {second.id} ({direction})</h3>"
                        f"{_svg(_merged_rows(first, second, direction))}"
                        f"<p>Observed frequency: <strong>{frequency}</strong></p>"
                        "</article>"
                    )
            overlap_groups.append(
                f"<h3>{direction.title()} overlaps ({len(overlap_cards)})</h3>"
                f'<div class="cards">{"".join(overlap_cards)}</div>'
            )

        sections.append(
            f"<section><h2>{escape(name)}</h2>"
            f"<p>Pattern size: {pattern_size}; source: "
            f"{len(text_grid[0])}×{len(text_grid)}</p>"
            f'<div class="cards">{"".join(pattern_cards)}</div>'
            f"{''.join(overlap_groups)}</section>"
        )

    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pattern extraction and overlap report</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1200px;margin:auto;padding:2rem;color:#222}
section{border-top:2px solid #bbb;margin-top:2rem}.cards{display:flex;flex-wrap:wrap;gap:1rem}
.card{border:1px solid #bbb;border-radius:.4rem;padding:.8rem;min-width:150px;background:#fafafa}
.card h3{margin-top:0}.tile{width:auto;height:128px;max-width:100%}.tile text{font:16px monospace;fill:#111}
code{font-size:.8rem}strong{font-variant-numeric:tabular-nums}
</style></head><body><h1>Pattern extraction and overlap report</h1>
<p>Overlap frequency is the number of times the ordered adjacent pair occurs in the source grid.</p>
""" + "".join(sections) + "</body></html>\n"
