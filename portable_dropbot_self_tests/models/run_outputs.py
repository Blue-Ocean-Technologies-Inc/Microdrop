# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What a run produced on the frontend: the received results, the report
regenerated from them, its saved copy, and the figures."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import Dict, HasTraits, Instance, List, Str

# Microdrop utils imports.
from microdrop_utils.json_helpers import restore_nan_from_json_nulls

# Local imports.
from .consts import MARKDOWN_REPORT_SUFFIXES
from .plot_model import SelfTestPlot

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

# The vendor module (``dropbot_portable.self_test``) is imported inside the
# methods that need it: it loads its service module on import.


class SelfTestRunOutputs(HasTraits):
    """Qt-free run outputs. Every report is regenerated locally from the
    inline results, so a remote frontend needs no backend files."""

    #: Received results by test name: the vendor dicts, NaN restored.
    results = Dict(Str, Dict)

    #: The Markdown report of ``results``, prepared for a Markdown viewer.
    report_markdown = Str()

    #: Where the last report was saved, or why that failed.
    report_status = Str()

    #: Figures of the plottable tests that have one, in vendor order.
    plots = List(Instance(SelfTestPlot))

    #: The figure tab shown; follows the newest result.
    selected_plot = Instance(SelfTestPlot)

    def clear(self):
        self.results = {}
        self.plots = []
        self.report_markdown = ""
        self.report_status = ""

    def add_result(self, result):
        """Keep a SelfTestResult and update the report and its figure."""
        received = self._received_result(result)
        self.results = {**self.results, result.name: received}

        self._regenerate_report()
        self._show_plot(result.name, result.title, received)

    def mark_saved(self, name, *keys):
        """Set the nested flag ``keys`` of result ``name`` to True (a part
        the backend has since saved to flash) and regenerate the report."""
        target = self.results.get(name)

        for key in keys[:-1]:
            target = target.get(key) if isinstance(target, dict) else None

        if isinstance(target, dict):
            target[keys[-1]] = True
            self._regenerate_report()

    def save_report(self, path):
        """Write the report to ``path``: Markdown (figures beside it) for a
        Markdown suffix, else the self-contained HTML report with one
        raw-data JSON per plottable test beside it."""
        from dropbot_portable import self_test

        target = Path(path)

        try:
            if target.suffix.lower() in MARKDOWN_REPORT_SUFFIXES:
                target = self_test.generate_markdown_report(self.results, target)
                saved = f"{target} (+ figures in {target.stem}_figures/)"

            else:
                target = self_test.generate_html_report(
                    self.results, target, force=True
                )
                saved = str(target)

        except Exception as exc:
            # OSError, or a vendor formatter bug: report it, keep the panel.
            logger.error(f"Saving the self-test report to {target} failed: {exc!r}")
            self.report_status = f"Save FAILED: {exc}"

            return

        self.report_status = f"Saved to {saved}"
        logger.info(f"Self-test report saved to {saved}")

    @staticmethod
    def _received_result(result):
        """The vendor result as the vendor's formatters expect it: NaN
        restored, and the message's error / timing fields folded back in
        where the backend left them out of the dict. The health tests
        record a missing reading as None, never NaN (e.g. a dead sensor in
        test_heaters' ``sensors``), so their nulls stay None."""
        from dropbot_portable import self_test

        received = dict(result.result)

        if result.name not in self_test.HEALTH_TESTS:
            received = restore_nan_from_json_nulls(received)

        message_fields = {
            "error": result.error,
            "cancelled": result.cancelled,
            "restore_errors": result.restore_errors,
            "duration": result.duration,
            "utc_timestamp": result.utc_timestamp,
        }

        for key, value in message_fields.items():
            if value not in (None, "", False, []):
                received.setdefault(key, value)

        return received

    def _regenerate_report(self):
        from dropbot_portable import self_test

        try:
            report = self_test.generate_report(self.results) or ""

        except Exception as exc:
            # A vendor formatter bug must not lose the run: show it instead.
            logger.warning("Self-test report formatting failed", exc_info=True)
            report = f"Report formatting failed: `{exc!r}`"

        self.report_markdown = self_test.report_markdown_for_display(report)

    def _show_plot(self, name, title, result):
        from dropbot_portable import self_test

        if name not in self_test.PLOTTABLE_TESTS:
            return

        plot = next((p for p in self.plots if p.name == name), None)

        if plot is None:
            plot = SelfTestPlot(name=name, title=title)

        plot.result = result
        others = [p for p in self.plots if p is not plot]

        if plot.figure is None and not plot.plot_error:
            self.plots = others

            return

        order = list(self_test.PLOTTABLE_TESTS)
        self.plots = sorted([*others, plot], key=lambda p: order.index(p.name))
        self.selected_plot = plot
