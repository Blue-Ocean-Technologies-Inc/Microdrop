# Scipy Random Analysis — demo plugin

A self-contained example MicroDrop plugin that demonstrates **dependency-aware
install**. It adds a dock pane where you pick a probability distribution and a
sample size and click **Generate & Analyze**; it draws fresh random samples
(numpy), runs a few `scipy.stats` analyses on them (skewness, excess kurtosis, a
normality test, and a Gaussian KDE), and plots a histogram with the KDE overlaid
(matplotlib).

`scipy` is **intentionally not** in MicroDrop's base environment, so this plugin
is the example for the dependency-resolution flow.

## Build the archive

```bash
pixi run python examples/build_scipy_plugin_zip.py
# -> examples/plugins/scipy_analysis.microdrop_plugin
```

## Install it (in the running app)

1. **Tools → Install Plugin…**, pick `scipy_analysis.microdrop_plugin`, accept consent.
2. Because the archive's `pyproject.toml` declares `scipy` (not importable now),
   the installer adds it to a `plugin-scipy_analysis` pixi feature + the
   `microdrop-plugins` environment and shows a **Relaunch required** dialog.
3. Click **Yes** to relaunch into `microdrop-plugins` (scipy now importable), or
   **No** to defer until the next launch.
4. After the relaunch, **Tools → Manage Plugins…**, tick **Scipy Random
   Analysis**, and the dock pane mounts. Try different distributions/sizes.

## Files

- `microdrop_plugin.json` — the manifest (one group, one plugin class).
- `pyproject.toml` — declares the `scipy` conda dependency (the only missing one;
  numpy/matplotlib are already in the base env).
- `scipy_analysis/` — the package: `plugin.py` (Envisage `Plugin`, contributes
  the dock pane) and `dock_pane.py` (the scipy analysis + matplotlib plot).
