# Mini-WAPS Experiment Notes

In a synthetic biased 24x24 PCG-style training map with 36 extracted 2x2 patterns, the mini-WAPS weighted sampler produced lower total-variation distance from the training pattern distribution than the unweighted WFC-style generator at every tested output size.

Results:

12x12: WFC 0.8220, Mini-WAPS 0.5665
20x20: WFC 0.8355, Mini-WAPS 0.7355
32x32: WFC 0.8483, Mini-WAPS 0.7250
48x48: WFC 0.8542, Mini-WAPS 0.6774

These preliminary results suggest that frequency-aware weighted sampling may preserve learned pattern distributions better than ordinary WFC-style generation. This motivates future experiments using WAPS proper.
