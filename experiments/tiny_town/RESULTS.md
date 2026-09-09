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

## Section 9 verification

| Test | Result |
|---|---|
| `In` definition, both directions | Pass |
| Hand-forced ragged house | UNSAT (pass) |
| Flood-filled components = true anchors, 5 seeds | Pass |
| Exactly three houses, 5 seeds | Pass |
| More houses than fit on a 5×4 grid | Clean UNSAT (pass) |

The focused suite contains 38 passing checks (individual house-tile implications are
parameterized by assertion). A repository-wide run excluding the pre-existing trace
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
