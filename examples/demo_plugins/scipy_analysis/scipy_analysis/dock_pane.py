"""A demo dock pane that uses scipy (deliberately NOT in MicroDrop's base
environment) to analyze random data and plot it based on user input.

Pick a distribution and a sample size, click "Generate & Analyze", and the pane
draws fresh random samples, runs a few scipy.stats analyses on them (skewness,
excess kurtosis, a normality test, and a Gaussian KDE), and plots a histogram
with the KDE overlaid via matplotlib.

scipy is imported at module top on purpose: until it is installed (and the app
relaunched into the microdrop-plugins env), enabling this plugin fails cleanly
instead of mounting a broken pane.
"""
from pyface.tasks.dock_pane import DockPane
from pyface.qt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QPushButton,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import numpy as np
from scipy import stats

from logger.logger_service import get_logger
from .consts import PKG, PKG_name

logger = get_logger(__name__)

# Distribution label -> a numpy sampler taking a sample size. Each click draws
# fresh random samples, so the analysis/plot changes every time.
_DISTRIBUTIONS = {
    "Normal": lambda n: np.random.normal(0.0, 1.0, n),
    "Exponential": lambda n: np.random.exponential(1.0, n),
    "Uniform": lambda n: np.random.uniform(-2.0, 2.0, n),
}


class ScipyAnalysisDockPane(DockPane):
    """Dock pane: user picks a distribution + sample size; scipy analyzes."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    def create_contents(self, parent):
        root = QWidget(parent)
        layout = QVBoxLayout(root)

        # --- user input row ---
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Distribution:"))
        self._dist_combo = QComboBox()
        self._dist_combo.addItems(list(_DISTRIBUTIONS))
        controls.addWidget(self._dist_combo)

        controls.addWidget(QLabel("Samples:"))
        self._n_spin = QSpinBox()
        self._n_spin.setRange(50, 50000)
        self._n_spin.setSingleStep(50)
        self._n_spin.setValue(1000)
        controls.addWidget(self._n_spin)

        self._go_btn = QPushButton("Generate && Analyze")
        self._go_btn.clicked.connect(self._run_analysis)
        controls.addWidget(self._go_btn)
        controls.addStretch()
        layout.addLayout(controls)

        # --- results line ---
        self._results = QLabel("Pick a distribution and click Generate && Analyze.")
        self._results.setWordWrap(True)
        layout.addWidget(self._results)

        # --- matplotlib canvas ---
        self._figure = Figure(figsize=(5, 3))
        self._canvas = FigureCanvas(self._figure)
        layout.addWidget(self._canvas)

        self._run_analysis()  # draw something on first mount
        return root

    def _run_analysis(self):
        name = self._dist_combo.currentText()
        n = int(self._n_spin.value())
        data = _DISTRIBUTIONS[name](n)

        # scipy-powered analysis — the part that needs the extra dependency.
        skew = stats.skew(data)
        kurt = stats.kurtosis(data)
        _, normal_p = stats.normaltest(data)
        kde = stats.gaussian_kde(data)

        xs = np.linspace(float(data.min()), float(data.max()), 200)
        density = kde(xs)

        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.hist(data, bins=40, density=True, alpha=0.5, label="samples")
        ax.plot(xs, density, "r-", lw=2, label="scipy gaussian_kde")
        ax.set_title(f"{name}  (n={n})")
        ax.legend(loc="best")
        self._figure.tight_layout()
        self._canvas.draw_idle()

        verdict = "looks normal" if normal_p > 0.05 else "not normal"
        self._results.setText(
            f"<b>{name}</b> sample of {n}: skew={skew:.3f}, "
            f"excess kurtosis={kurt:.3f}, normaltest p={normal_p:.3g} ({verdict}). "
            f"Red curve is a scipy Gaussian KDE of the samples."
        )
        logger.info(
            f"scipy_analysis: {name} n={n} skew={skew:.3f} kurt={kurt:.3f} p={normal_p:.3g}"
        )
