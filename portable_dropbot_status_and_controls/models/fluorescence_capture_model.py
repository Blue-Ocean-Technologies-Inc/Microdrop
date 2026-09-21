# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state for the Fluorescence Capture pane: one row per filter-wheel
position (Capture tick, LED %, exposure, focus), the running capture's
state, and the saved-path results. Trait mutations are safe from any
thread — attach_step/detach_step are called from the message handler's
Dramatiq worker thread; only Qt object creation needs the GUI thread (see
the controller). The attach/detach/step-cell trio is copied from the PMT
capture model (portable_dropbot_status_and_controls/models/pmt_capture_model.py),
keyed by filter_position instead of slot."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from traits.api import (
    Any,
    Bool,
    Button,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Range,
    Str,
)

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FILTER_POSITIONS,
    FLUORESCENCE_DEFAULT_EXPOSURE_MS,
    FLUORESCENCE_DEFAULT_LED_PERCENT,
    FLUORESCENCE_EXPOSURE_MS_BOUNDS,
    FLUORESCENCE_LED_PERCENT_BOUNDS,
    FluorescenceStepCapture,
)
from template_status_and_controls.base_model import BaseStatusModel

# Local imports.
from ..consts import PORTABLE_DROPBOT_IMAGE

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class FluorescenceRow(HasTraits):
    """One filter-wheel position as a table row."""

    #: Filter-wheel position (FILTER_POSITIONS) — the identity of the row.
    filter_position = Int
    #: Manual mode's own tick, unused while a step is attached (see
    #: at_start/at_end below).
    capture = Bool(True, desc="Capture this filter position")
    led_percent = Range(
        *FLUORESCENCE_LED_PERCENT_BOUNDS,
        FLUORESCENCE_DEFAULT_LED_PERCENT,
        desc="Fluorescence LED level, percent of full scale",
    )
    exposure_ms = Range(
        *FLUORESCENCE_EXPOSURE_MS_BOUNDS,
        FLUORESCENCE_DEFAULT_EXPOSURE_MS,
        desc="Camera exposure for this filter position, milliseconds",
    )
    #: True = continuous auto focus; False = the fixed focus_distance below.
    auto_focus = Bool(True, desc="Continuous auto focus")
    focus_distance = Range(
        0.0, 1.0, 0.5, desc="Manual focus distance (QCamera scale, 0.0 near - 1.0 far)"
    )
    #: Attached-step ticks — captured at the step's start / end (or both);
    #: hidden and unused in manual mode.
    at_start = Bool(False, desc="Capture this filter at the step's start")
    at_end = Bool(False, desc="Capture this filter at the step's end")


class FluorescenceResultRow(HasTraits):
    """One saved capture file, for the results table's link column."""

    path = Str
    #: `path`'s file name, for the table; `path` is what open_file uses.
    file = Str
    #: Fired by the File column's link; the controller opens `path`.
    open_file = Event


class PortableDropbotFluorescenceCaptureModel(BaseStatusModel):
    """One row per filter-wheel position, the running capture's state, and
    the saved-path results of the last capture.

    "Pane follows step" (mirrors #601 increment 2 for PMT): selecting a
    protocol step loads its fluorescence_capture cell into the table
    (attach_step); a group or empty selection returns to manual mode
    (detach_step), restoring the table's own state from the snapshot taken
    at the moment it was left.
    """

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- Filter table ---------------------------------------------------
    #: Table rows; list order is capture order.
    rows = List(Instance(FluorescenceRow))
    selected_row = Instance(FluorescenceRow)

    # ---- Attached step (pane follows step) -------------------------------
    #: uuid of the step whose fluorescence_capture cell the table mirrors;
    #: empty in manual mode.
    attached_step_id = Str("", desc="Step the filter table is attached to")
    #: Read-only header line: "Editing step <id>" / "Manual capture".
    attached_label = Str("Manual capture")
    #: True while attach_step/detach_step are applying a loaded cell or the
    #: manual snapshot to the rows — the controller must not echo these
    #: mutations back out as a set-cell publish.
    loading_step = Bool(False)
    #: The step_id/value of the last set-cell the controller pushed, so the
    #: message handler can tell a ROW_SELECTED echo of its own write (skip)
    #: from a genuine external change (reload).
    last_pushed_step_id = Str("")
    last_pushed_value = Any(None)
    #: The table's own state, saved on the first attach and restored on
    #: detach; None until manual mode has been left at least once.
    _manual_snapshot = Any(None)

    # ---- Run state --------------------------------------------------------
    #: True between Start and the backend's done message.
    running = Bool(False)
    status = Str("-", desc="Current stage / last outcome")
    #: Folder the last capture wrote to.
    last_directory = Str("")

    start_button = Button("Start capture")
    abort_button = Button("Abort")

    # ---- Results ------------------------------------------------------
    #: Saved capture paths, newest first — the source of truth.
    results = List(Str)
    #: Display rows derived from results — kept a plain list refreshed by
    #: record_results, not a Property: the TableEditor's item listener on
    #: open_file walks the old value, and a Property's old value is
    #: Undefined (see PmtResultFrame/results in pmt_capture_model.py).
    result_rows = List(Instance(FluorescenceResultRow))

    def _rows_default(self):
        return [
            FluorescenceRow(filter_position=position) for position in FILTER_POSITIONS
        ]

    @staticmethod
    def _parse_step_capture(cell_value):
        """Tolerant parse of a fluorescence_capture cell: missing or invalid
        reads as no capture rather than failing the step load."""
        if not cell_value:
            return None

        try:
            return FluorescenceStepCapture.model_validate(cell_value)
        except ValidationError as error:
            logger.warning(f"Invalid fluorescence_capture cell value, ignored: {error}")
            return None

    @staticmethod
    def _short_step_id(step_id):
        """First 8 characters of a uuid-like id; already-short ids pass
        through unchanged."""
        return step_id[:8] if len(step_id) > 8 else step_id

    def _save_manual_snapshot(self):
        """Capture the table's own state before the first attach, so
        detach_step can restore it exactly."""
        self._manual_snapshot = {
            "rows": [
                {
                    "filter_position": row.filter_position,
                    "capture": row.capture,
                    "led_percent": row.led_percent,
                    "exposure_ms": row.exposure_ms,
                    "auto_focus": row.auto_focus,
                    "focus_distance": row.focus_distance,
                }
                for row in self.rows
            ]
        }

    def attach_step(self, step_id, cell_value, step_label=""):
        """Load a step's fluorescence_capture cell into the table: rows the
        cell names take its settings/ticks and order, positions absent from
        it are unticked and moved after.

        The first attach out of manual mode snapshots the table so
        detach_step can restore it; a step-to-step reattach does not
        overwrite that snapshot.
        """

        if not self.attached_step_id:
            self._save_manual_snapshot()

        parsed = self._parse_step_capture(cell_value)
        by_position = {row.filter_position: row for row in self.rows}

        self.loading_step = True

        try:
            ordered = []
            seen_positions = set()

            for entry in parsed.entries if parsed else []:
                row = by_position.get(entry.filter_position)

                if row is None:
                    logger.warning(
                        f"Step {step_id} fluorescence_capture names filter "
                        f"position {entry.filter_position}, not on the "
                        "wheel; skipped"
                    )
                    continue

                row.led_percent = entry.led_percent
                row.exposure_ms = entry.exposure_ms
                row.auto_focus = entry.focus_distance is None

                if entry.focus_distance is not None:
                    row.focus_distance = entry.focus_distance

                row.at_start = entry.at_start
                row.at_end = entry.at_end
                ordered.append(row)
                seen_positions.add(row.filter_position)

            remaining = [
                row for row in self.rows if row.filter_position not in seen_positions
            ]

            for row in remaining:
                row.at_start = False
                row.at_end = False

            self.rows = ordered + remaining
        finally:
            self.loading_step = False

        self.attached_step_id = step_id
        self.attached_label = (
            f"Editing step {step_label or self._short_step_id(step_id)}"
        )

    def detach_step(self):
        """Return to manual mode, restoring the snapshot taken on the first
        attach (a no-op if the pane is already unattached)."""

        if not self.attached_step_id:
            return

        self.attached_step_id = ""
        self.attached_label = "Manual capture"
        self.last_pushed_step_id = ""
        self.last_pushed_value = None

        self.loading_step = True

        try:
            self._restore_manual_snapshot()
        finally:
            self.loading_step = False

    def _restore_manual_snapshot(self):
        snapshot = self._manual_snapshot
        by_position = {row.filter_position: row for row in self.rows}

        if snapshot is None:
            # Nothing was ever saved (e.g. a step was attached before the
            # operator touched manual mode) — just clear the step ticks.
            for row in self.rows:
                row.at_start = row.at_end = False

            return

        ordered = []
        seen_positions = set()

        for saved in snapshot["rows"]:
            row = by_position.get(saved["filter_position"])

            if row is None:
                continue

            row.capture = saved["capture"]
            row.led_percent = saved["led_percent"]
            row.exposure_ms = saved["exposure_ms"]
            row.auto_focus = saved["auto_focus"]
            row.focus_distance = saved["focus_distance"]
            row.at_start = row.at_end = False
            ordered.append(row)
            seen_positions.add(row.filter_position)

        remaining = [
            row for row in self.rows if row.filter_position not in seen_positions
        ]

        for row in remaining:
            row.at_start = row.at_end = False

        self.rows = ordered + remaining
        self._manual_snapshot = None

    def step_cell_value(self):
        """The attached rows as a fluorescence_capture cell value (a
        FluorescenceStepCapture dict), or None once nothing is ticked.
        Entries with neither tick are dropped."""
        entries = [
            {
                "filter_position": row.filter_position,
                "led_percent": int(row.led_percent),
                "exposure_ms": float(row.exposure_ms),
                "focus_distance": None if row.auto_focus else float(row.focus_distance),
                "at_start": row.at_start,
                "at_end": row.at_end,
            }
            for row in self.rows
            if row.at_start or row.at_end
        ]

        if not entries:
            return None

        return {"entries": entries}

    def record_pushed_value(self, value):
        """Remember a set-cell value just pushed for the attached step, so
        the message handler's echo suppression can recognize its
        rebroadcast (see last_pushed_step_id/last_pushed_value)."""
        self.last_pushed_step_id = self.attached_step_id
        self.last_pushed_value = value

    def capture_entries(self):
        """The rows to run right now, in table order, as
        FluorescenceCaptureEntry payloads: manual mode's own `capture`
        tick, or — while attached — every row ticked `at_start` or
        `at_end` (a test-run of the step's setup)."""
        if self.attached_step_id:
            rows = [row for row in self.rows if row.at_start or row.at_end]
        else:
            rows = [row for row in self.rows if row.capture]

        return [
            {
                "filter_position": row.filter_position,
                "led_percent": int(row.led_percent),
                "exposure_ms": float(row.exposure_ms),
                "focus_distance": None if row.auto_focus else float(row.focus_distance),
            }
            for row in rows
        ]

    def capture_request(self, request_id="", label=""):
        """Ticked filters as a FluorescenceCaptureRequest payload; an empty
        directory means the current experiment directory."""
        return {
            "entries": self.capture_entries(),
            "request_id": request_id,
            "label": label,
            "directory": "",
        }

    def record_results(self, paths):
        """Prepend a capture's saved paths (newest first — paths arrive in
        capture order) and rebuild the display rows the results table
        renders (open_file needs real HasTraits rows, not plain strings)."""
        self.results = list(reversed(paths)) + self.results
        self.result_rows = [
            FluorescenceResultRow(path=path, file=Path(path).name)
            for path in self.results
        ]
