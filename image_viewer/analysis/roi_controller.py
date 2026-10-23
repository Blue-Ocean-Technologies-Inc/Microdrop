# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Controller for the ROI analysis: reacts to the analysis toolbuttons
and canvas events, keeps the per-experiment ROI config in sync, and
orchestrates the cache-aware batch computation. All observers run on
the GUI thread; the only off-thread work is inside RoiBatchRunner."""

# Standard library imports.
import math
import queue
import time
from pathlib import Path

# Enthought library imports.
from pyface.api import NO, YES, clipboard
from traits.api import Any, Bool, Dict, Float, HasTraits, Instance, observe

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from microdrop_application.dialogs.pyface_wrapper import choose, confirm

# Local imports.
from ..consts import CAPTURE_TIMESTAMP_FORMAT
from ..device_outline import DeviceOutlineReference, published_device_repo_dir
from ..discovery import capture_timestamp, sanitize_label, utc_stamp
from ..model import ImageViewerModel
from ..scale_bar import area_unit, format_length, pixel_area
from .consts import (
    DEFAULT_ROI_COLORS,
    DELETE_ROI_ALL_IMAGES,
    DELETE_ROI_EARLIER_IMAGES,
    DELETE_ROI_LATER_IMAGES,
    DELETE_ROI_THIS_IMAGE,
    HEATER_LOGS_DIR_NAME,
    HEATER_SENSOR_MEAN,
    NEGATIVE_MASK_COLOR,
    NEGATIVE_MASK_NAME_PREFIX,
    PASTE_OFFSET_PX,
    ROI_ABSENCE_SCOPES,
    ROI_BATCH_PROTOCOL_WORKERS,
    ROI_DELETE_DONT_ASK_TEXT,
    ROI_DELETE_SCOPES,
    STATS_SAVE_DEBOUNCE_S,
)
from .curve_fit import FIT_LABELS, fit_series
from .fit_presets import fit_arguments, load_presets, save_presets
from .heater_loader import HeaterSamplesLoader
from .heater_log import describe_heater_coverage, sensors_in, temperature_at
from .plot_series import analysed_series, calibrated_temperatures, x_quantity
from .protocol_guard import proceed_despite_protocol
from .roi_batch import (
    BATCH_FINISHED,
    BATCH_RESULT,
    INSTANT_RESULT,
    RoiBatchRunner,
    pool_is_warm,
)
from .roi_commands import (
    AddRoisCommand,
    EditRoiCommand,
    HideRoiOnImageCommand,
    MergeRoiOnImageCommand,
    RemoveRoisCommand,
)
from .roi_compute import stats_are_current
from .roi_geometry import translated
from .roi_model import (
    EXPECTED_TRAITS,
    AnalysisSession,
    CustomPoint,
    Roi,
    RoiAnalysisModel,
    RoiStyle,
)
from .roi_store import (
    analysis_directory,
    load_roi_stats,
    load_session,
    save_fit_equations,
    save_roi_stats,
    save_session,
    write_expected_csv,
    write_intensity_csv,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class RoiAnalysisController(HasTraits):
    """Glue between the viewer model (whose ``paths`` IS the filtered
    series), the analysis model, and the batch runner."""

    viewer_model = Instance(ImageViewerModel)
    analysis_model = Instance(RoiAnalysisModel)
    runner = Instance(RoiBatchRunner, ())

    #: Export requested while the cache was incomplete: write the CSV
    #: when the running batch finishes.
    _pending_export = Bool(False)

    #: (path str, roi_id) -> cache key, snapshotted at dispatch time so
    #: drained results land under the geometry they were computed with.
    _dispatched_keys = Dict()

    #: The stats store changed since the last write; flushed by the
    #: dock pane's drain tick after STATS_SAVE_DEBOUNCE_S of quiet.
    _stats_dirty = Bool(False)
    _stats_dirty_since = Float(0.0)

    #: When the running batch started, for the finished-in log line.
    _batch_started = Float(0.0)

    #: What the applied heater samples were read from (their
    #: HeaterSamples.fingerprint), so a load that found no new lines is
    #: not applied again. None forces the next apply.
    _heater_fingerprint = Any()

    #: Tails the heater logs off the GUI thread; drain_results() applies
    #: what it finds.
    _heater_loader = Instance(HeaterSamplesLoader, ())

    #: A drift re-check updated an ROI's geometry since the last save —
    #: flushed by drain_results() once per drain tick rather than once
    #: per tracked frame.
    _ai_config_dirty = Bool(False)

    @property
    def session(self):
        return self.analysis_model.session

    # ------------------------------------------------------------------ #
    # Saved fit equations (app-wide, so they live in preferences rather   #
    # than in any one experiment's config)                                #
    # ------------------------------------------------------------------ #
    @observe("viewer_model, analysis_model")
    def _load_fit_presets(self, event):
        """Both models are constructor arguments, and traits assigns
        them one at a time — so this watches both and acts when the
        second arrives, whichever order the caller passed them in."""
        if self.viewer_model is None or self.analysis_model is None:
            return
        self.analysis_model.fit_presets = load_presets(
            self.viewer_model.preferences.fit_presets
        )

    @observe("analysis_model:fit_presets.items, analysis_model:fit_presets")
    def _store_fit_presets(self, event):
        if self.viewer_model is None:
            return
        preferences = self.viewer_model.preferences
        stored = save_presets(list(self.analysis_model.fit_presets))
        if preferences.fit_presets != stored:
            preferences.fit_presets = stored

    # ------------------------------------------------------------------ #
    # Interaction modes                                                    #
    # ------------------------------------------------------------------ #
    def _arm(self, mode):
        """Arm a drawing tool, or put it away if it is the one already
        armed — its button shows itself pressed, so a second click
        releasing it is what that appearance promises."""
        model = self.analysis_model
        model.interaction_mode = (
            self._rest_mode() if model.interaction_mode == mode else mode
        )

    @observe("analysis_model:draw_ellipse_button")
    def _arm_draw_ellipse(self, event):
        self._arm("draw_ellipse")

    @observe("analysis_model:draw_box_button")
    def _arm_draw_box(self, event):
        self._arm("draw_box")

    @observe("analysis_model:draw_capsule_button")
    def _arm_draw_capsule(self, event):
        self._arm("draw_capsule")

    @observe("analysis_model:draw_polygon_button")
    def _arm_draw_polygon(self, event):
        self._arm("draw_polygon")

    @observe("analysis_model:calibrate_scale_button")
    def _arm_calibrate_scale(self, event):
        self._arm("draw_scale")

    @observe("analysis_model:session, analysis_model:session:scale:metres_per_pixel")
    def _on_scale_changed(self, event):
        """Keep the status-row readout current: the bar alone cannot
        say whether a calibration was measured here or seeded."""
        scale = self.session.scale
        self.viewer_model.scale_text = (
            f"1 px = {format_length(scale.metres_per_pixel)}"
            if scale.calibrated()
            else "Scale: not set"
        )

    @observe("analysis_model:show_background_ring")
    def _on_show_background_ring(self, event):
        if self.session.ring.show_on_canvas != event.new:
            self.session.ring.show_on_canvas = event.new
            self._save_config()

    @observe("analysis_model:rolling_ball_enabled")
    def _on_rolling_ball_toggled(self, event):
        if self.session.ball.enabled != event.new:
            self.session.ball.enabled = event.new
            self._save_config()

    @observe("analysis_model:perspective_enabled")
    def _on_perspective_toggled(self, event):
        if self.session.perspective.enabled != event.new:
            self.session.perspective.enabled = event.new
            self._save_config()

    @observe(
        "analysis_model:session:ring:gap_px, "
        "analysis_model:session:ring:thickness_px, "
        "analysis_model:session:ball:enabled, "
        "analysis_model:session:ball:radius_px, "
        "analysis_model:session:perspective:enabled, "
        "analysis_model:session:perspective:matrix"
    )
    def _on_correction_changed(self, event):
        """A different correction selects a different set of cached stats
        (it is part of every cache key): redraw the plot and table from
        that set — it may already be complete, in which case Calculate
        has nothing to compute and nothing else would bump the revision."""
        self.session.stats_revision += 1

    @observe("analysis_model:session:perspective:matrix")
    def _on_perspective_defined(self, event):
        self.analysis_model.perspective_defined = self.session.perspective.is_defined()

    @observe("analysis_model:define_perspective_button")
    def _on_define_perspective(self, event):
        """Open the definition window on the shown frame; OK stores the
        picked quads (applying them is the toolbar toggle's job)."""
        array = self.viewer_model.array

        if array is None:
            self.analysis_model.progress_text = "Load an image to define a perspective"
            return

        # Qt window, imported lazily so this controller stays Qt-free at
        # import time.
        from ..perspective_dialog import define_perspective

        perspective = self.session.perspective
        quads = define_perspective(
            array,
            perspective.source_quad,
            perspective.target_quad,
            DeviceOutlineReference(
                preferences=self.viewer_model.preferences,
                repo_dir=published_device_repo_dir(),
            ),
        )

        if quads is not None:
            perspective.trait_set(source_quad=quads[0], target_quad=quads[1])
            self._save_config()

    @observe("analysis_model:edit_mode")
    def _toggle_edit_mode(self, event):
        self.analysis_model.interaction_mode = "edit" if event.new else "pan"

    def _rest_mode(self):
        return "edit" if self.analysis_model.edit_mode else "pan"

    # ------------------------------------------------------------------ #
    # Canvas events                                                        #
    # ------------------------------------------------------------------ #
    @observe("analysis_model:canvas_roi_created")
    def _on_canvas_roi_created(self, event):
        # The tool stays armed: drawing a row of ROIs should not mean a
        # trip to the toolbar between each. Escape puts it away.
        kind, geometry = event.new
        self._create_roi(kind, geometry)

    @observe("analysis_model:canvas_draw_cancelled")
    def _on_canvas_draw_cancelled(self, event):
        self.analysis_model.interaction_mode = self._rest_mode()

    def _create_roi(self, kind, geometry, is_negative=None):
        """Add an ROI anchored at the displayed image and start
        measuring it — the one path a drawn or pasted shape takes.

        ``is_negative`` (else the toolbar's negative_mode) makes it a
        negative mask: named "Mask N", drawn in NEGATIVE_MASK_COLOR
        without taking a slot in the ROI colour cycle, and re-measuring
        every ROI it may cut."""
        if is_negative is None:
            is_negative = self.analysis_model.negative_mode

        current = self.viewer_model.current_path
        anchor = capture_timestamp(current) if current else 0.0
        color = (
            NEGATIVE_MASK_COLOR
            if is_negative
            else DEFAULT_ROI_COLORS[
                len(self.session.positive_rois) % len(DEFAULT_ROI_COLORS)
            ]
        )
        roi = Roi(
            name=self.session.next_roi_name(
                NEGATIVE_MASK_NAME_PREFIX if is_negative else "ROI"
            ),
            kind=kind,
            geometry=[float(value) for value in geometry],
            base_anchor=anchor,
            is_negative=is_negative,
            style=RoiStyle(color=color),
        )

        self._push(AddRoisCommand(session=self.session, rois=[roi]))
        self._instant_stats(self._rois_measured_with(roi))

        return roi

    @observe("analysis_model:ai_rois_accepted")
    def _on_ai_rois_accepted(self, event):
        pairs, anchor = event.new
        self._create_rois(pairs, anchor)

    def _create_rois(self, pairs, anchor):
        """Bulk sibling of _create_roi for accepted AI candidates: one
        undo step, one save and one batch restart for the whole set.
        Names and colours count the ROIs built so far, as none is in the
        session until the set lands."""
        session = self.session
        created = []

        for kind, geometry in pairs:
            created.append(
                Roi(
                    name=session.next_roi_name(pending=created),
                    kind=kind,
                    geometry=[float(value) for value in geometry],
                    base_anchor=anchor,
                    style=RoiStyle(
                        color=DEFAULT_ROI_COLORS[
                            (len(session.positive_rois) + len(created))
                            % len(DEFAULT_ROI_COLORS)
                        ]
                    ),
                )
            )

        if not created:
            return created

        self._push(AddRoisCommand(session=session, rois=created))
        self._instant_stats(created)

        return created

    @observe("analysis_model:ai_roi_tracked")
    def _on_ai_roi_tracked(self, event):
        roi_id, capture_time, geometry = event.new
        roi = self.session.roi_by_id(roi_id)
        if roi is not None:
            roi.apply_edit(capture_time, [float(value) for value in geometry])
            self._ai_config_dirty = True

    @observe("analysis_model:canvas_roi_edited")
    def _on_canvas_roi_edited(self, event):
        roi_id, geometry = event.new
        roi = self.session.roi_by_id(roi_id)
        current = self.viewer_model.current_path
        if roi is None or not current:
            return
        self._push(
            EditRoiCommand(
                session=self.session,
                roi=roi,
                capture_time=capture_timestamp(current),
                geometry=[float(value) for value in geometry],
            )
        )
        self._instant_stats(self._rois_measured_with(roi))

    def _rois_measured_with(self, roi):
        """The positive ROIs whose stats change when ``roi`` is drawn,
        edited or removed: ``roi`` itself, or — a negative mask cuts
        whichever ROIs it overlaps — every positive ROI."""
        return self.session.positive_rois if roi.is_negative else [roi]

    @observe("analysis_model:session:rois:items:style:visible")
    def _on_roi_visibility_changed(self, event):
        """A mask's eye decides whether it subtracts (a positive's is
        plot-only), so remeasure as for a mask edit. The toggle also
        selects a different cache set, which toggling back finds
        complete: bump the revision, as nothing else would redraw.
        _on_plot_settings_changed saves the style."""
        roi = next(
            (roi for roi in self.session.negative_rois if roi.style is event.object),
            None,
        )

        if roi is None:
            return

        self.session.stats_revision += 1
        self._restart_batch_if_running()
        self._instant_stats(self._rois_measured_with(roi))

    # ------------------------------------------------------------------ #
    # Copy / paste                                                         #
    # ------------------------------------------------------------------ #
    @observe("analysis_model:copy_roi_button")
    def _copy_roi(self, event):
        """Hold the selected ROI's shape as it stands on the displayed
        image — the shape the user is looking at, which a drift
        override may have moved away from the base geometry."""
        model = self.analysis_model
        roi = self.session.roi_by_id(model.selected_roi_id)
        if roi is None:
            model.progress_text = "Select an ROI first (edit mode) to copy it"
            return
        current = self.viewer_model.current_path
        model.clipboard_kind = roi.kind
        model.clipboard_geometry = roi.effective_geometry(
            capture_timestamp(current) if current else 0.0
        )
        model.clipboard_negative = roi.is_negative
        model.progress_text = f"Copied {roi.name}"

    @observe("analysis_model:paste_roi_button")
    def _paste_roi(self, event):
        """Place a copy, nudged clear of the original so it cannot hide
        under it. It gets its own name and the next colour in the
        cycle: two curves in one colour cannot be told apart. A copied
        negative mask pastes as one, whatever negative_mode says."""
        model = self.analysis_model
        if not model.clipboard_kind:
            model.progress_text = "Nothing copied yet"
            return
        roi = self._create_roi(
            model.clipboard_kind,
            translated(
                model.clipboard_kind,
                model.clipboard_geometry,
                PASTE_OFFSET_PX,
                PASTE_OFFSET_PX,
            ),
            model.clipboard_negative,
        )
        model.selected_roi_id = roi.roi_id
        model.progress_text = f"Pasted {roi.name}"

    # ------------------------------------------------------------------ #
    # Undo / redo                                                          #
    # ------------------------------------------------------------------ #
    def _push(self, command):
        """Make a shape change through the undo stack, then persist it
        and fold it into a running batch."""
        self.analysis_model.undo_stack.push(command)
        self._save_config()
        self._restart_batch_if_running()

    @observe("analysis_model:undo_roi_button")
    def _undo_roi_change(self, event):
        if self.analysis_model.can_undo:
            self._step_history(self.analysis_model.undo_stack.undo)

    @observe("analysis_model:redo_roi_button")
    def _redo_roi_change(self, event):
        if self.analysis_model.can_redo:
            self._step_history(self.analysis_model.undo_stack.redo)

    def _step_history(self, step):
        """Undo or redo one shape change and catch everything up with it.
        The step can land the ROIs back on geometry whose stats are
        cached, which computes nothing, so bump the revision the plot and
        table redraw on; remeasure every positive ROI on the shown image,
        as a step may have moved a mask over any of them."""
        model = self.analysis_model
        step()

        if self.session.roi_by_id(model.selected_roi_id) is None:
            model.selected_roi_id = ""

        self.session.stats_revision += 1
        self._save_config()
        self._restart_batch_if_running()
        self._instant_stats(self.session.positive_rois)

    # ------------------------------------------------------------------ #
    # Delete / clear / reset                                               #
    # ------------------------------------------------------------------ #
    @observe("analysis_model:delete_roi_button")
    def _delete_selected_roi(self, event):
        """Delete the selected ROI from the shown image alone, or from
        every image — asked, or as the preferences remember. With no
        image shown there is only the latter, and nothing to ask."""
        session = self.session
        roi = session.roi_by_id(self.analysis_model.selected_roi_id)

        if roi is None:
            self.analysis_model.progress_text = (
                "Select an ROI first (edit mode) to delete it"
            )
            return

        scope = self._roi_delete_scope(roi) if self.viewer_model.current_path else "all"

        if scope is None:
            return

        if scope in ROI_ABSENCE_SCOPES:
            self._set_absent_on_shown_image(roi, scope, restore=False)
        else:
            self._push(RemoveRoisCommand(session=session, rois=[roi]))

        self.analysis_model.selected_roi_id = ""

        if roi.is_negative:
            self._instant_stats(session.positive_rois)

    def _roi_delete_scope(self, roi):
        """A ROI_DELETE_SCOPES key other than "ask": what the preferences
        remember, else what the dialog is told — None when it is
        cancelled. A ticked "don't ask again" remembers the answer (the
        preferences tab undoes that)."""
        preferences = self.viewer_model.preferences

        if preferences.roi_delete_scope != "ask":
            return preferences.roi_delete_scope

        choice, dont_ask_again = choose(
            message=f"Which images should {roi.name} be deleted from?",
            title="Delete ROI",
            choices=[
                DELETE_ROI_THIS_IMAGE,
                DELETE_ROI_LATER_IMAGES,
                DELETE_ROI_EARLIER_IMAGES,
                DELETE_ROI_ALL_IMAGES,
            ],
            informative="Short of all images, it can be put back with Undo or "
            "the Restore button in the sidebar's exclusion section; later "
            "and earlier include captures still to come.",
            checkbox_text=ROI_DELETE_DONT_ASK_TEXT,
        )

        if choice is None:
            return None

        scope = {label: scope for scope, label in ROI_DELETE_SCOPES.items()}[choice]

        if dont_ask_again:
            preferences.roi_delete_scope = scope

        return scope

    def _set_absent_on_shown_image(self, roi, scope, restore):
        """Take ``roi`` off the shown image — alone, or with every later
        or earlier one by ``scope`` — or undo that, as one undoable
        step."""
        self._push(
            HideRoiOnImageCommand(
                session=self.session,
                roi=roi,
                capture_time=capture_timestamp(self.viewer_model.current_path),
                scope=scope,
                restore=restore,
            )
        )
        # A pair with no stats now (or its old ones again) computes
        # nothing, so nothing else would redraw the plot.
        self.session.stats_revision += 1

    @observe("analysis_model:session:rois:items:name")
    def _merge_renamed_roi(self, event):
        """Renaming a shape drawn on the shown image to the name of an
        ROI deleted from that image alone makes it that ROI's shape
        there: the ROI comes back on the image, keeping its identity,
        and the new shape goes. Every other rename is just a rename."""
        replacement = event.object
        current = self.viewer_model.current_path

        if not current or replacement.is_negative:
            return

        capture_time = capture_timestamp(current)
        roi = next(
            (
                roi
                for roi in self.session.rois
                if roi is not replacement and roi.name == event.new
            ),
            None,
        )

        if roi is None or roi.is_negative or capture_time not in roi.absent_at:
            return

        # Only a shape drawn here and not edited elsewhere: one with a
        # life on other images is an ROI of its own.
        if (
            replacement.base_anchor != capture_time
            or replacement.overrides
            or replacement.local_overrides
        ):
            return

        self._push(
            MergeRoiOnImageCommand(
                session=self.session,
                roi=roi,
                replacement=replacement,
                capture_time=capture_time,
                replacement_name=event.old,
            )
        )

        if self.analysis_model.selected_roi_id == replacement.roi_id:
            self.analysis_model.selected_roi_id = roi.roi_id

        self.analysis_model.progress_text = (
            f"{event.old} replaced {roi.name} on this image"
        )
        self.session.stats_revision += 1
        self._instant_stats([roi])

    @observe("analysis_model:restore_absent_rois_button")
    def _restore_absent_rois(self, event):
        current = self.viewer_model.current_path

        if not current:
            return

        capture_time = capture_timestamp(current)

        # A range is cleared whole: it has no hole for one image.
        for roi in self.session.absent_on(current):
            for scope in roi.absent_by(capture_time):
                self._set_absent_on_shown_image(roi, scope, restore=True)

        self._instant_stats(self.session.positive_rois)

    @observe(
        "analysis_model:current_image_path, analysis_model:session, "
        "analysis_model:session:rois.items, "
        "analysis_model:session:rois:items:absent_at, "
        "analysis_model:session:rois:items:absent_from, "
        "analysis_model:session:rois:items:absent_until"
    )
    def _mirror_absent_roi_count(self, event):
        """Keep the sidebar's count of ROIs deleted from the shown image
        current (a top-level mirror its visible_when can see), and
        whether any of those is a range."""
        current = self.analysis_model.current_image_path
        absent = self.session.absent_on(current) if current else []
        capture_time = capture_timestamp(current) if current else 0.0

        self.viewer_model.trait_set(
            absent_roi_count=len(absent),
            absent_roi_ranged=any(
                set(roi.absent_by(capture_time)) - {"image"} for roi in absent
            ),
        )

    @observe("analysis_model:clear_rois_button")
    def _clear_rois(self, event):
        session = self.session
        if not session.rois:
            return
        if confirm(message="Remove ALL ROIs (and their drift overrides)?") != YES:
            return
        self.runner.cancel()
        self._pending_export = False
        self.analysis_model.undo_stack.push(
            RemoveRoisCommand(
                session=session, rois=list(session.rois), name="Clear ROIs"
            )
        )
        self.analysis_model.selected_roi_id = ""
        self.analysis_model.batch_running = False
        self.analysis_model.progress_text = ""
        self._save_config()

    @observe("analysis_model:reset_expected_button")
    def _reset_expected_values(self, event):
        for roi in self.session.rois:
            roi.trait_set(**{name: math.nan for name in EXPECTED_TRAITS.values()})

    @observe("analysis_model:add_custom_point_button")
    def _add_custom_point(self, event):
        points = self.session.custom_points

        points.append(CustomPoint(name=f"Point {len(points) + 1}"))

    @observe("analysis_model:remove_custom_point_button")
    def _remove_custom_points(self, event):
        selected = {
            point for point, _column in self.analysis_model.selected_custom_cells
        }
        points = self.session.custom_points

        # In place, so the session keeps its list object.
        points[:] = [point for point in points if point not in selected]
        self.analysis_model.selected_custom_cells = []

    @observe("analysis_model:export_expected_button")
    def _export_expected(self, event):
        directory = self._experiment_directory()

        if directory is None:
            self.analysis_model.progress_text = "No experiment folder"
            return

        name = (
            f"roi_fastest_change_"
            f"{sanitize_label(self.viewer_model.selected_burst)}_"
            f"{sanitize_label(self.viewer_model.selected_filter)}_"
            f"{utc_stamp()}.csv"
        )
        csv_path = analysis_directory(directory) / name
        unit = x_quantity(self.session.figure)[1]

        try:
            write_expected_csv(
                csv_path,
                self.analysis_model.expected_rows,
                unit,
                custom_points=self.session.custom_points,
            )
        except Exception as error:
            logger.warning(f"Expected-table export failed: {error}")
            self.analysis_model.progress_text = f"Export failed: {error}"
            return

        self.analysis_model.progress_text = f"Exported {csv_path.name}"
        logger.info(f"ROI fastest changes exported to {csv_path}")

    @observe("analysis_model:copy_trend_expression_button")
    def _copy_trend_expression(self, event):
        if self.analysis_model.copy_trend_blocker:
            return

        clipboard.text_data = self.session.trend.expression
        self.analysis_model.progress_text = "Copied the trend expression"

    @observe("analysis_model:reset_cache_button")
    def _reset_cache(self, event):
        result = confirm(
            message="Reset the calculated ROI intensities?",
            cancel=True,
            yes_label="Cache only",
            no_label="Drift also?",
        )
        if result not in (YES, NO):
            return
        session = self.session
        self.runner.cancel()
        self._pending_export = False
        session.stats = {}
        session.stats_revision += 1
        self._mark_stats_dirty()
        self.flush_stats(force=True)
        self.analysis_model.batch_running = False
        self.analysis_model.progress_text = ""
        if result == NO:
            for roi in session.rois:
                roi.clear_overrides()
            self._save_config()

    # ------------------------------------------------------------------ #
    # Batch orchestration                                                  #
    # ------------------------------------------------------------------ #
    @observe("analysis_model:calculate_button")
    def _calculate(self, event):
        if proceed_despite_protocol(self.analysis_model):
            self._start_batch()

    @observe("analysis_model:export_csv_button")
    def _export(self, event):
        if not self.session.positive_rois or not self.viewer_model.paths:
            self.analysis_model.progress_text = "Nothing to export"
            return

        if not proceed_despite_protocol(self.analysis_model):
            return

        self._dispatched_keys = {}
        work = self._missing_work()
        if work:
            self._pending_export = True
            self.analysis_model.progress_text = "Calculating for export…"
            self._start_batch(work)
            return
        self._write_export()

    @observe(
        "viewer_model:paths.items, viewer_model:selected_filter,"
        " viewer_model:selected_burst"
    )
    def _on_filter_changed(self, event):
        """The filtered series changed mid-batch: restart on the new
        snapshot (the work list is a snapshot by design; the plot pane
        observes the filters itself)."""
        self._restart_batch_if_running()

    @observe("analysis_model:protocol_running")
    def _on_protocol_running_changed(self, event):
        # A batch narrows when a run starts and widens when it ends.
        self._restart_batch_if_running()

    def _missing_work(self):
        """[(path_str, {roi_id: (kind, geometry)}, correction), ...] for
        every filtered image with at least one uncached (image, ROI)
        pair — only the missing positive ROIs are dispatched per image;
        the image's negative masks travel in its correction. A pair
        cached before the shape stats existed counts as missing."""
        session = self.session
        rois = session.positive_rois
        stat_cache = {}
        work = []
        for path in self.viewer_model.paths:
            if session.is_excluded(path):
                continue
            missing = {}
            for roi in rois:
                if not session.measures(path, roi, stat_cache):
                    continue  # deleted from this image alone
                key = session.cache_key(path, roi, stat_cache)
                if not stats_are_current(session.stats.get(key)):
                    missing[roi.roi_id] = (roi.kind, tuple(key[4]))
                    self._dispatched_keys[(str(path), roi.roi_id)] = key
            if missing:
                work.append(
                    (str(path), missing, session.correction_for(path, stat_cache))
                )
        return work

    def _start_batch(self, work=None):
        if not self.session.positive_rois or not self.viewer_model.paths:
            return
        if work is None:
            self._dispatched_keys = {}
            work = self._missing_work()
        self.analysis_model.batch_done = 0
        self.analysis_model.batch_failed = 0
        self.analysis_model.batch_total = len(work)
        if not work:
            self.analysis_model.batch_running = False
            self.analysis_model.progress_text = "ROI stats up to date"
            if self._pending_export:
                self._write_export()
            return
        self.analysis_model.batch_running = True
        gap, width, ball, perspective = self.session.correction_key()
        logger.info(
            f"ROI batch: {len(work)} images x {len(self.session.positive_rois)} "
            f"ROIs, {len(self.session.negative_rois)} negative masks; ring "
            f"gap={gap}px width={width}px; rolling ball="
            f"{f'r={ball}px' if ball else 'off'}; perspective "
            f"{'on' if perspective else 'off'}"
        )
        self._batch_started = time.monotonic()
        if pool_is_warm():
            self._update_progress_text()
        else:
            # First batch of the session: the pool spawns before any
            # image can finish, so say that rather than sit at 0/N.
            self.analysis_model.progress_text = (
                f"Starting workers for {len(work)} images…"
            )
        self.runner.start(
            work,
            ROI_BATCH_PROTOCOL_WORKERS if self.analysis_model.protocol_running else 0,
        )

    def _restart_batch_if_running(self):
        if self.analysis_model.batch_running:
            self._start_batch()

    def drain_results(self):
        """Called by the dock pane's drain QTimer (GUI thread): move
        finished results from the runner's queue into the model.

        The count advances one image at a time, so the readout reads
        1/N, 2/N, 3/N — the editor showing it repaints on each write.
        What stays coalesced is the expensive part: a stats_revision
        bump redraws the plot, refitting every ROI, and doing that per
        result starved the GUI that has to paint the progress."""
        heater = self._heater_loader.latest_result()

        if heater is not None:
            self._apply_heater_samples(heater)

        absorbed = False
        finished = False
        while True:
            try:
                kind, payload = self.runner.results.get_nowait()
            except queue.Empty:
                break
            if kind == BATCH_RESULT:
                absorbed = self._absorb(payload) or absorbed
                self.analysis_model.batch_done += 1
                if payload["error"]:
                    self.analysis_model.batch_failed += 1
                    logger.warning(
                        f"ROI stats failed for {payload['path']}: {payload['error']}"
                    )
                self._update_progress_text()
            elif kind == INSTANT_RESULT:
                absorbed = self._absorb(payload) or absorbed
            elif kind == BATCH_FINISHED:
                finished = True
        if absorbed:
            self.session.stats_revision += 1
            self._mark_stats_dirty()
        if finished:
            self.analysis_model.batch_running = False
            elapsed = time.monotonic() - (self._batch_started or time.monotonic())
            logger.info(
                f"ROI batch finished: {self.analysis_model.batch_done} "
                f"done, {self.analysis_model.batch_failed} failed, in "
                f"{elapsed:.1f}s"
            )
            self._update_progress_text(finished=True)
            self.flush_stats(force=True)
            if self._pending_export:
                self._write_export()
        if self._ai_config_dirty:
            self._ai_config_dirty = False
            self._save_config()

    def _absorb(self, payload):
        """True when anything landed — the caller bumps the revision
        once per drain instead of once per result."""
        absorbed = False
        for roi_id, stats in payload["stats"].items():
            key = self._dispatched_keys.get((payload["path"], roi_id))
            if key is not None:
                self.session.stats[key] = stats
                absorbed = True
        return absorbed

    def _update_progress_text(self, finished=False):
        model = self.analysis_model
        failed = f", {model.batch_failed} failed" if model.batch_failed else ""
        state = "done" if finished else "calculating"
        model.progress_text = (
            f"ROI stats {model.batch_done}/{model.batch_total} {state}{failed}"
        )

    def _instant_stats(self, rois):
        """Kick off one instant single-image compute for the positive
        ``rois`` on the shown image; already-cached stats need no
        compute — the table reads the session cache directly."""
        session = self.session
        current = self.viewer_model.current_path

        if not current or session.is_excluded(current):
            return

        stat_cache = {}
        missing = {}

        for roi in rois:
            # Deleted from this image alone: nothing to measure.
            if not session.measures(current, roi, stat_cache):
                continue

            key = session.cache_key(current, roi, stat_cache)
            self._dispatched_keys[(current, roi.roi_id)] = key

            if not stats_are_current(session.stats.get(key)):
                missing[roi.roi_id] = (roi.kind, tuple(key[4]))

        if missing:
            self.runner.compute_single(
                current, missing, session.correction_for(current, stat_cache)
            )

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #
    def _experiment_directory(self):
        """The folder analysis outputs belong to: the experiment folder
        when browsing its captures dir, else the browsed folder itself.
        None when nothing is resolved yet."""
        browsed = self.viewer_model.browsed_directory
        if not browsed:
            return None
        folder = Path(browsed)
        return folder.parent if folder.name == CAPTURES_DIR_NAME else folder

    def _save_config(self):
        directory = self._experiment_directory()
        if directory is None:
            return
        try:
            save_session(directory, self.session)
        except Exception as error:
            logger.warning(f"Could not save ROI config: {error}")

    def _mark_stats_dirty(self):
        self._stats_dirty_since = time.monotonic()
        self._stats_dirty = True

    def flush_stats(self, force=False):
        """Write the stats store if it changed — debounced (waits
        STATS_SAVE_DEBOUNCE_S seconds of quiet since the last change
        before writing) unless ``force``d (batch finish, session swap,
        reset)."""
        if not self._stats_dirty:
            return
        if not force and (
            time.monotonic() - self._stats_dirty_since < STATS_SAVE_DEBOUNCE_S
        ):
            return
        directory = self.session.directory
        if not directory:
            self._stats_dirty = False
            return
        try:
            save_roi_stats(directory, self.session.stats)
            self._stats_dirty = False
        except Exception as error:
            logger.warning(f"Could not save ROI stats: {error}")

    @observe("viewer_model:browsed_directory")
    def _on_experiment_changed(self, event):
        """A different folder is being browsed: swap in its saved
        session wholesale (ROIs, styles, figure settings), persisting
        the outgoing experiment's stats first."""
        self.runner.cancel()
        self._pending_export = False
        self.flush_stats(force=True)
        self.analysis_model.batch_running = False
        self.analysis_model.progress_text = ""
        self.analysis_model.selected_roi_id = ""
        directory = self._experiment_directory()
        session = (
            load_session(directory) if directory is not None else AnalysisSession()
        )
        if directory is not None:
            session.stats = load_roi_stats(directory)
            session.stats_revision += 1
        preferences = self.viewer_model.preferences
        seed = preferences.last_scale_metres_per_px
        if not session.scale.calibrated() and seed > 0:
            # Seed from the last calibration and write it straight into
            # this experiment, so its record states what it was measured
            # with instead of drifting with later calibrations.
            session.scale.trait_set(
                metres_per_pixel=seed, unit=preferences.last_scale_unit
            )
            if directory is not None:
                try:
                    save_session(directory, session)
                except Exception as error:
                    logger.warning(f"Could not seed the scale: {error}")
        if directory is not None and not session.heater_log_dir:
            # Before the model swap, so its observers see the resolved
            # default rather than a change from it.
            session.heater_log_dir = str(Path(directory) / HEATER_LOGS_DIR_NAME)
        self.analysis_model.session = session
        self.analysis_model.show_background_ring = session.ring.show_on_canvas
        self.analysis_model.rolling_ball_enabled = session.ball.enabled
        self.analysis_model.perspective_enabled = session.perspective.enabled
        self.analysis_model.perspective_defined = session.perspective.is_defined()
        self._dispatched_keys = {}
        self._heater_loader.reset()
        self._heater_fingerprint = None
        self._ensure_heater_samples()

    @observe(
        "analysis_model:session:plot_stat, "
        "analysis_model:session:figure:export_format, "
        "analysis_model:session:figure:export_dpi, "
        "analysis_model:session:figure:x_auto, "
        "analysis_model:session:figure:x_min, "
        "analysis_model:session:figure:x_max, "
        "analysis_model:session:figure:y_auto, "
        "analysis_model:session:figure:y_min, "
        "analysis_model:session:figure:y_max, "
        "analysis_model:session:figure:fit_method, "
        "analysis_model:session:figure:custom_expression, "
        "analysis_model:session:figure:trim_poor_fit, "
        "analysis_model:session:figure:show_legend, "
        "analysis_model:session:figure:show_fit_equations, "
        "analysis_model:session:figure:show_second_derivative_max, "
        "analysis_model:session:figure:show_second_derivative_min, "
        "analysis_model:session:figure:show_second_derivative_zero, "
        "analysis_model:session:figure:second_derivative_vline, "
        "analysis_model:session:figure:second_derivative_hline, "
        "analysis_model:session:figure:second_derivative_coords, "
        "analysis_model:session:figure:view_mode, "
        "analysis_model:session:figure:flip_actual_expected, "
        "analysis_model:session:figure:compare_second_derivative_max, "
        "analysis_model:session:figure:compare_second_derivative_min, "
        "analysis_model:session:figure:trend_method, "
        "analysis_model:session:figure:log_x, "
        "analysis_model:session:figure:log_y, "
        "analysis_model:session:figure:normalize, "
        "analysis_model:session:figure:subtract_first, "
        "analysis_model:session:figure:subtract_background_ref, "
        "analysis_model:session:figure:remove_outliers, "
        "analysis_model:session:figure:outlier_threshold, "
        "analysis_model:session:figure:outlier_window, "
        "analysis_model:session:figure:smooth_method, "
        "analysis_model:session:figure:savgol_window, "
        "analysis_model:session:figure:savgol_order, "
        "analysis_model:session:figure:butter_order, "
        "analysis_model:session:figure:butter_cutoff, "
        "analysis_model:session:figure:interpolate_gaps, "
        "analysis_model:session:figure:show_excluded_points, "
        "analysis_model:session:temperature_style:line_color, "
        "analysis_model:session:temperature_style:line_style, "
        "analysis_model:session:temperature_style:line_width, "
        "analysis_model:session:temperature_style:capture_marker, "
        "analysis_model:session:temperature_style:capture_size, "
        "analysis_model:session:temperature_style:capture_color_follows_line, "
        "analysis_model:session:temperature_style:capture_color, "
        "analysis_model:session:temperature_style:excluded_size, "
        "analysis_model:session:temperature_style:line_alpha, "
        "analysis_model:session:temperature_style:capture_alpha, "
        "analysis_model:session:temperature_style:excluded_alpha, "
        "analysis_model:session:temperature_style:show_legend, "
        "analysis_model:session:temperature_style:shown_sensors.items, "
        "analysis_model:session:temperature_style:sensors:items:visible, "
        "analysis_model:session:temperature_style:sensors:items:color, "
        "analysis_model:session:temperature_style:sensors:items:line_style, "
        "analysis_model:session:temperature_style:sensors:items:line_width, "
        "analysis_model:session:temperature_style:sensors:items:alpha, "
        "analysis_model:session:temperature_style:sensors.items, "
        "analysis_model:session:figure:x_axis, "
        "analysis_model:session:figure:time_unit, "
        "analysis_model:session:figure:heater_sensor, "
        "analysis_model:session:figure:heater_window_ms, "
        "analysis_model:session:figure:temperature_expression, "
        "analysis_model:session:heater_log_dir, "
        "analysis_model:session:figure:show_method_group, "
        "analysis_model:session:figure:show_metrics_group, "
        "analysis_model:session:figure:show_custom_points_group, "
        "analysis_model:session:rois:items:name, "
        "analysis_model:session:rois:items:is_background_ref, "
        "analysis_model:session:rois:items:expected_fastest_change, "
        "analysis_model:session:rois:items:expected_second_derivative_max, "
        "analysis_model:session:rois:items:expected_second_derivative_min, "
        "analysis_model:session:custom_points.items, "
        "analysis_model:session:custom_points:items:name, "
        "analysis_model:session:custom_points:items:actual, "
        "analysis_model:session:custom_points:items:expected, "
        "analysis_model:session:rois:items:style:color, "
        "analysis_model:session:rois:items:style:line_style, "
        "analysis_model:session:rois:items:style:marker, "
        "analysis_model:session:rois:items:style:marker_size, "
        "analysis_model:session:rois:items:style:visible, "
        "analysis_model:session:rois:items:style:alpha, "
        "analysis_model:session:scale:metres_per_pixel, "
        "analysis_model:session:scale:value, "
        "analysis_model:session:scale:unit, "
        "analysis_model:session:ring:gap_px, "
        "analysis_model:session:ring:thickness_px, "
        "analysis_model:session:ring:show_on_canvas, "
        "analysis_model:session:ball:enabled, "
        "analysis_model:session:ball:radius_px, "
        "analysis_model:session:perspective:enabled"
    )
    def _on_plot_settings_changed(self, event):
        self._save_config()

    # ------------------------------------------------------------------ #
    # Heater log (temperature x-axis)                                     #
    # ------------------------------------------------------------------ #
    @observe(
        "analysis_model:session:heater_log_dir, analysis_model:session:figure:x_axis"
    )
    def _on_heater_settings_changed(self, event):
        # Other logs, or a fresh look for a sibling's: tail from scratch.
        self._heater_loader.reset()
        self._heater_fingerprint = None
        self._ensure_heater_samples()

    @observe("analysis_model:plot_visible, analysis_model:session:figure:view_mode")
    def _on_heater_demand_changed(self, event):
        self._ensure_heater_samples()

    def _heater_samples_wanted(self):
        """Only a shown plot on the temperature axis, or showing the
        Temperature over time view, reads the samples (the CSV export
        loads its own), so nothing else pays for them."""
        figure = self.session.figure

        return self.analysis_model.plot_visible and (
            figure.x_axis == "temperature" or figure.view_mode == "temperature"
        )

    def _has_heater_inputs(self):
        """A folder to read and captures to join it to."""
        return bool(self.session.heater_log_dir and self.viewer_model.paths)

    def _clear_heater_samples(self):
        session = self.session

        self._heater_loader.cancel()
        self._heater_fingerprint = None
        session.heater_log_fallback_dir = ""
        session.heater_log_coverage = ""

        if session.heater_samples:
            session.heater_samples = []

    def _heater_request(self):
        """(folder, experiment directory, start, end) — the loader's
        arguments for the current capture range."""
        session = self.session
        stat_cache = {}
        times = [
            session.stat_info(path, stat_cache)[1] for path in self.viewer_model.paths
        ]

        return (
            session.heater_log_dir,
            self._experiment_directory(),
            min(times),
            max(times),
        )

    def _ensure_heater_samples(self):
        """Have the loader tail the heater logs for the current capture
        range, when the plot needs them; the result lands through
        drain_results(). Without a folder or captures there is nothing
        to join, and what was loaded is cleared."""
        if not self._has_heater_inputs():
            self._clear_heater_samples()
            return

        if self._heater_samples_wanted():
            self._heater_loader.request(*self._heater_request())

    def _load_heater_samples_now(self):
        """The export's load: synchronous, and whatever axis is shown —
        the CSV carries each frame's temperature whenever a log covers
        it."""
        if not self._has_heater_inputs():
            self._clear_heater_samples()
            return

        self._apply_heater_samples(
            self._heater_loader.load_now(*self._heater_request())
        )

    def _apply_heater_samples(self, result):
        """Publish a load's HeaterSamples to the session (GUI thread)."""
        if result.fingerprint == self._heater_fingerprint:
            return

        session = self.session

        if result.fallback:
            logger.info(
                f"Heater log: nothing in {result.folder} covers the captures; "
                f"using {result.fallback} (most overlap of {result.match_count} "
                f"sibling match(es))"
            )

        self._heater_fingerprint = result.fingerprint
        # Reported, never written to heater_log_dir: only an explicit
        # pick is persisted as the experiment's heater folder.
        session.heater_log_fallback_dir = result.fallback
        session.heater_log_coverage = describe_heater_coverage(
            result.folder,
            result.span,
            result.capture_span,
            result.fallback,
            result.match_count,
        )
        session.heater_samples = result.samples
        sensors = sensors_in(result.samples)
        self.analysis_model.heater_sensor_choices = [HEATER_SENSOR_MEAN] + sensors
        # A row per sensor the log carries, new ones styled by default.
        session.temperature_style.show_sensors(sensors)
        logger.info(
            f"Heater log: {len(result.samples)} samples from "
            f"{result.fallback or result.folder}"
        )

    @observe("viewer_model:paths.items")
    def _mirror_filtered_paths(self, event):
        self.analysis_model.filtered_paths = [
            str(path) for path in self.viewer_model.paths
        ]
        # The capture range the heater join covers just changed.
        self._ensure_heater_samples()

    @observe("viewer_model:current_path")
    def _mirror_current_image(self, event):
        self.analysis_model.current_image_path = self.viewer_model.current_path

    # ------------------------------------------------------------------ #
    # Exclude-from-analysis (sidebar checkbox <-> session)                 #
    # ------------------------------------------------------------------ #
    #: Guards the checkbox observer while the mirror below writes it.
    _syncing_excluded = Bool(False)

    @observe(
        "analysis_model:current_image_path, analysis_model:session, "
        "analysis_model:session:excluded_images"
    )
    def _mirror_current_image_excluded(self, event):
        """Point the checkbox at the displayed image's exclusion state
        (image navigation, session swaps and bulk changes to the
        marks all land here)."""
        current = self.analysis_model.current_image_path
        self._syncing_excluded = True
        try:
            self.analysis_model.current_image_excluded = bool(
                current
            ) and self.session.is_excluded(current)
        finally:
            self._syncing_excluded = False

    @observe("analysis_model:current_image_excluded")
    def _on_current_image_excluded(self, event):
        """The checkbox was toggled by the user: mark/unmark the
        displayed image and re-run whatever is consuming the series."""
        if self._syncing_excluded:
            return
        current = self.analysis_model.current_image_path
        if not current:
            return
        name = Path(current).name
        excluded = list(self.session.excluded_images)
        if event.new and name not in excluded:
            self.session.excluded_images = excluded + [name]
        elif not event.new and name in excluded:
            self.session.excluded_images = [
                entry for entry in excluded if entry != name
            ]
        else:
            return
        # The plot derives its series from the (now different) included
        # set; stats_revision is what it redraws on.
        self.session.stats_revision += 1
        self._save_config()
        self._restart_batch_if_running()

    @observe("analysis_model:toggle_exclusion_request")
    def _toggle_requested_exclusion(self, event):
        """A plot point was clicked: show its image, then flip that
        image's exclusion through the checkbox — the one path that
        marks, saves and re-runs — so the sidebar shows what changed."""
        path = event.new
        self.viewer_model.current_path = path

        # The mirrors above point the checkbox at the shown image; one
        # that is not the clicked one must not be toggled instead.
        if self.analysis_model.current_image_path != path:
            logger.warning(f"Cannot show {path} to toggle its exclusion")
            return

        self.analysis_model.current_image_excluded = (
            not self.analysis_model.current_image_excluded
        )

    @observe("analysis_model:exclude_before_button")
    def _exclude_all_before(self, event):
        self._set_excluded_relative(before=True, excluded=True)

    @observe("analysis_model:exclude_after_button")
    def _exclude_all_after(self, event):
        self._set_excluded_relative(before=False, excluded=True)

    @observe("analysis_model:include_before_button")
    def _include_all_before(self, event):
        self._set_excluded_relative(before=True, excluded=False)

    @observe("analysis_model:include_after_button")
    def _include_all_after(self, event):
        self._set_excluded_relative(before=False, excluded=False)

    @observe("analysis_model:include_all_button")
    def _include_every_image(self, event):
        if self.session.excluded_images:
            self._set_excluded_images([])

    def _set_excluded_relative(self, before, excluded):
        """Mark or unmark every image before/after the displayed one
        (exclusive) as excluded — the checkbox applied in bulk."""
        current = self.analysis_model.current_image_path
        paths = [str(path) for path in self.viewer_model.paths]
        if current not in paths:
            return
        index = paths.index(current)
        marked = paths[:index] if before else paths[index + 1 :]
        names = [Path(path).name for path in marked]
        current_marks = list(self.session.excluded_images)
        if excluded:
            added = [name for name in names if name not in current_marks]
            if not added:
                return
            self._set_excluded_images(current_marks + added)
        else:
            kept = [name for name in current_marks if name not in names]
            if len(kept) == len(current_marks):
                return
            self._set_excluded_images(kept)

    def _set_excluded_images(self, names):
        """Replace the exclusion marks with ``names`` and re-run what
        consumes the series — the bulk buttons' one write path."""
        self.session.excluded_images = names
        # The plot derives its series from the (now different)
        # included set; stats_revision is what it redraws on.
        self.session.stats_revision += 1
        self._save_config()
        self._restart_batch_if_running()

    def _write_export(self):
        self._pending_export = False
        directory = self._experiment_directory()
        if directory is None:
            self.analysis_model.progress_text = "No experiment folder"
            return
        session = self.session
        paths = [
            path for path in self.viewer_model.paths if not session.is_excluded(path)
        ]
        stat_cache = {}
        times = [session.stat_info(path, stat_cache)[1] for path in paths]
        start_time = times[0] if times else 0.0
        self._load_heater_samples_now()

        if session.heater_samples:
            temperatures, _uninvertible = calibrated_temperatures(
                session.figure,
                temperature_at(
                    session.heater_samples,
                    session.figure.heater_sensor,
                    times,
                    session.figure.heater_window_ms / 1000.0,
                ),
            )
        else:
            temperatures = [math.nan] * len(times)

        rows = []
        for path, capture_time, temperature in zip(paths, times, temperatures):
            stats_by_roi = {}
            for roi in session.positive_rois:
                stats = session.stats.get(session.cache_key(path, roi, stat_cache))
                if stats is not None:
                    stats_by_roi[roi.roi_id] = stats
            rows.append(
                {
                    "filename": Path(path).name,
                    "time_utc": time.strftime(
                        CAPTURE_TIMESTAMP_FORMAT, time.gmtime(capture_time)
                    ),
                    "elapsed_sec": capture_time - start_time,
                    "temperature_c": temperature,
                    "capture_session": self.viewer_model.session_of(path),
                    "filter": self.viewer_model.filter_value(path),
                    "stats": stats_by_roi,
                }
            )
        name = (
            f"roi_intensities_"
            f"{sanitize_label(self.viewer_model.selected_burst)}_"
            f"{sanitize_label(self.viewer_model.selected_filter)}_"
            f"{utc_stamp()}.csv"
        )
        csv_path = analysis_directory(directory) / name
        fitted, outlier_flags = self._analysed_series()
        self._write_fit_equations(directory, fitted)
        scale = session.scale
        try:
            write_intensity_csv(
                csv_path,
                rows,
                session.positive_rois,
                pixel_area(scale.metres_per_pixel, scale.unit),
                area_unit(scale.metres_per_pixel, scale.unit),
                session.plot_stat if session.figure.normalize else None,
                session.correction_key(),
                outlier_flags,
                session.figure.heater_sensor if session.heater_samples else "",
                self.viewer_model.filter_label.lower() or "filter",
            )
        except Exception as error:
            logger.warning(f"CSV export failed: {error}")
            self.analysis_model.progress_text = f"Export failed: {error}"
            return
        self.analysis_model.progress_text = f"Exported {csv_path.name}"
        logger.info(f"ROI intensities exported to {csv_path}")

    def _analysed_series(self):
        """(series, outlier flags) for the export: the same pipeline
        the plot fits, less the visibility filter — a hidden ROI is a
        display choice, and the CSV has always carried them all."""
        return analysed_series(
            self.session, self.analysis_model.filtered_paths, visible_only=False
        )

    def _write_fit_equations(self, directory, series):
        """Record the fitted parameters beside the CSV, keyed by the
        equation — the numbers behind the curves the export describes,
        which the CSV itself has no column for. ``series`` is the
        analysed one, so these are the fits the plot drew."""
        session = self.session
        method, expression = fit_arguments(
            session.figure, self.analysis_model.fit_presets
        )
        if method == "none":
            return
        fits = {}
        for roi_id, (name, elapsed, values) in series.items():
            fit = fit_series(
                elapsed,
                values,
                method,
                session.figure.trim_poor_fit,
                expression,
                session.figure.initial_guesses,
            )
            if fit is None:
                continue
            finite = [time for time, value in zip(elapsed, values) if value == value]
            series_end = max(finite) if finite else fit.fitted_end
            fits[name] = {
                "params": fit.params,
                "r_squared": fit.r_squared,
                # The span actually solved on, and whether that is
                # short of the data — a parameter set from a trimmed
                # fit describes only that stretch, and read without
                # this it looks like it describes the whole series.
                "fitted_range_sec": [fit.fitted_start, fit.fitted_end],
                "trimmed": bool(fit.fitted_end < series_end),
            }
        try:
            equation = expression or FIT_LABELS.get(method, method)
            save_fit_equations(directory, equation, fits)
            logger.info(
                f"Fitted {len(fits)} ROIs to {equation!r} "
                f"(trim={session.figure.trim_poor_fit})"
            )
        except Exception as error:
            logger.warning(f"Could not write fit equations: {error}")
