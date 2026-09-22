# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The testbed's state: a device, its paths, which path is being edited, and
which phase is being shown. Qt-free; every derived trait is kept fresh by an
``@observe`` handler so the sidebar, canvas and timeline only ever read."""

# Third-party imports.
from shapely.geometry import Polygon

# Enthought library imports.
from traits.api import (
    Button,
    Dict,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Str,
    observe,
)

# Microdrop utils imports.
from microdrop_utils.wide_path_geometry import leaving_heading, merged, route_headings
from microdrop_utils.wide_path_notation import render_phases, shorthand

# Local imports.
from .wide_path import WidePathModel


class WidePathDemoModel(HasTraits):
    # ------------------------------------------------------------ the device
    #: The loaded device, handed to every path.
    electrode_polygons = Dict(Str, Instance(Polygon))
    electrode_neighbours = Dict(Str, List(Str))

    # ------------------------------------------------------------- the paths
    #: All paths on the device, in creation order.
    paths = List(Instance(WidePathModel))

    #: Row selected in the sidebar list; -1 for none.
    selected_index = Int(-1)

    #: The path canvas clicks edit — ``paths[selected_index]`` or None. A
    #: real Instance trait (not a Property) so observers can reach through
    #: it: ``selected.phases`` fires when the selection or its phases change.
    selected = Instance(WidePathModel)

    #: What the sidebar's parameter Items bind to. TraitsUI binds even while
    #: an Item is hidden, so with nothing selected this is a spare instance
    #: rather than None.
    editing = Instance(WidePathModel, ())

    #: One row label per path for the sidebar list.
    path_names = List(Str)

    # ------------------------------------------------------------ the phases
    #: Which of the selected path's phases is shown; clamped to its range.
    step = Int(0)
    max_step = Int(0)

    #: "1 r", "2 r", "3 u", ... one per phase of the selected path.
    phase_titles = List(Str)

    #: "3 / 7 · 3x1 u" for the ticker: the phase and the shape as it reads.
    phase_label = Str("no phases")

    #: The current phase in frame notation, titled with the shape shorthand.
    frame = Str

    #: The selected path's one-line summary.
    summary = Str

    #: The selected path's last refusal ("Pick an electrode next to...").
    status = Str

    # ---------------------------------------------------------- interactions
    #: Fired by the canvas on Escape.
    escape_pressed = Event()

    load_svg_button = Button("Load device SVG…")
    new_path_button = Button("New path")
    delete_path_button = Button("Delete path")
    undo_button = Button("Undo last")
    clear_path_button = Button("Clear route")
    invert_button = Button("Invert")
    merge_button = Button("Merge with next")
    prev_phase_button = Button("<")
    next_phase_button = Button(">")

    # ------------------------------------------------------------- reactions
    @observe("[selected_index, paths.items]")
    def _selection_changed(self, event):
        in_range = 0 <= self.selected_index < len(self.paths)
        self.selected = self.paths[self.selected_index] if in_range else None
        self.editing = self.selected if in_range else WidePathModel()

    @observe("[paths.items, paths:items:phases, paths:items:name]")
    def _path_names_changed(self, event):
        self.path_names = [f"{p.name} ({len(p.phases)} phases)" for p in self.paths]

    @observe("[selected.phases, step]")
    def _phase_view_changed(self, event):
        """Everything the phase controls show follows from the selected
        path's phases and the step."""
        path = self.selected
        if path is None or not path.phases:
            self.phase_titles, self.max_step = [], 0
            self.step, self.phase_label, self.frame = 0, "no phases", ""
            self.summary = "" if path is None else path.summary
            return
        frames = render_phases(
            path.phases, path.unrolled_route, path.centroids, path.pitch
        )
        self.phase_titles = [title for title, _picture in frames]
        self.max_step = len(frames) - 1
        if self.step > self.max_step:
            self.step = self.max_step  # re-enters this handler with a valid step
            return
        title, picture = frames[self.step]
        block_heading = (
            leaving_heading(route_headings(path.route_ids, path.centroids))
            if path.rotation_lock
            else None
        )
        shape = shorthand(
            path.left,
            path.right,
            path.trail_length,
            path.phases[self.step].heading,
            block_heading,
        )
        self.phase_label = f"{self.step + 1} / {len(frames)} · {shape}"
        self.frame = f"phase {title}   {shape}\n{picture}"
        self.summary = path.summary

    # Colon, not dot: react to the note firing, not to the selection changing
    # (a dot would deliver the new path object as ``event.new``).
    @observe("selected:note")
    def _note_fired(self, event):
        self.status = event.new

    @observe("[selected, selected.route_ids.items]")
    def _route_changed(self, event):
        self.status = ""

    # --------------------------------------------------------------- editing
    def add_path(self, name):
        """Append an empty path on the current device and select it."""
        path = WidePathModel(
            name=name,
            electrode_polygons=self.electrode_polygons,
            electrode_neighbours=self.electrode_neighbours,
        )
        self.paths = self.paths + [path]
        self.selected_index = len(self.paths) - 1
        return path

    def merge_selected_with_next(self):
        """Join the selected path and the one below it at their shared
        endpoint — the device viewer's merge — keeping the selected path
        and dropping the other. Refused through ``status`` when they share
        no endpoint."""
        index = self.selected_index
        if not 0 <= index < len(self.paths) - 1:
            self.status = "Select a path with another one below it to merge"
            return
        path, other = self.paths[index], self.paths[index + 1]
        route = merged(path.route_ids, other.route_ids)
        if route is None:
            self.status = "Paths must share an endpoint to merge"
            return
        path.route_ids = route
        self.paths = [p for p in self.paths if p is not other]
        self.selected_index = index
