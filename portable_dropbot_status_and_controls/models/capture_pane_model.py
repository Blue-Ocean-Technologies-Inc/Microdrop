# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state shared by the capture panes (PMT Capture, Fluorescence
Capture): a table of capture rows in capture order, the running capture's
state with the row being captured highlighted, "pane follows step"
attach/detach against a protocol-tree cell, and the results paged one
capture run at a time.

A pane subclasses CaptureRow for its rows and CapturePaneModel for the pane,
then fills in the hooks each base names. Row traits tagged ``setting=True``
are the per-row settings a manual snapshot saves and an edit pushes to the
attached step's cell."""

# Standard library imports.
from datetime import datetime

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from traits.api import (
    Any,
    Bool,
    Button,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
    observe,
)

# Microdrop package imports.
from template_status_and_controls.base_model import BaseStatusModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class CaptureRow(HasTraits):
    """One capture target as a table row. Subclasses name their identity
    trait in KEY_NAME and tag their per-row settings ``setting=True``."""

    #: Name of the trait identifying the row (e.g. "slot").
    KEY_NAME = ""

    #: The row the running capture is on; the table highlights it.
    active = Bool(False)
    #: Manual mode's own tick, unused while a step is attached (see
    #: at_start/at_end below).
    capture = Bool(True, desc="Capture this row")
    #: Attached-step ticks — captured at the step's start / end (or both);
    #: hidden and unused in manual mode.
    at_start = Bool(False, desc="Capture at the step's start")
    at_end = Bool(False, desc="Capture at the step's end")
    #: Upper bound of the row's exposure slider, from the pane's exposure
    #: range pick; the exposure itself is never clamped to it.
    exposure_max = Float

    @property
    def key(self):
        return getattr(self, self.KEY_NAME)

    def settings(self):
        """The row's own settings, as saved by a manual snapshot."""
        return self.trait_get(setting=True)

    def capture_entry(self):
        """The row as its pane's capture-request entry."""
        raise NotImplementedError

    def load_step_entry(self, entry):
        """Adopt a parsed step-cell entry's settings (not its ticks)."""
        raise NotImplementedError

    def step_entry(self):
        """The row as a step-cell entry, ticks included."""
        return {
            **self.capture_entry(),
            "at_start": self.at_start,
            "at_end": self.at_end,
        }


class CaptureResultFrame(HasTraits):
    """One capture run's results: a page of the Results table."""

    #: Time the run's results arrived, "HH:MM:SS".
    taken = Str
    #: The done message's label (e.g. "step1.2-end", "manual"), shown after
    #: the time.
    label = Str
    #: The pane's result rows, in capture order; each carries a `path` and
    #: an `open_file` Event for the File link.
    rows = List(Instance(HasTraits))


class CapturePaneModel(BaseStatusModel):
    """Capture rows in capture order, the running capture, the attached
    step, and the results paged per run.

    "Pane follows step": selecting a protocol step loads its cell into the
    table (attach_step); a group or empty selection returns to manual mode
    (detach_step), restoring the table's own state from the snapshot taken
    at the moment it was left.

    Subclasses set the class constants below and declare
    ``exposure_range = Enum(<default>, tuple(EXPOSURE_RANGES))``.
    """

    #: The pane's CaptureRow subclass.
    ROW_CLASS = CaptureRow
    #: Pydantic model of the pane's protocol-tree cell value.
    STEP_CAPTURE_MODEL = None
    #: The cell's column name, for log messages.
    STEP_CELL_NAME = ""
    #: Exposure range label -> the exposure sliders' upper bound.
    EXPOSURE_RANGES = {}

    # ---- Capture table --------------------------------------------------
    #: Table rows; list order is capture order.
    rows = List(Instance(CaptureRow))
    selected_row = Instance(CaptureRow)

    # ---- Attached step (pane follows step) -------------------------------
    #: uuid of the step whose cell the table mirrors; empty in manual mode.
    attached_step_id = Str("", desc="Step the capture table is attached to")
    #: Read-only header line: "Editing step <id>" / "Manual capture".
    attached_label = Str("Manual capture")
    #: The attached step already carries the other capture pane's setup (PMT
    #: and fluorescence are exclusive per step), so this pane's step table
    #: is locked; see step_capture_taken_note.
    step_capture_taken = Bool(False)
    #: Why the step table is locked; each pane names the other capture.
    step_capture_taken_note = Str()
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
    capturing = Bool(False)
    #: Top-level (not nested) so enabled_when reacts to it — TraitsUI's
    #: enabled_when ignores changes nested inside a Property's dependencies.
    #: Panes with more run states widen it.
    busy = Property(Bool, observe="capturing")
    progress = Str("-", desc="Current stage / last outcome")
    results_directory = Str("", desc="Folder the last capture wrote to")

    start_button = Button("Start capture")
    abort_button = Button("Abort")

    # ---- Results ----------------------------------------------------------
    #: Chevron toggle for the Results group.
    show_results = Bool(False)
    #: Every capture run's results since the pane opened, oldest first; the
    #: Results table pages through them one run at a time.
    result_frames = List(Instance(CaptureResultFrame))
    #: Index of the frame on show; -1 before the first capture.
    frame_index = Int(-1)
    #: The shown frame's rows, in capture order. A plain list refreshed by
    #: _show_frame, not a Property: the TableEditor's item listener walks
    #: the old value, and a Property's old value is Undefined.
    results = List(Instance(HasTraits))
    #: "Run 2 / 3 · 14:05:09 · step1.2-end", or a hint before the first
    #: capture.
    frame_label = Property(Str, observe="result_frames.items, frame_index")
    #: Top-level flags so the arrows' enabled_when reacts.
    has_previous_frame = Property(Bool, observe="frame_index")
    has_next_frame = Property(Bool, observe="result_frames.items, frame_index")
    previous_frame_button = Button("Previous run")
    next_frame_button = Button("Next run")

    def _get_busy(self):
        return self.capturing

    # ---- Exposure range -------------------------------------------------

    @observe("exposure_range, rows.items")
    def _apply_exposure_range(self, event):
        exposure_max = self.EXPOSURE_RANGES[self.exposure_range]

        for row in self.rows:
            row.exposure_max = exposure_max

    # ---- Running capture ------------------------------------------------

    def mark_active_row(self, key):
        """Highlight the row being captured; a key no row has clears it."""
        for row in self.rows:
            row.active = row.key == key

    def capture_entries(self):
        """The rows to run right now, in table order, as capture-request
        entries: manual mode's own `capture` tick, or — while attached —
        every row ticked `at_start` or `at_end` (a test-run of the step's
        setup)."""
        if self.attached_step_id:
            rows = [row for row in self.rows if row.at_start or row.at_end]
        else:
            rows = [row for row in self.rows if row.capture]

        return [row.capture_entry() for row in rows]

    # ---- Results ----------------------------------------------------------

    @observe("frame_index, result_frames.items")
    def _show_frame(self, event):
        if 0 <= self.frame_index < len(self.result_frames):
            self.results = self.result_frames[self.frame_index].rows
        else:
            self.results = []

    def _get_frame_label(self):
        if not self.result_frames:
            return "no captures yet"

        frame = self.result_frames[self.frame_index]
        position = f"Run {self.frame_index + 1} / {len(self.result_frames)}"

        return " · ".join(part for part in (position, frame.taken, frame.label) if part)

    def _get_has_previous_frame(self):
        return self.frame_index > 0

    def _get_has_next_frame(self):
        return self.frame_index < len(self.result_frames) - 1

    def append_result_frame(self, rows, label=""):
        """Add a capture run's result rows as a new frame and show it."""
        frame = CaptureResultFrame(
            taken=datetime.now().strftime("%H:%M:%S"),
            label=label,
            rows=rows,
        )
        self.result_frames.append(frame)
        self.frame_index = len(self.result_frames) - 1

    def show_previous_frame(self):
        self.frame_index = max(self.frame_index - 1, 0)

    def show_next_frame(self):
        self.frame_index = min(self.frame_index + 1, len(self.result_frames) - 1)

    # ---- Pane follows step ----------------------------------------------

    def _pane_settings(self):
        """Pane-level settings the step cell carries beside its entries."""
        return {}

    def _load_pane_settings(self, settings):
        """Apply pane-level settings from a snapshot or a parsed cell."""

    def _parse_step_capture(self, cell_value):
        """Tolerant parse of the step's cell: missing or invalid reads as no
        capture rather than failing the step load."""
        if not cell_value:
            return None

        try:
            return self.STEP_CAPTURE_MODEL.model_validate(cell_value)
        except ValidationError as error:
            logger.warning(
                f"Invalid {self.STEP_CELL_NAME} cell value, ignored: {error}"
            )
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
                {"key": row.key, "capture": row.capture, **row.settings()}
                for row in self.rows
            ],
            "pane": self._pane_settings(),
        }

    def _reorder_rows(self, ordered):
        """Put `ordered` first, clearing the step ticks of every other row."""
        placed = {row.key for row in ordered}
        remaining = [row for row in self.rows if row.key not in placed]

        for row in remaining:
            row.at_start = row.at_end = False

        self.rows = ordered + remaining

    def attach_step(self, step_id, cell_value, step_label=""):
        """Load a step's cell into the table: rows the cell names take its
        settings/ticks and order, rows absent from it are unticked and moved
        after. Pane-level settings load too.

        The first attach out of manual mode snapshots the table so
        detach_step can restore it; a step-to-step reattach does not
        overwrite that snapshot.
        """

        if not self.attached_step_id:
            self._save_manual_snapshot()

        parsed = self._parse_step_capture(cell_value)
        key_name = self.ROW_CLASS.KEY_NAME
        by_key = {row.key: row for row in self.rows}

        self.loading_step = True

        try:
            ordered = []

            for entry in parsed.entries if parsed else []:
                key = getattr(entry, key_name)
                row = by_key.get(key)

                if row is None:
                    logger.warning(
                        f"Step {step_id} {self.STEP_CELL_NAME} names "
                        f"{key_name} {key}, not in the table; skipped"
                    )
                    continue

                row.load_step_entry(entry)
                row.at_start = entry.at_start
                row.at_end = entry.at_end
                ordered.append(row)

            self._reorder_rows(ordered)

            if parsed:
                self._load_pane_settings(parsed.model_dump(exclude={"entries"}))
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
        self.step_capture_taken = False
        self.last_pushed_step_id = ""
        self.last_pushed_value = None

        self.loading_step = True

        try:
            self._restore_manual_snapshot()
        finally:
            self.loading_step = False

    def _restore_manual_snapshot(self):
        snapshot = self._manual_snapshot

        if snapshot is None:
            # Nothing was ever saved (e.g. a step was attached before the
            # operator touched manual mode) — just clear the step ticks.
            self._reorder_rows([])

            return

        by_key = {row.key: row for row in self.rows}
        ordered = []

        for saved in snapshot["rows"]:
            row = by_key.get(saved["key"])

            if row is None:
                continue

            settings = {name: value for name, value in saved.items() if name != "key"}
            row.trait_set(**settings)
            ordered.append(row)

        self._reorder_rows(ordered)
        self._load_pane_settings(snapshot["pane"])
        self._manual_snapshot = None

    def step_cell_value(self):
        """The attached rows as a cell value (a STEP_CAPTURE_MODEL dict), or
        None once nothing is ticked. Entries with neither tick are dropped."""
        entries = [row.step_entry() for row in self.rows if row.at_start or row.at_end]

        if not entries:
            return None

        return {**self._pane_settings(), "entries": entries}

    def record_pushed_value(self, value):
        """Remember a set-cell value just pushed for the attached step, so
        the message handler's echo suppression can recognize its
        rebroadcast (see last_pushed_step_id/last_pushed_value)."""
        self.last_pushed_step_id = self.attached_step_id
        self.last_pushed_value = value
