from pathlib import Path

path = Path("experiments/waps_probe_complex/mini_waps_probe_complex.py")
text = path.read_text()
Path("experiments/waps_probe_complex/mini_waps_probe_complex.py.before-complex-training").write_text(text)

start = text.index("def make_training_grid")
end = text.index("\n\ndef extract_patterns", start)

new_make_training_grid = r'''def make_training_grid(size: int = 36) -> list[str]:
    """Richer synthetic PCG-like map.

    Tile symbols:
    G = grass
    F = forest
    W = water
    M = mountain
    T = town
    R = road
    D = desert
    """
    grid = []

    for y in range(size):
        row = []

        for x in range(size):
            # Large biome structure.
            if x < size * 0.34:
                ch = "G"      # grassland
            elif x < size * 0.67:
                ch = "F"      # forest
            else:
                ch = "D"      # desert

            # Water basin in lower-right.
            if x > size * 0.55 and y > size * 0.62:
                ch = "W"

            # Mountain ridge.
            if abs(x - y + 6) <= 1 and 4 < x < size - 5:
                ch = "M"

            # Secondary mountain spur.
            if abs((size - 1 - x) - y + 8) <= 1 and size * 0.45 < x < size * 0.85:
                ch = "M"

            # Road running roughly west-east with a bend.
            road_y = int(size * 0.52 + 3 * math.sin(x / 4.0))
            if abs(y - road_y) <= 0:
                ch = "R"

            # North-south road connector.
            if abs(x - int(size * 0.42)) <= 0 and size * 0.25 < y < size * 0.80:
                ch = "R"

            # Towns placed along roads.
            town_cells = {
                (int(size * 0.18), int(size * 0.52)),
                (int(size * 0.42), int(size * 0.35)),
                (int(size * 0.42), int(size * 0.70)),
                (int(size * 0.72), int(size * 0.49)),
            }

            if (x, y) in town_cells:
                ch = "T"

            row.append(ch)

        grid.append("".join(row))

    return grid'''
text = text[:start] + new_make_training_grid + text[end:]

start = text.index("def render_text_grid")
colors_start = text.index("    colors = {", start)
colors_end = text.index("    }\n", colors_start) + len("    }\n")

new_colors = '''    colors = {
        "G": "#70ad47",  # grass
        "F": "#1f7a3a",  # forest
        "W": "#4f81bd",  # water
        "M": "#7f7f7f",  # mountain
        "T": "#c0504d",  # town
        "R": "#f4b183",  # road
        "D": "#d9c27f",  # desert
        "?": "#ffffff",
    }
'''

text = text[:colors_start] + new_colors + text[colors_end:]

# Update labels in result title/file heading if present.
text = text.replace("# Mini-WAPS Probe Results", "# Complex Mini-WAPS Probe Results")

path.write_text(text)
print("Patched complex training generator and colors.")
print("Backup saved as mini_waps_probe_complex.py.before-complex-training")
