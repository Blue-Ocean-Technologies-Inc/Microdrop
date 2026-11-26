# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Reactions to the plotted experiments: the ROI table's buttons (pick
an experiment folder to plot, plot the live one alone, copy every
plotted curve), and, on the image viewer's side, keeping the set in its
preferences and showing a clicked experiment in the viewer."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from pyface.api import clipboard
from pyface.qt import QtWidgets
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from microdrop_application.dialogs.pyface_wrapper import YES, confirm, warning

# Local imports.
from ..model import ImageViewerModel
from .imported_experiments_model import (
    ImportedExperimentsModel,
    payloads_as_text,
    payloads_from_text,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _pick_directories(default_path, title):
    """Folders the user picks, several at once; [] on cancel.

    pyface's DirectoryDialog and the native folder picker take a single
    folder, so this is Qt's own dialog with its views switched to
    extended (shift/ctrl) selection."""
    dialog = QtWidgets.QFileDialog(None, title, default_path)
    dialog.setFileMode(QtWidgets.QFileDialog.FileMode.Directory)
    dialog.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setOption(QtWidgets.QFileDialog.Option.ShowDirsOnly, True)

    for view in dialog.findChildren(QtWidgets.QAbstractItemView):
        view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )

    if not dialog.exec():
        return []

    selected = dialog.selectedFiles()

    # With folders picked inside it, the browsed folder itself can come
    # back too; it is not an experiment the user chose.
    if len(selected) > 1:
        browsed = Path(dialog.directory().absolutePath())
        selected = [path for path in selected if Path(path) != browsed]

    return selected


class ImportedExperimentsController(HasTraits):
    """Turns the ROI table's buttons into dialogs, set changes and the
    clipboard."""

    model = Instance(ImportedExperimentsModel)

    @observe("model:import_experiment_button")
    def _pick_experiments(self, event):
        problems = [
            problem
            for directory in _pick_directories(
                self.model.browse_directory(), "Select experiments to plot"
            )
            if (problem := self.model.add_experiment(directory))
        ]

        if problems:
            warning(
                message="\n".join(problems), title="Import experiments", cancel=False
            )

    @observe("model:current_experiment_button")
    def _plot_live_only(self, event):
        self.model.keep_live_only()

    @observe("model:copy_series_button")
    def _copy_series(self, event):
        clipboard.text_data = self.model.series_table_text()
        self.model.analysis.progress_text = "Copied the plotted curves"
        logger.info("Copied the plotted curves, every plotted experiment's")

    @observe("model:delete_roi_request")
    def _delete_rois(self, event):
        """Delete the ROIs a delete cell names — its row's, or every
        selected row's — from every image of their experiments, once
        confirmed: the live ones through the image viewer's undoable
        delete, as one step; every other one from its experiment's saved
        session, for good, one write per experiment."""
        grouped = self.model.rois_by_experiment(event.new)
        rois = [roi for group in grouped.values() for roi in group]
        stored = [
            experiment
            for experiment in grouped
            if experiment is not None and not experiment.live
        ]

        # Gone since the click: deleted another way, or their section left.
        if not rois:
            return

        message, title = self._delete_question(grouped, rois)

        if stored and len(stored) == len(grouped):
            message += (
                " This cannot be undone."
                if len(rois) == 1
                else " They cannot be undone."
            )
        elif stored:
            message += " Some of them cannot be undone."

        if confirm(message=message, title=title) != YES:
            return

        live_ids = [
            roi.roi_id
            for experiment, group in grouped.items()
            if experiment not in stored
            for roi in group
        ]

        if live_ids:
            self.model.analysis.delete_roi_request = live_ids

        for experiment in stored:
            experiment.delete_rois(grouped[experiment])

        logger.info(f"Deleted {len(rois)} ROIs from {len(grouped)} experiments")

    def _delete_question(self, grouped, rois):
        """(message, title) asking to delete ``rois`` (grouped by
        experiment, as rois_by_experiment gives them): one by its name
        and its experiment's label, several by their count."""
        if len(rois) > 1:
            return (
                f"Delete {len(rois)} ROIs from every image of their experiments?",
                "Delete ROIs",
            )

        ((experiment, (roi,)),) = grouped.items()
        label = "this experiment" if experiment is None else experiment.label
        kind = "mask" if roi.is_negative else "ROI"

        return (
            f"Delete {kind} '{roi.name}' from every image of {label}?",
            f"Delete {kind}",
        )


class ImportedExperimentsViewerController(HasTraits):
    """Keeps the plotted experiments in the image viewer's preferences,
    and shows the experiment a section click asks for in the viewer —
    which makes it live."""

    viewer_model = Instance(ImageViewerModel)
    model = Instance(ImportedExperimentsModel)

    @observe("viewer_model, model")
    def _restore(self, event):
        """Both are constructor arguments, assigned one at a time: act
        once the second arrives, whichever it is."""
        if self.viewer_model is None or self.model is None:
            return

        text = self.viewer_model.preferences.plotted_experiments
        self.model.restore(payloads_from_text(text))

    @observe(
        "model:experiments.items, model:experiments:items:[label,align_to_run_start]"
    )
    def _store(self, event):
        """Keep the set, less the experiments read with no measured ROI
        intensities — as add_experiment refuses them — so one shown only
        because it was current does not pile up launch after launch
        (#1072)."""
        if self.viewer_model is None:
            return

        preferences = self.viewer_model.preferences
        text = payloads_as_text(
            [
                experiment.as_payload()
                for experiment in self.model.experiments
                if experiment.live or experiment.loading or experiment.paths
            ]
        )

        if preferences.plotted_experiments != text:
            preferences.plotted_experiments = text

    @observe("model:open_experiment_request")
    def _show_in_viewer(self, event):
        """Pick the experiment in the viewer's own experiment list when
        it is there; else browse its captures folder, as the folder
        button would. The viewer saves the experiment it leaves and
        loads this one's session."""
        folder = Path(event.new)
        viewer = self.viewer_model
        name = next(
            (
                name
                for name, captures in viewer.experiments
                if Path(captures).parent.resolve() == folder.resolve()
            ),
            None,
        )

        if name is not None and name != viewer.selected_experiment:
            viewer.selected_experiment = name

            return

        captures = folder / CAPTURES_DIR_NAME
        viewer.directory = str(captures if captures.is_dir() else folder)
        logger.info(f"Showing {folder} in the image viewer")
