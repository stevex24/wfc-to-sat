# Context-Sensitive WFC-as-SAT Detailed Comparison

## Purpose

This report audits the original context-sensitive WFC-as-SAT experiment specification. Its main research question is whether steering a SAT solver with WFC-style decisions preserves the output-distribution behavior of ordinary overlapping WFC, and how uniform, source-frequency, and context-sensitive candidate weighting affect resemblance to the source.

The checkpoint is explicitly **partial**: it records completed measurements and leaves unavailable cells visible rather than filling them from later work.

## Experimental design

The primary study used two inputs: the text-based **Stick** model at pattern size N=1 and the authors' tiled **Zelda** map, with Zelda studies specified at N=1 and overlapping N=3. Primary outputs were 20x20 and used seeds 0..99 (100 runs per condition). Output-location selection was lexical. Generated boundaries were finite/nonperiodic; the verified Zelda N=3 specification used wrapped source-pattern extraction but nonwrapped output constraints and output-edge metrics.

For each heuristic, the intended matched comparison was ordinary WFC versus WFC-as-SAT:

- **Uniform** chooses among candidates uniformly.
- **Frequency** weights candidates by source frequency.
- **Context** uses the experiment's context-sensitive frequency rule.

Ordinary WFC is this repository's independent overlapping-WFC implementation and stops at a contradiction. WFC-as-SAT uses WFC-style decisions with CDCL recovery. A plain SAT/CDCL run was also included as a control where available. These different failure policies are reported, not treated as equivalent.

Resemblance was measured with KL divergence from the generated distribution P to the source distribution Q (natural logarithm, no smoothing; lower is closer), for pattern frequency, pattern-edge frequency, decoded-tile frequency, and decoded-tile-edge frequency. At N=1, pattern and decoded-tile metrics are mathematically identical. The report contains pooled KL values, per-run mean/median/standard deviation, success/failure and runtime data, conflicts/backtracks where applicable, Zelda N=1 axis-specific lag-r measurements for r=1,2,4,8,16, and seed-0 N=3 repository benchmark diagnostics. Peak memory was not measured.

## Results

The completed primary matched study was **Stick N=1**. Every ordinary-WFC and WFC-as-SAT condition succeeded in 100/100 runs, with all 100 paired grids exactly identical within each heuristic because these runs had no conflicts or backtracks.

| Stick heuristic | WFC pooled tile KL | SAT pooled tile KL | WFC pooled edge KL | SAT pooled edge KL |
| --- | ---: | ---: | ---: | ---: |
| Uniform | 0.201085 | 0.201085 | 0.566717 | 0.566717 |
| Frequency | 0.000201 | 0.000201 | 0.085051 | 0.085051 |
| Context | 0.002608 | 0.002608 | 0.000837 | 0.000837 |

Mean runtimes for ordinary WFC / WFC-as-SAT were 0.0722 / 0.0767 seconds for Uniform, 0.0945 / 0.0940 seconds for Frequency, and 0.0971 / 0.0984 seconds for Context. The one deterministic Stick plain-SAT control succeeded, with pooled tile KL 0.501859, pooled edge KL 0.998043, and runtime 0.0252 seconds.

The **Zelda N=1 ordinary-WFC** arms also completed 100/100 runs each. Their pooled tile / edge KL values were 0.291385 / 1.466527 for Uniform, 0.141110 / 1.537492 for Frequency, and 0.041169 / 0.065351 for Context. The corresponding Zelda SAT cells were missing at this checkpoint, so these values are not WFC/SAT comparisons.

Zelda N=3 had no generated primary outputs. The report also includes six seed-0, N=3, 8x8-placement repository benchmark diagnostics; it explicitly treats them as diagnostics rather than primary distribution estimates. The report's overall acceptance status is therefore partial.

## Zelda status at this checkpoint

The original report says that the Zelda N=1 SAT pilot exceeded 90 seconds before completing one seed and was stopped; the 100-run SAT rerun was not launched. Thus only ordinary WFC completed for Zelda N=1 in this checkpoint.

For Zelda N=3, the report records 2,958 patterns and states that the existing exact-one encoding alone would exceed 1.7 billion pair clauses at 20x20. No faithful Zelda N=3 SAT run was launched and no Zelda N=3 outputs were saved. These are checkpoint observations, not a claim about the precise cause of the Zelda N=1 pilot behavior.

Zelda was investigated subsequently, but those later experiments and results are deliberately excluded here and have separate documentation.

## Files

- [HTML report](index.html)
- Raw data: [Stick matched runs](../core-comparison/raw-runs.json), [Zelda N=1](raw/zelda-1x1.json), and [Zelda N=1 lag-r](raw/zelda-1x1-lag-r.json)
- Summary data: [main results](results.csv), [per-run statistics](per-run.csv), and [performance](performance.csv)
- Experiment/report source: [detailed report generator](../../experiments/context_sensitive/detailed_report.py) and [Zelda experiment](../../experiments/context_sensitive/zelda_experiment.py)

No standalone copy of the original experiment specification or prompt was committed at this checkpoint; the HTML report is itself a specification-compliance audit and records the implemented requirements and gaps.

## Reproducibility

- Branch: `spec-completion-report`
- Report creation commit: `fdd168a`
- Final original report correction commit: `a6f7f92`
- Recorded execution base commit: `e4db319f22181599127127b172a06c30ddf11b9d`
- Recorded analysis-code commit: `5c4069d`

This README is a later documentation-only commit. The original results summarized here are those in the report finalized at `a6f7f92`, before the subsequent Zelda experiments.
