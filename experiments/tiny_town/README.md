# Tiny Town structured-house SAT experiment

This is a generative structure experiment, not an object detector. It compiles Kenney
Tiny Town tile roles, row grammar, equal-width constraints, house anchors, and a unary
cardinality counter into one CNF instance.

```bash
python -m pip install -r requirements.txt
python experiments/tiny_town/house_experiment.py \
  --width 16 --height 12 --min-houses 3 --max-houses 3 --seed 0
```

Use `--exact-houses N` to impose retractable counter-output assumptions against the
same compiled range. Outputs are written under `local-generated-output/tiny-town/`:
DIMACS, mapping sidecar, decoded JSON, and a PNG using the actual Kenney sprites.

The first run downloads only the tiles declared in `manifest.json` from Kenney's CC0
archive. See `SECTION_8_FINDINGS.md` for the required pre-coding inspection conclusions.
