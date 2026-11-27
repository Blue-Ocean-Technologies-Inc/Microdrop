# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The demo's stand-in for the app: a mock rig with live toggles, the
scenarios that set it, and the snapshot taken
from it into a ``PreflightContext`` for one run scope (as the real version
would from the RowManager and the device)."""

# Enthought library imports.
from traits.api import (
    Bool,
    Dict,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Str,
    Tuple,
    Union,
    observe,
)
from traits.observation.api import trait

# Microdrop package imports.
from pluggable_protocol_tree.preflight.controller import PreflightController
from pluggable_protocol_tree.preflight.models import PreflightContext

# Local imports.
from .mock_columns import make_column_handlers

#: The loaded device: a grid of electrodes, numbered row by row.
DEVICE_ROWS = 6
DEVICE_COLUMNS = 10

#: Columns the "Video/Heater unused" toggle empties in every step.
TOGGLED_COLUMNS = ("video", "heater")

#: The steps "Run selected" runs: the first two.
SELECTED_PATHS = [(0,), (1,)]


def device_grid():
    """Electrode ids and each one's orthogonal neighbours."""

    def electrode(row, column):
        return f"E-{row * DEVICE_COLUMNS + column + 1}"

    neighbours = {}

    for row in range(DEVICE_ROWS):
        for column in range(DEVICE_COLUMNS):
            around = [
                (row + d_row, column + d_column)
                for d_row, d_column in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ]
            neighbours[electrode(row, column)] = [
                electrode(*cell)
                for cell in around
                if 0 <= cell[0] < DEVICE_ROWS and 0 <= cell[1] < DEVICE_COLUMNS
            ]

    return list(neighbours), neighbours


class MockRig(HasTraits):
    """The app state: hardware (read by the columns) and the protocol, the
    device and the data folder (read into the snapshot)."""

    #: Instrument.
    dropbot_connected = Bool
    hv_powered = Bool
    chip_inserted = Bool
    max_voltage = Int
    max_frequency = Int

    #: Peripherals.
    camera_present = Bool
    heater_connected = Bool
    magnet_connected = Bool

    #: The device: electrode ids and their neighbours.
    device_electrodes = List(Str)
    electrode_neighbours = Dict(Str, List(Str))

    #: Protocol steps: dicts with electrodes, routes, voltage, frequency,
    #: duration_s, repeats, and a value per column id.
    steps = List(Dict)

    #: Demo toggle: empty the Video and Heater columns in every step.
    toggled_columns_unused = Bool(False)

    #: Data.
    experiment_folder = Str
    folder_writable = Bool
    free_disk_gb = Float

    #: The protocol's columns, reading this rig.
    column_handlers = List

    def _column_handlers_default(self):
        return make_column_handlers(self)


def take_snapshot(rig, run_paths=None, preview_mode=False):
    """A ``PreflightContext`` of ``rig``'s protocol for a run over
    ``run_paths`` (every step when None)."""
    steps = []

    for index, step in enumerate(rig.steps):
        step = {**step, "path": (index,)}

        if rig.toggled_columns_unused:
            step.update(dict.fromkeys(TOGGLED_COLUMNS, False))

        steps.append(step)

    if run_paths is None:
        run_paths = [step["path"] for step in steps]

    context = PreflightContext(steps=steps, run_paths=run_paths)
    hooked = [handler for handler in rig.column_handlers if handler.has_protocol_hooks]

    context.trait_set(
        preview_mode=preview_mode,
        columns={handler.column_id: handler.name for handler in hooked},
        unused_column_ids=[
            handler.column_id for handler in hooked if not handler.is_used(context)
        ],
        device_electrodes=rig.device_electrodes,
        electrode_neighbours=rig.electrode_neighbours,
        experiment_folder=rig.experiment_folder,
        folder_writable=rig.folder_writable,
        free_disk_gb=rig.free_disk_gb,
    )

    return context


class SnapshotBinding(HasTraits):
    """Invalidates the controller's report whenever the rig or the run
    scope changes, as the app's ``PreflightHost`` does on row-manager edits
    and connection changes; ``snapshot`` is the controller's provider."""

    #: The state snapshotted.
    rig = Instance(MockRig)

    #: The controller fed.
    controller = Instance(PreflightController)

    #: The scope of the run the pill reflects: the last one asked for.
    run_paths = Union(None, List(Tuple))
    preview_mode = Bool(False)

    def snapshot(self):
        """A snapshot of the rig for the current scope."""
        return take_snapshot(self.rig, self.run_paths, self.preview_mode)

    @observe(trait("rig").anytrait())
    @observe("controller, run_paths, preview_mode")
    def _resnapshot(self, event):
        if self.rig is not None and self.controller is not None:
            self.controller.invalidate()


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def _step(electrodes=(), route=(), voltage=100, duration_s=20, repeats=1, **more):
    """A protocol step dict with demo values."""
    step = {
        "electrodes": list(electrodes),
        "routes": [list(route)] if route else [],
        "voltage": voltage,
        "frequency": 10000,
        "duration_s": duration_s,
        "repeats": repeats,
        "video": False,
        "heater": False,
        "magnet": False,
    }
    step.update(more)

    return step


def good_protocol():
    """An eight-step sample-prep protocol that passes every check."""
    return [
        _step(["E-1", "E-2"]),
        _step(route=["E-2", "E-3", "E-4", "E-5", "E-6"], duration_s=12),
        _step(["E-6", "E-7"], video=True, repeats=3),
        _step(route=["E-7", "E-8", "E-9", "E-10"], magnet=True),
        _step(["E-10", "E-20", "E-30"], duration_s=60, video=True),
        _step(route=["E-30", "E-29", "E-28"], repeats=4),
        _step(["E-28", "E-38"], video=True, repeats=10),
        _step(["E-38"], duration_s=30, heater=True),
    ]


def _warnings():
    steps = good_protocol()
    steps[3] = _step(magnet=True)
    steps[6] = _step(video=True)

    return {"camera_present": False, "free_disk_gb": 1.4, "steps": steps}


def _blocking():
    steps = good_protocol()
    steps[3] = _step(route=["E-7", "E-8", "E-99", "E-10"], magnet=True)

    return {"dropbot_connected": False, "steps": steps}


def _mixed():
    steps = good_protocol()
    steps[1] = _step(route=["E-2", "E-3", "E-5", "E-6"], duration_s=12)
    steps[4] = _step(["E-10", "E-20"], voltage=180, video=True)
    steps[6] = _step(["E-28", "E-38"], video=True, repeats=200)

    return {"free_disk_gb": 3.2, "steps": steps}


#: Scenario name -> rig overrides on top of the all-good baseline.
SCENARIOS = {
    "All good": dict,
    "Warnings: camera missing + empty steps": _warnings,
    "Blocking: DropBot disconnected + bad electrode": _blocking,
    "Mixed": _mixed,
}


def apply_scenario(rig, name):
    """Reset ``rig`` to the all-good baseline, then apply scenario ``name``."""
    electrodes, neighbours = device_grid()
    baseline = {
        "dropbot_connected": True,
        "hv_powered": True,
        "chip_inserted": True,
        "max_voltage": 150,
        "max_frequency": 20000,
        "camera_present": True,
        "heater_connected": True,
        "magnet_connected": True,
        "toggled_columns_unused": False,
        "experiment_folder": "C:/Experiments/2026-11-26",
        "folder_writable": True,
        "free_disk_gb": 120.0,
        "device_electrodes": electrodes,
        "electrode_neighbours": neighbours,
        "steps": good_protocol(),
    }
    baseline.update(SCENARIOS[name]())

    rig.trait_set(**baseline)
