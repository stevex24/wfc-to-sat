from pathlib import Path

path = Path("experiments/waps_probe_complex/mini_waps_probe_complex.py")
text = path.read_text()
Path("experiments/waps_probe_complex/mini_waps_probe_complex.py.before-record-failures").write_text(text)

old = '''            wfc_grid = generate_pattern_grid(patterns, allowed, size, size, weighted=False)
            weighted_grid = generate_pattern_grid(patterns, allowed, size, size, weighted=True)

            wfc_dist = pattern_distribution(wfc_grid, patterns)
            weighted_dist = pattern_distribution(weighted_grid, patterns)

            wfc_errors.append(tv_distance(target, wfc_dist))
            weighted_errors.append(tv_distance(target, weighted_dist))

            if size == sizes[-1] and trial == 0:
                representative_wfc = wfc_grid
                representative_weighted = weighted_grid'''

new = '''            try:
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
                representative_weighted = weighted_grid'''

if old not in text:
    raise SystemExit("Could not find trial loop block.")

text = text.replace(old, new)

text = text.replace(
    'mean_wfc = sum(wfc_errors) / len(wfc_errors)',
    'mean_wfc = sum(wfc_errors) / len(wfc_errors) if wfc_errors else float("nan")'
)

text = text.replace(
    'mean_weighted = sum(weighted_errors) / len(weighted_errors)',
    'mean_weighted = sum(weighted_errors) / len(weighted_errors) if weighted_errors else float("nan")'
)

text = text.replace(
    'f"WFC_error={mean_wfc:.4f} "\n            f"MiniWAPS_error={mean_weighted:.4f}"',
    'f"WFC_error={mean_wfc:.4f} success={len(wfc_errors)}/{trials} "\n            f"MiniWAPS_error={mean_weighted:.4f} success={len(weighted_errors)}/{trials}"'
)

text = text.replace(
    '"wfc_error": mean_wfc,\n                "weighted_error": mean_weighted,',
    '"wfc_error": mean_wfc,\n                "weighted_error": mean_weighted,\n                "wfc_success": len(wfc_errors),\n                "weighted_success": len(weighted_errors),\n                "trials": trials,'
)

path.write_text(text)
print("Patched script to record generator failures instead of crashing.")
