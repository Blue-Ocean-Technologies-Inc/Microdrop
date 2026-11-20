# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The figure of one plottable self-test, drawn from its received result
by the vendor's own plot code."""

# Enthought library imports.
from traits.api import Bool, Dict, HasTraits, Instance, Property, Str, observe

# Local imports.
from .consts import CALIBRATION_TEST, CHANNELS_TEST, DEFAULT_PLOT_VIEW, PLOT_VIEW_LABELS

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SelfTestPlot(HasTraits):
    """Qt-free figure state: a pyplot-free matplotlib Figure that the view
    puts on a canvas. Each redraw makes a new Figure."""

    #: The vendor test name.
    name = Str()

    #: The tab label.
    title = Str()

    #: The received result (NaN restored) the figure is drawn from.
    result = Dict()

    #: Figure view choices of this test as EnumEditor values; empty when it
    #: has a single figure.
    view_labels = Dict(Str, Str)

    #: The chosen figure view.
    view = Str()

    #: The result carries the data of the alternative views.
    has_views = Property(Bool, observe="result")

    #: The drawn figure; None when the result has none (e.g. an error).
    figure = Instance("matplotlib.figure.Figure")

    #: Why the figure failed to draw.
    plot_error = Str()

    def _view_labels_default(self):
        return PLOT_VIEW_LABELS.get(self.name, {})

    def _view_default(self):
        return next(iter(self.view_labels), DEFAULT_PLOT_VIEW)

    def _get_has_views(self):
        if self.name == CHANNELS_TEST:
            return self.result.get("c_corrected_pf") is not None

        if self.name == CALIBRATION_TEST:
            return bool(self.result.get("matrix"))

        return False

    @observe("result, view")
    def _redraw(self, event):
        if not self.result:
            return

        # Imported here: the vendor module loads its service module on
        # import, which only a drawn result should pay for.
        from dropbot_portable import self_test

        view = self.view if self.has_views else self._view_default()

        try:
            self.figure = self_test.draw_test_figure(self.name, self.result, view=view)

        except Exception as exc:
            # A malformed result must not break the panel: say why instead.
            logger.warning(f"{self.name}: figure failed to draw", exc_info=True)
            self.figure = None
            self.plot_error = f"plot failed: {exc!r}"

            return

        self.plot_error = ""
