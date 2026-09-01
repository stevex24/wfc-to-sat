# Zelda 1x1 Follow-up Results

## Purpose

This follow-up completes the Zelda portion of the earlier detailed-comparison experiment, in which the Zelda SAT runs had not completed. Later diagnostics established several useful facts about the formula and decision policies, but the earlier execution has not been reconstructed sufficiently to make a confident historical claim about exactly why the original Context run timed out.

## Experiment

The completed matched experiment compared four conditions on the Zelda 1x1 model:

- Ordinary WFC — Frequency
- WFC-as-SAT — Frequency
- Ordinary WFC — Context
- WFC-as-SAT — Context

Every condition used a 20x20 output, seeds 0..99, 100 runs, and lexical location selection, for 400 successful runs total. Lexical selection determines **which output location is selected next**. Frequency weights the candidates at that location by their frequency in the source. Context instead weights candidates using this experiment's context-sensitive frequency rule.

## Results

All four conditions succeeded in 100/100 runs. There were no timeouts and no other failures.

| Heuristic | Engine | Pooled tile KL | Pooled edge KL |
| --- | --- | ---: | ---: |
| Frequency | Ordinary WFC | 0.141110 | 1.537492 |
| Frequency | WFC-as-SAT | 0.147489 | 1.542629 |
| Context | Ordinary WFC | 0.041169 | 0.065351 |
| Context | WFC-as-SAT | 0.050125 | 0.071992 |

For the SAT conditions, runtime and search totals were:

| Heuristic | Mean total runtime | Mean solve time | Total conflicts | Total observer backtracks |
| --- | ---: | ---: | ---: | ---: |
| Frequency | 3.913 s | 0.819 s | 55,339 | 57,118 |
| Context | 3.379 s | 0.278 s | 3,730 | 3,743 |

Context retained a strong aggregate fidelity advantage over Frequency. Within each heuristic, SAT closely preserved the aggregate distribution of the corresponding ordinary-WFC condition. Exact WFC/SAT image equality was not generally expected or obtained: Frequency had 0/100 exact paired images and Context had 1/100. Those exact-match counts should not be overinterpreted; the primary comparison is aggregate distributional fidelity, not identical per-seed images.

## What changed / diagnostic context

Follow-up diagnostics showed that:

- the Zelda 1x1 SAT formula itself was easy for plain CaDiCaL;
- DomainObserver attachment alone did not account for the earlier multi-minute behavior in the diagnostic configuration;
- different WFC decision policies produced dramatically different SAT search trajectories; and
- the Frequency- and Context-weighted conditions were practical, allowing the matched 100-seed study to be completed.

These observations do **not** definitively explain why the earlier Context run in the original report timed out. The precise historical cause of that timeout has not been reconstructed sufficiently to make that claim.

## Files

- [HTML report](zelda-1x1-weighted.html)
- [Raw matched-run JSON](raw/zelda-1x1-weighted-matched.json)
- [Per-run CSV](zelda-1x1-weighted-per-run.csv)
- [Summary CSV](zelda-1x1-weighted-summary.csv)
- [Matched experiment source](../../experiments/context_sensitive/zelda_weighted_sweep.py)
- Diagnostics: [plain CaDiCaL](../../experiments/context_sensitive/zelda_plain_sat_timing_probe.py), [observer/solver](../../experiments/context_sensitive/zelda_observer_solver_timing_probe.py), [baseline timing](../../experiments/context_sensitive/zelda_timing_probe.py), and [weighted timing](../../experiments/context_sensitive/zelda_weighted_timing_probe.py)

## Reproducibility / commit

- Branch: `spec-completion-report`
- Experiment commit: `ddd9ae5`

This README is necessarily recorded in a later documentation commit; the experiment data, report, and source listed above are from `ddd9ae5`.
