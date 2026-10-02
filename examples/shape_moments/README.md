# Shape-moments prototype

Exploratory prototype for picking a **droplet shape** quantity to add to the
ROI analysis pane, next to Area. Everything here produces one scalar per ROI
per image — the same contract as the pane's `compute_image_stats` stats dict
and `plot_series.stat_value()` — so the winner can plug into the Over time /
Per image / Distribution views unchanged.

```bash
cd microdrop-py/src
pixi run --manifest-path ../pyproject.toml python -m examples.shape_moments.run [out_dir]
```

`out_dir` defaults to `examples/shape_moments/output/` (git-ignored). It gets
`frames/` (40 PNGs + `series.json` with the ROI definitions and per-frame
ground truth), `descriptors.csv`, `descriptors_over_time.png`,
`descriptors_distribution.png` and `contour_montage.png`.

| File | What it is |
| --- | --- |
| `synthetic.py` | 40 frames, 320×320 8-bit, five droplets each in a fixed circular ROI (r = 50 px), soft edges, σ = 4 noise |
| `descriptors.py` | Pure numpy/cv2 (no Qt, no `image_viewer` imports): Otsu inside the ROI → largest external contour → moments → descriptors |
| `run.py` | Generate, read frames back from disk, measure, write CSV + figures (matplotlib Agg) |
| `../tests/test_shape_descriptors.py` | Analytic circle / ellipse / rotated copy / bump / empty ROI |

## The test droplets

| | Behaviour | Should read as |
| --- | --- | --- |
| A | circle, unchanged | control: nothing changes |
| B | circle → ellipse, axis ratio 1 → 2.5 at constant area | elongation |
| C | a satellite blob grows next to the droplet and merges in at frame 20 | irregular outline |
| D | 2:1 ellipse turning −45° → +45° | no shape change; orientation changes |
| E | circle shrinking to 1/4 of its area | area change only |

## Descriptors

Definitions and the plain-language meaning of each are in the
`descriptors.py` module docstring. Summary: `area`, `centroid_x/y`,
`axis_ratio` (≥ 1, moment-equivalent ellipse), `eccentricity`,
`orientation_deg`, `circularity` (4πA/P²), `solidity` (A/hull),
`extent` (A/bounding box), `hu1..hu7` (log-scaled), and two
"changed since frame 0" scalars: `shape_deviation` (root-normalised Hu,
recommended) and `hu_log_deviation` (log Hu, for comparison).

## Results (seed 0, frame 0 → frame 39)

| | A circle | B elongate | C bump | D rotate | E shrink |
| --- | --- | --- | --- | --- | --- |
| area (px²) | 1477 → 1475 | 1472 → 1475 | 1479 → 1952 | 1188 → 1184 | 1473 → 361 |
| axis_ratio | 1.00 (sd 0.001) | **1.00 → 2.52** | 1.00 → 1.68 (jumps at merge) | 2.00 (sd 0.011) | 1.00 (max 1.02) |
| circularity | 0.98–1.00 | **0.98 → 0.74** | **0.98 → 0.62 → 0.74** | 0.82–0.83 | 0.97–0.99 |
| solidity | 0.98 (sd 0.001) | 0.97–0.99 | **0.98 → 0.89–0.92** | 0.97–0.98 | 0.97–0.99 |
| orientation_deg | noise ±90 | 0 (once elongated) | ≈ 30 (bump direction) | **−45.0 → +45.0** | noise ±90 |
| extent | 0.76 | 0.73–0.77 | 0.76 → 0.62 | **0.59–0.76 (rotation!)** | 0.69–0.76 |
| shape_deviation | ≤ 0.005 | **0 → 1.15** | **0 → 0.69** | ≤ 0.033 | ≤ 0.015 |
| hu_log_deviation | 0 → 40–68 | 0 → 26–54 | 0 → 39–67 | 0 → 2–55 | 0 → 40–67 |

Contour detection is clean in every frame (see the montage); before the merge
C's satellite is a separate speck, correctly ignored as "not the largest
contour".

Small droplets (separate probe, blurred circles, 10 frames each): radius
4 px reads circularity 0.94 ± 0.02, axis_ratio 1.05 (max 1.08),
shape_deviation ≤ 0.05; radius 8 px reads 0.97, 1.01 (max 1.03), ≤ 0.02.

## Recommendation

1. **`shape_deviation` — "Shape change"** is the one-number answer. It is 0
   for an unchanged droplet whatever its size, position or rotation (A, D, E
   all stay ≤ 0.033) and climbs steadily with real change (B → 1.15, C →
   0.69): a 20–35× margin over the noise floor. It is a *series* quantity
   (needs a reference image), so in the pane it belongs beside the existing
   baseline-subtraction logic (`subtracted_series`) rather than in the
   per-image worker: compute and store the root-normalised Hu vector per
   (image, ROI), take the distance from the ROI's first filtered,
   non-excluded image at series-derivation time.
2. **`axis_ratio` — "Axis ratio"** is the best interpretable per-image
   quantity: exactly the elongation number a user would quote (B reads 2.52
   for a true 2.5, D reads 2.00 for a true 2.0), rotation- and
   size-invariant, noise ≈ 0.01. Plugs straight into Over time / Per image /
   Distribution as a stats key.
3. **`solidity` — "Solidity"** is the irregularity signal that elongation
   cannot trigger: only C moves (0.98 → 0.89), every convex droplet stays
   0.97–0.99. Worth adding next to axis ratio if lobes, satellites, necking
   or partial splits matter.

Not recommended:

- **circularity** mixes elongation and irregularity (B and C both fall to
  ~0.74), so a drop does not say *what* changed; axis_ratio + solidity
  separate the two. Its absolute value also depends on the perimeter
  estimator (raw pixel contour: 0.90 for a circle; 1 px polygon smoothing,
  used here: 0.98).
- **eccentricity** is axis_ratio on a compressed, less intuitive scale.
- **extent** changes with pure rotation (D: 0.59–0.76) — misleading.
- **orientation_deg** is pure noise (±90°) for round droplets; only useful as
  a secondary "which way is it stretched" readout once axis_ratio > ~1.2.
- **hu_log_deviation** (the textbook log-Hu distance / `cv2.matchShapes`
  scaling) is unusable here: for round and elliptical droplets hu3..hu7 are
  ≈ 0 and their logarithms are dominated by pixel noise, so the unchanged
  circle A reads 40–68. The root normalisation in `shape_deviation` is the
  fix.

Proposed pane mapping: three Plot quantities — **"Shape change"**
(`shape_deviation`), **"Axis ratio"**, **"Solidity"** — all unit-less (the
scale calibration does not apply), each working in Over time / Per image /
Distribution. (`area` here is the *droplet's* area, not the ROI's pixel
count that the pane's current "Area" plots; a "Droplet area" quantity comes
free with the same segmentation if wanted.)

## Caveats

- **Threshold.** Otsu over the ROI assumes a bimodal ROI: droplet plus
  background. An ROI drawn tightly inside a droplet, or with almost no
  background, gets a meaningless split; uneven illumination shifts the
  boundary (the pane's rolling-ball correction should run first, as it does
  for the intensity stats). Dark-on-bright (back-lit) droplets need
  `polarity="dark"`. 16-bit frames are stretched over the ROI's own range
  before Otsu.
- **Touching / clipped droplets.** Two droplets in one ROI merge into one
  contour (reads as irregular); a droplet cut off by the ROI edge reads as
  flattened. A future version could flag a contour touching the ROI border.
- **Satellites.** Only the largest contour is measured, so a satellite is
  invisible until it merges — then the descriptors jump (C at frame 20).
- **Tiny ROIs.** At a few px radius (the Pi camera on a small electrode) the
  noise floor rises: axis_ratio up to ~1.08 and shape_deviation ~0.05 at
  r = 4 px. Below ~4 px the contour is too coarse to call a shape.
- **Synthetic data.** Smooth edges and Gaussian noise only; real frames have
  electrode edges, reflections and meniscus rings inside the ROI that can
  steal the Otsu split. Try it on a real image series before committing to
  thresholds.
