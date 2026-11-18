# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the experiments the ROI Intensities pane plots: an
ordered set of experiment folders, one of them live — the one the image
viewer shows, whose session is the analysis model's, edited, measured
and saved there — and every other one's saved analysis read from disk
as it stands, never written.

The set is the pane's own, not any experiment's: the viewer controller
keeps it in the image viewer preferences (payloads_as_text), so
switching the viewer's experiment only moves the live mark — the
experiment it shows joins the set, and the one it leaves stays, read
back from disk."""

# Standard library imports.
import json
from pathlib import Path

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Event,
    HasTraits,
    Instance,
    List,
    Property,
    Str,
    observe,
)

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME

# Local imports.
from .consts import HEATER_LOGS_DIR_NAME
from .heater_log import resolve_heater_samples
from .imported_series import (
    imported_key,
    imported_series,
    run_paths,
    series_table,
    split_imported_key,
)
from .plot_series import analysed_series, quantity_label, x_quantity
from .roi_model import AnalysisSession, RoiAnalysisModel, roi_analysis_model
from .roi_store import (
    ROI_STYLE_FIELDS,
    delete_saved_rois,
    load_roi_stats,
    load_session,
    save_roi_styles,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: What the preferences keep of each plotted experiment, in order (see
#: ImportedExperiment.as_payload).
PLOTTED_EXPERIMENT_FIELDS = ("directory", "label", "align_to_run_start")


def _same_folder(first, second):
    """Whether two folder spellings name the same folder."""
    return Path(first).resolve() == Path(second).resolve()


def _style_traits_for(roi, traits):
    """Of the style ``traits``, those ``roi`` takes: all of them, or on a
    mask only its eye, the one style setting a mask has."""
    return {
        name: value
        for name, value in traits.items()
        if name == "visible" or not roi.is_negative
    }


def payloads_as_text(payloads):
    """``payloads`` (as_payload() dicts, in order) as the preferences
    store them."""
    return json.dumps(payloads)


def payloads_from_text(text):
    """The as_payload() dicts the preferences ``text`` holds, in order;
    [] for none or an unreadable value. An unreadable entry is skipped,
    not the rest."""
    try:
        entries = list(json.loads(text)) if text else []
    except Exception as error:
        logger.warning(f"Ignoring unreadable plotted experiments: {error}")

        return []

    payloads = []

    for entry in entries:
        try:
            payload = {
                name: entry[name] for name in PLOTTED_EXPERIMENT_FIELDS if name in entry
            }
            payload["directory"] = str(entry["directory"])
            payloads.append(payload)
        except Exception as error:
            logger.warning(f"Skipping unreadable plotted experiment: {error}")

    return payloads


class ImportedExperiment(HasTraits):
    """One experiment the ROI Intensities pane plots."""

    #: Its folder — the one holding its analysis folder.
    directory = Str()

    #: Its section's title in the ROI table, and what its curves' legend
    #: entries start with while it is not live; the folder's name by
    #: default.
    label = Str()

    #: Plot its run from its own first capture on the elapsed-time
    #: axis; off, on the live run's clock, as captured.
    align_to_run_start = Bool(True)

    #: Whether the image viewer shows it: then ``session`` IS the
    #: analysis model's, and its curves are the plot's own.
    live = Bool(False)

    #: Its analysis. Not live, its saved one, read from disk: its ROIs,
    #: exclusions and calibration change only once it is live, but its
    #: ROIs' styles can be edited and are written back (_save_styles).
    session = Instance(AnalysisSession, ())

    #: Not live, the images of its run the plot reads (see run_paths).
    paths = List(Str)

    #: What was found to plot, "<n> images, <m> ROIs".
    summary = Property(Str, observe="paths.items, session")

    #: Whether any of its ROIs (masks aside) is shown: its section eye.
    any_roi_shown = Property(
        Bool,
        observe=["session.rois.items.is_negative", "session.rois.items.style.visible"],
    )

    #: Fired by its section's remove button: stop plotting it.
    remove = Event()

    #: Set while restyle sets its ROIs' styles one by one, so they are
    #: saved once, after the last.
    _restyling = Bool(False)

    def _label_default(self):
        return Path(self.directory).name

    def _get_any_roi_shown(self):
        return any(roi.style.visible for roi in self.session.positive_rois)

    @observe(f"session:rois:items:style:[{','.join(ROI_STYLE_FIELDS)}]")
    def _save_styles(self, event):
        """Not live, keep a style edit in its own saved session; live,
        the image viewer saves the session itself."""
        if not self.live and not self._restyling:
            save_roi_styles(self.directory, self.session.rois)

    def restyle(self, rois, **traits):
        """Set the style ``traits`` on each of its ``rois`` — on a mask
        only its eye, the one style setting a mask has. Not live, saved
        in one write, after the last; live, the image viewer saves each
        change itself."""
        self._restyling = True

        try:
            for roi in rois:
                roi.style.trait_set(**_style_traits_for(roi, traits))
        finally:
            self._restyling = False

        if not self.live:
            save_roi_styles(self.directory, self.session.rois)

    def toggle_rois_shown(self):
        """Its section eye clicked: hide its ROIs while any is shown,
        else show them all. Masks keep their eyes: a mask's says whether
        it is subtracted, not whether it is drawn."""
        self.restyle(self.session.positive_rois, visible=not self.any_roi_shown)

    def delete_rois(self, rois):
        """Not live, delete its ``rois`` — from every image — from its
        saved session for good, in one write, and from the one read
        here."""
        delete_saved_rois(self.directory, [roi.roi_id for roi in rois])

        for roi in rois:
            self.session.rois.remove(roi)

    def _get_summary(self):
        images = len(self.paths)
        rois = len(self.session.positive_rois)

        return (
            f"{images} {'image' if images == 1 else 'images'}, "
            f"{rois} {'ROI' if rois == 1 else 'ROIs'}"
        )

    def key_of(self, roi):
        """The curve key of its ROI ``roi``: the ROI's id while live,
        else its imported_key."""
        if self.live:
            return roi.roi_id

        return imported_key(self.session.directory, roi.roi_id)

    def roi_of(self, key):
        """Its ROI whose curve ``key`` is, or None."""
        directory, roi_id = split_imported_key(key)

        if directory != ("" if self.live else self.session.directory):
            return None

        return self.session.roi_by_id(roi_id)

    def series(self, primary, primary_paths):
        """Its curves, not live, as the live experiment ``primary``,
        over its ``primary_paths``, plots them (see imported_series)."""
        return imported_series(
            primary,
            primary_paths,
            self.session,
            self.paths,
            self.label,
            self.align_to_run_start,
        )

    def as_payload(self):
        """What the preferences keep of it."""
        return {name: getattr(self, name) for name in PLOTTED_EXPERIMENT_FIELDS}


def load_imported_experiment(directory, **traits):
    """An ImportedExperiment, not live, for the experiment folder
    ``directory``: its saved session and stats store, the images of its
    run, and the heater samples over them, so it plots on the
    temperature axis too. ``traits`` set the rest (label, ...)."""
    session = load_session(directory)
    session.stats = load_roi_stats(directory)
    paths = run_paths(session)

    if paths:
        epochs = [session.stat_info(path)[1] for path in paths]
        folder = session.heater_log_dir or str(Path(directory) / HEATER_LOGS_DIR_NAME)
        session.heater_samples, _fallback, _matches = resolve_heater_samples(
            folder, directory, min(epochs), max(epochs)
        )

    return ImportedExperiment(
        directory=str(directory), session=session, paths=paths, **traits
    )


class ImportedExperimentsModel(HasTraits):
    """The experiments the ROI Intensities pane plots, the analysis
    model's session live among them."""

    #: The analysis whose session is the live experiment.
    analysis = Instance(RoiAnalysisModel)

    #: The plotted experiments, in the order they were added.
    experiments = List(Instance(ImportedExperiment))

    #: The one of them the image viewer shows; None with none shown.
    live_experiment = Property(
        Instance(ImportedExperiment), observe="experiments.items.live"
    )

    #: Pick an experiment folder to plot (the controller opens the
    #: dialog).
    import_experiment_button = Button("Import experiment…")

    #: Plot the live experiment alone again.
    current_experiment_button = Button("Current experiment")

    #: Put every plotted curve on the clipboard.
    copy_series_button = Button("Copy data")

    #: A section was clicked: show that experiment's folder in the image
    #: viewer, which makes it live. # experiment folder (str)
    open_experiment_request = Event()

    #: A row's delete cell was clicked: delete that ROI — or every
    #: selected one, the row among them — from every image of its
    #: experiment, once confirmed (the controller asks). # the ROIs'
    #: curve keys ([str, ...])
    delete_roi_request = Event()

    def _get_live_experiment(self):
        return next(
            (experiment for experiment in self.experiments if experiment.live), None
        )

    @observe("analysis.session")
    def _follow_live(self, event):
        """The viewer swapped experiments: the one it shows goes live —
        where the set lists it, else last — and the one it left is read
        back from disk."""
        self.restore([experiment.as_payload() for experiment in self.experiments])

    @observe("experiments:items:remove")
    def _remove_experiment(self, event):
        self.experiments.remove(event.object)

    def restore(self, payloads):
        """Plot the experiments ``payloads`` (as_payload() dicts) list,
        in order: the analysis session's folder live — listed where it
        is, else last — and every other one read from disk (one already
        read is kept as it is). A folder listed twice, or gone, is left
        out."""
        session = self.analysis.session
        read = {
            experiment.directory: experiment
            for experiment in self.experiments
            if not experiment.live
        }
        experiments = []

        for payload in payloads:
            directory = payload["directory"]

            if any(_same_folder(directory, other.directory) for other in experiments):
                continue

            if session.directory and _same_folder(directory, session.directory):
                experiment = ImportedExperiment(live=True, session=session, **payload)
            elif directory in read:
                experiment = read[directory]
            else:
                experiment = self._experiment_from(payload)

            if experiment is not None:
                experiments.append(experiment)

        if session.directory and not any(other.live for other in experiments):
            experiments.append(
                ImportedExperiment(
                    directory=session.directory, live=True, session=session
                )
            )

        self.experiments = experiments

    def _experiment_from(self, payload):
        """The ImportedExperiment a payload describes, read from disk, or
        None when its folder is gone."""
        if not Path(payload["directory"]).is_dir():
            logger.warning(f"Plotted experiment {payload['directory']} is missing")

            return None

        traits = {name: value for name, value in payload.items() if name != "directory"}

        return load_imported_experiment(payload["directory"], **traits)

    def keep_live_only(self):
        """Plot the live experiment alone again."""
        self.experiments = [
            experiment for experiment in self.experiments if experiment.live
        ]

    def browse_directory(self):
        """Where the experiment picker opens: beside the live
        experiment, "" with none."""
        directory = self.analysis.session.directory

        return str(Path(directory).parent) if directory else ""

    def add_experiment(self, directory):
        """Plot the experiment folder ``directory`` (its captures folder
        stands for it too). Returns "" once added, else why it was
        not."""
        folder = Path(directory)

        if folder.name == CAPTURES_DIR_NAME:
            folder = folder.parent

        if any(_same_folder(folder, other.directory) for other in self.experiments):
            return f"{folder.name} is already plotted."

        experiment = load_imported_experiment(folder)

        if not experiment.paths:
            return (
                f"{folder.name} has no measured ROI intensities to plot. "
                "Open it in the image viewer and Calculate first."
            )

        self.experiments.append(experiment)
        logger.info(f"Plotting {folder} ({experiment.summary})")

        return ""

    def experiment_of(self, key):
        """The experiment, not live, whose curve ``key`` is, or None —
        for a live ROI's id too."""
        directory, _roi_id = split_imported_key(key)

        return next(
            (
                experiment
                for experiment in self.experiments
                if not experiment.live and experiment.session.directory == directory
            ),
            None,
        )

    def rois_by_experiment(self, keys):
        """{experiment: [ROI, ...]} of the ROIs ``keys`` (curve keys)
        name, in their order — the live session's under the live
        experiment, or under None with no experiment shown. A key naming
        no ROI is left out."""
        grouped = {}

        for key in keys:
            roi = self.analysis.session.roi_by_id(key)
            experiment = self.live_experiment

            if roi is None:
                experiment = self.experiment_of(key)
                roi = None if experiment is None else experiment.roi_of(key)

            if roi is not None:
                grouped.setdefault(experiment, []).append(roi)

        return grouped

    def restyle_rois(self, keys, **traits):
        """Set the style ``traits`` on every ROI ``keys`` (curve keys)
        name — on a mask only its eye — each experiment not live saved
        once (ImportedExperiment.restyle)."""
        for experiment, rois in self.rois_by_experiment(keys).items():
            if experiment is None:
                for roi in rois:
                    roi.style.trait_set(**_style_traits_for(roi, traits))
            else:
                experiment.restyle(rois, **traits)

    def roi_of(self, key):
        """The ROI, not live, whose curve ``key`` is, or None."""
        experiment = self.experiment_of(key)

        return None if experiment is None else experiment.roi_of(key)

    def imported_series(self):
        """(series, outlier flags, excluded, area fit) of every plotted
        experiment but the live one, each merged in the set's order and
        keyed by imported_key — see ImportedExperiment.series."""
        session = self.analysis.session
        primary_paths = list(self.analysis.filtered_paths)
        merged = ({}, {}, {}, {})

        for experiment in self.experiments:
            if experiment.live:
                continue

            for whole, part in zip(merged, experiment.series(session, primary_paths)):
                whole.update(part)

        return merged

    def series_table_text(self):
        """The live experiment's shown curves and every other plotted
        one as imported_series.series_table text."""
        session = self.analysis.session
        series, _flags = analysed_series(session, self.analysis.filtered_paths)
        imported, _flags, _excluded, _area_fit = self.imported_series()

        return series_table(
            {**series, **imported}, quantity_label(*x_quantity(session.figure))
        )


#: The experiments the ROI Intensities pane plots beside the shared
#: analysis model's session, listed by the ROI table and drawn by the
#: plot.
imported_experiments_model = ImportedExperimentsModel(analysis=roi_analysis_model)
