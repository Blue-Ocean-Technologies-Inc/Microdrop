# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI view: the canvas beside a sidebar of path list, slug parameters
and phase controls. Declarative — every Item binds to a model trait."""

# Enthought library imports.
from traitsui.api import (
    CodeEditor,
    CustomEditor,
    EnumEditor,
    HGroup,
    Item,
    ListStrEditor,
    RangeEditor,
    UItem,
    VGroup,
    View,
)

# Microdrop utils imports.
from microdrop_utils.wide_path_geometry import IN_OUT, LEFT_RIGHT

# Local imports.
from .canvas import wide_path_canvas_factory
from .consts import SIDEBAR_WIDTH
from .timeline import timeline_factory

path_list = VGroup(
    UItem(
        "path_names",
        editor=ListStrEditor(selected_index="selected_index", editable=False),
        height=120,
        width=SIDEBAR_WIDTH,
    ),
    HGroup(
        UItem("new_path_button"),
        UItem("delete_path_button", enabled_when="selected is not None"),
        UItem(
            "undo_button", enabled_when="selected is not None and selected.route_ids"
        ),
        UItem("clear_path_button", enabled_when="selected is not None"),
    ),
    HGroup(
        UItem(
            "invert_button", enabled_when="selected is not None and selected.route_ids"
        ),
        UItem(
            "merge_button",
            enabled_when="selected is not None and selected_index < len(paths) - 1",
        ),
    ),
    label="Paths",
    show_border=True,
)

# ``editing`` is the selected path, or a spare instance when nothing is
# selected, so these Items always have something to bind to.
slug_controls = VGroup(
    Item("object.editing.name", label="Name"),
    Item(
        "object.editing.lane_frame",
        label="Lanes",
        editor=EnumEditor(
            values={LEFT_RIGHT: "Left / right", IN_OUT: "In / out of the turn"},
            cols=2,
        ),
        style="custom",
    ),
    HGroup(
        Item(
            "object.editing.left",
            label="Left",
            editor=RangeEditor(low=0, high=5, mode="spinner"),
        ),
        Item(
            "object.editing.right",
            label="Right",
            editor=RangeEditor(low=0, high=5, mode="spinner"),
        ),
        visible_when="editing.lane_frame == 'left/right'",
    ),
    HGroup(
        Item(
            "object.editing.left",
            label="In",
            editor=RangeEditor(low=0, high=5, mode="spinner"),
        ),
        Item(
            "object.editing.right",
            label="Out",
            editor=RangeEditor(low=0, high=5, mode="spinner"),
        ),
        visible_when="editing.lane_frame == 'in/out'",
    ),
    HGroup(
        Item(
            "object.editing.trail_length",
            label="Trail",
            editor=RangeEditor(low=1, high=20, mode="spinner"),
        ),
        Item(
            "object.editing.trail_overlay",
            label="Overlay",
            editor=RangeEditor(low=0, high=19, mode="spinner"),
        ),
    ),
    HGroup(
        Item("object.editing.rotation_lock", label="Rotation lock"),
        Item("object.editing.soft_start", label="Soft start"),
        Item("object.editing.soft_terminate", label="Soft end"),
    ),
    Item(
        "object.editing.repetitions",
        label="Repeats",
        editor=RangeEditor(low=1, high=20, mode="spinner"),
        visible_when="editing.loop",
    ),
    label="Slug",
    show_border=True,
    visible_when="selected is not None",
)

phase_controls = VGroup(
    HGroup(
        UItem("prev_phase_button", enabled_when="step > 0"),
        UItem("phase_label", style="readonly"),
        UItem("next_phase_button", enabled_when="step < max_step"),
    ),
    UItem("step", editor=CustomEditor(timeline_factory)),
    UItem("summary", style="readonly"),
    UItem("status", style="readonly"),
    UItem(
        "frame",
        editor=CodeEditor(show_line_numbers=False, lexer="text"),
        style="readonly",
        height=160,
    ),
    label="Phases",
    show_border=True,
    visible_when="selected is not None",
)

WidePathDemoView = View(
    HGroup(
        UItem(
            "electrode_polygons",
            editor=CustomEditor(wide_path_canvas_factory),
            springy=True,
        ),
        VGroup(UItem("load_svg_button"), path_list, slug_controls, phase_controls),
    ),
    title="Wide Path Spike",
    width=1200,
    height=700,
    resizable=True,
)
