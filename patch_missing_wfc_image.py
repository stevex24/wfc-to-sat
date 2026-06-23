from pathlib import Path

path = Path("experiments/waps_probe_complex/mini_waps_probe_complex.py")
text = path.read_text()
Path("experiments/waps_probe_complex/mini_waps_probe_complex.py.before-missing-wfc-image").write_text(text)

text = text.replace(
'''    assert representative_wfc is not None
    assert representative_weighted is not None

    wfc_text = reconstruct(representative_wfc, patterns)
    weighted_text = reconstruct(representative_weighted, patterns)

    render_text_grid(wfc_text, OUTDIR / "wfc_output.png", "WFC output")
    render_text_grid(weighted_text, OUTDIR / "mini_waps_output.png", "Mini-WAPS output")

    wfc_dist = pattern_distribution(representative_wfc, patterns)
    weighted_dist = pattern_distribution(representative_weighted, patterns)
''',
'''    if representative_wfc is not None:
        wfc_text = reconstruct(representative_wfc, patterns)
        render_text_grid(wfc_text, OUTDIR / "wfc_output.png", "WFC output")
        wfc_dist = pattern_distribution(representative_wfc, patterns)
    else:
        wfc_dist = {p.id: 0.0 for p in patterns}

    assert representative_weighted is not None

    weighted_text = reconstruct(representative_weighted, patterns)
    render_text_grid(weighted_text, OUTDIR / "mini_waps_output.png", "Mini-WAPS output")

    weighted_dist = pattern_distribution(representative_weighted, patterns)
'''
)

path.write_text(text)
print("Patched missing WFC representative image handling.")
