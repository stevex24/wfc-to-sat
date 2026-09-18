# Verified result

Command:

```bash
python experiments/tiny_town/house_experiment.py \
  --width 12 --height 10 --min-houses 3 --max-houses 3 \
  --exact-houses 3 --seed 4 \
  --output-prefix local-generated-output/tiny-town/three-houses
```

Result: SAT with exactly three separated, equal-width houses. Each house has one top
roof row, one to three lower-roof rows, and at least one body row. Tile style families
remain consistent within each house.

After the follow-up fixes, each house also has a door on its final body row,
upper body rows cannot contain doors, and roof tiles with a dark right edge
appear only next to the gable. A freshly generated 12×10, exact-three map was
independently checked for bottom-row doors and roof-edge placement.

## Section 9 verification

| Test | Result |
|---|---|
| `In` definition, both directions | Pass |
| Hand-forced ragged house | UNSAT (pass) |
| Flood-filled components = true anchors, 10 seeds plus exact counts 1–3 | Pass |
| Exactly three houses, 20 seeds plus 10 further seeds | Pass |
| More houses than fit on a 5×4 grid | Clean UNSAT (pass) |
| Bottom-row door required; door forbidden above the bottom | Pass |
| Gable-edge roof sprites cannot occur mid-roof; tiers cannot mix | Pass |

The focused suite now contains 52 passing cases. A repository-wide run excluding the pre-existing trace
fixture test passes. The excluded test refers to absent `examples/visualizer/pipes-*`
files on this branch.

## Heuristic smoke comparison

The same compiled 12×10 exact-three instance was solved through the instrumented
observer in both modes:

| Mode | Result | Conflicts | Decisions | Propagations |
|---|---:|---:|---:|---:|
| Solver | SAT | 23 | 874 | 11,470 |
| Skeleton-first | SAT | 18 | 160 | 6,405 |

These are smoke-test measurements, not a performance claim; the skeleton run observes
additional variables and therefore has different callback overhead.
