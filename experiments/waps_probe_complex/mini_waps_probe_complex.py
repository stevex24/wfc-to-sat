from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import math
import random

import matplotlib.pyplot as plt


OUTDIR = Path("experiments/waps_probe_complex/out")
OUTDIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 7
random.seed(RANDOM_SEED)


@dataclass(frozen=True)
class Pattern:
    id: int
    rows: tuple[str, ...]
    frequency: int


def make_training_grid(size: int = 36) -> list[str]:
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

    return grid

def extract_patterns(text_grid: list[str], pattern_size: int) -> list[Pattern]:
    counts: Counter[tuple[str, ...]] = Counter()
    h = len(text_grid)
    w = len(text_grid[0])

    for y in range(h - pattern_size + 1):
        for x in range(w - pattern_size + 1):
            rows = tuple(text_grid[y + dy][x : x + pattern_size] for dy in range(pattern_size))
            counts[rows] += 1

    return [
        Pattern(id=i, rows=rows, frequency=freq)
        for i, (rows, freq) in enumerate(counts.items())
    ]


def overlaps_right(left: Pattern, right: Pattern) -> bool:
    n = len(left.rows)
    return all(left.rows[y][1:] == right.rows[y][: n - 1] for y in range(n))


def overlaps_down(top: Pattern, bottom: Pattern) -> bool:
    n = len(top.rows)
    return all(top.rows[y] == bottom.rows[y - 1] for y in range(1, n))


def build_compatibility(patterns: list[Pattern]) -> dict[str, dict[int, list[int]]]:
    allowed = {"right": {}, "down": {}}

    for p1 in patterns:
        allowed["right"][p1.id] = []
        allowed["down"][p1.id] = []

        for p2 in patterns:
            if overlaps_right(p1, p2):
                allowed["right"][p1.id].append(p2.id)
            if overlaps_down(p1, p2):
                allowed["down"][p1.id].append(p2.id)

    return allowed


def compatible_with_neighbors(
    grid: list[list[int | None]],
    x: int,
    y: int,
    pid: int,
    allowed: dict[str, dict[int, list[int]]],
) -> bool:
    if x > 0 and grid[y][x - 1] is not None:
        if pid not in allowed["right"][grid[y][x - 1]]:
            return False

    if y > 0 and grid[y - 1][x] is not None:
        if pid not in allowed["down"][grid[y - 1][x]]:
            return False

    return True


def random_choice(items: list[int]) -> int:
    return random.choice(items)


def weighted_choice(items: list[int], weights: dict[int, float]) -> int:
    total = sum(weights[i] for i in items)
    r = random.random() * total
    upto = 0.0

    for i in items:
        upto += weights[i]
        if upto >= r:
            return i

    return items[-1]


def generate_pattern_grid(
    patterns: list[Pattern],
    allowed: dict[str, dict[int, list[int]]],
    width: int,
    height: int,
    weighted: bool,
    max_restarts: int = 200,
) -> list[list[int]]:
    """Simple restart-based WFC-like generator.

    weighted=False: ordinary random legal choice.
    weighted=True: mini-WAPS-style frequency-weighted legal choice.
    """
    pattern_ids = [p.id for p in patterns]
    weights = {p.id: float(p.frequency) for p in patterns}

    for _ in range(max_restarts):
        grid: list[list[int | None]] = [[None for _ in range(width)] for _ in range(height)]
        failed = False

        for y in range(height):
            for x in range(width):
                candidates = [
                    pid
                    for pid in pattern_ids
                    if compatible_with_neighbors(grid, x, y, pid, allowed)
                ]

                if not candidates:
                    failed = True
                    break

                if weighted:
                    grid[y][x] = weighted_choice(candidates, weights)
                else:
                    grid[y][x] = random_choice(candidates)

            if failed:
                break

        if not failed:
            return [[int(v) for v in row] for row in grid]  # type: ignore[arg-type]

    raise RuntimeError("Generator failed after restarts")


def reconstruct(pattern_grid: list[list[int]], patterns: list[Pattern]) -> list[str]:
    by_id = {p.id: p for p in patterns}
    n = len(patterns[0].rows)
    out_h = len(pattern_grid) + n - 1
    out_w = len(pattern_grid[0]) + n - 1
    out = [["?" for _ in range(out_w)] for _ in range(out_h)]

    for y, row in enumerate(pattern_grid):
        for x, pid in enumerate(row):
            p = by_id[pid]
            for dy in range(n):
                for dx in range(n):
                    out[y + dy][x + dx] = p.rows[dy][dx]

    return ["".join(row) for row in out]


def pattern_distribution(pattern_grid: list[list[int]], patterns: list[Pattern]) -> dict[int, float]:
    counts = Counter(pid for row in pattern_grid for pid in row)
    total = sum(counts.values())
    return {p.id: counts[p.id] / total for p in patterns}


def training_distribution(patterns: list[Pattern]) -> dict[int, float]:
    total = sum(p.frequency for p in patterns)
    return {p.id: p.frequency / total for p in patterns}


def tv_distance(a: dict[int, float], b: dict[int, float]) -> float:
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def render_text_grid(text_grid: list[str], path: Path, title: str) -> None:
    colors = {
        "G": "#70ad47",  # grass
        "F": "#1f7a3a",  # forest
        "W": "#4f81bd",  # water
        "M": "#7f7f7f",  # mountain
        "T": "#c0504d",  # town
        "R": "#f4b183",  # road
        "D": "#d9c27f",  # desert
        "?": "#ffffff",
    }

    h = len(text_grid)
    w = len(text_grid[0])

    fig, ax = plt.subplots(figsize=(max(5, w / 4), max(5, h / 4)))
    for y, row in enumerate(text_grid):
        for x, ch in enumerate(row):
            ax.add_patch(
                plt.Rectangle(
                    (x, h - y - 1),
                    1,
                    1,
                    facecolor=colors.get(ch, "#dddddd"),
                    edgecolor="black",
                    linewidth=0.15,
                )
            )

    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title)
    plt.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_distribution(
    target: dict[int, float],
    wfc: dict[int, float],
    weighted: dict[int, float],
    path: Path,
) -> None:
    pattern_ids = sorted(target.keys())
    xs = list(range(len(pattern_ids)))
    width = 0.25

    fig, ax = plt.subplots(figsize=(max(8, len(pattern_ids) * 0.35), 5))

    ax.bar([x - width for x in xs], [target[i] for i in pattern_ids], width, label="Training")
    ax.bar(xs, [wfc[i] for i in pattern_ids], width, label="WFC")
    ax.bar([x + width for x in xs], [weighted[i] for i in pattern_ids], width, label="Mini-WAPS")

    ax.set_title("Pattern frequency distribution")
    ax.set_xlabel("Pattern ID")
    ax.set_ylabel("Frequency")
    ax.set_xticks(xs)
    ax.set_xticklabels([str(i) for i in pattern_ids], rotation=90)
    ax.legend()
    plt.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_error_vs_size(results: list[dict[str, float]], path: Path) -> None:
    sizes = [r["size"] for r in results]
    wfc = [r["wfc_error"] for r in results]
    weighted = [r["weighted_error"] for r in results]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(sizes, wfc, marker="o", label="WFC")
    ax.plot(sizes, weighted, marker="o", label="Mini-WAPS")

    ax.set_title("Distribution error vs output size")
    ax.set_xlabel("Pattern-grid width")
    ax.set_ylabel("Total variation distance")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> None:
    pattern_size = 2
    training = make_training_grid(24)
    patterns = extract_patterns(training, pattern_size)
    allowed = build_compatibility(patterns)
    target = training_distribution(patterns)

    print(f"Training grid: {len(training[0])}x{len(training)}")
    print(f"Pattern size: {pattern_size}")
    print(f"Distinct patterns: {len(patterns)}")

    render_text_grid(training, OUTDIR / "training.png", "Training image")

    sizes = [12, 20, 32, 48]
    trials = 20
    results = []

    representative_wfc = None
    representative_weighted = None

    for size in sizes:
        wfc_errors = []
        weighted_errors = []

        for trial in range(trials):
            try:
                wfc_grid = generate_pattern_grid(patterns, allowed, size, size, weighted=False)
                wfc_dist = pattern_distribution(wfc_grid, patterns)
                wfc_errors.append(tv_distance(target, wfc_dist))
            except RuntimeError:
                wfc_grid = None

            try:
                weighted_grid = generate_pattern_grid(patterns, allowed, size, size, weighted=True)
                weighted_dist = pattern_distribution(weighted_grid, patterns)
                weighted_errors.append(tv_distance(target, weighted_dist))
            except RuntimeError:
                weighted_grid = None

            if size == sizes[-1] and trial == 0:
                representative_wfc = wfc_grid
                representative_weighted = weighted_grid

        mean_wfc = sum(wfc_errors) / len(wfc_errors) if wfc_errors else float("nan")
        mean_weighted = sum(weighted_errors) / len(weighted_errors) if weighted_errors else float("nan")

        print(
            f"size={size}x{size} "
            f"WFC_error={mean_wfc:.4f} success={len(wfc_errors)}/{trials} "
            f"MiniWAPS_error={mean_weighted:.4f} success={len(weighted_errors)}/{trials}"
        )

        results.append(
            {
                "size": size,
                "wfc_error": mean_wfc,
                "weighted_error": mean_weighted,
                "wfc_success": len(wfc_errors),
                "weighted_success": len(weighted_errors),
                "trials": trials,
            }
        )

    if representative_wfc is not None:
        wfc_text = reconstruct(representative_wfc, patterns)
        render_text_grid(wfc_text, OUTDIR / "wfc_output.png", "WFC output")
        wfc_dist = pattern_distribution(representative_wfc, patterns)
    else:
        wfc_dist = {p.id: 0.0 for p in patterns}

    assert representative_weighted is not None

    weighted_text = reconstruct(representative_weighted, patterns)
    render_text_grid(weighted_text, OUTDIR / "mini_waps_output.png", "Mini-WAPS output")

    weighted_dist = pattern_distribution(representative_weighted, patterns)

    plot_distribution(
        target,
        wfc_dist,
        weighted_dist,
        OUTDIR / "distribution_comparison.png",
    )

    plot_error_vs_size(results, OUTDIR / "error_vs_size.png")

    with open(OUTDIR / "results.md", "w", encoding="utf-8") as f:
        f.write("# Complex Mini-WAPS Probe Results\n\n")
        f.write(f"Training grid: {len(training[0])}x{len(training)}\n\n")
        f.write(f"Pattern size: {pattern_size}\n\n")
        f.write(f"Distinct patterns: {len(patterns)}\n\n")
        f.write("| Pattern-grid size | WFC TV error | Mini-WAPS TV error |\n")
        f.write("|---:|---:|---:|\n")
        for r in results:
            f.write(
                f"| {int(r['size'])}x{int(r['size'])} "
                f"| {r['wfc_error']:.4f} "
                f"| {r['weighted_error']:.4f} |\n"
            )

        f.write("\nGenerated figures:\n\n")
        f.write("- training.png\n")
        f.write("- wfc_output.png\n")
        f.write("- mini_waps_output.png\n")
        f.write("- distribution_comparison.png\n")
        f.write("- error_vs_size.png\n")

    print()
    print(f"Saved results to: {OUTDIR}")


if __name__ == "__main__":
    main()
