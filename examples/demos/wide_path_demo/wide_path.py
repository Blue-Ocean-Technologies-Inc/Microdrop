# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The traits model of one wide path.

Inputs are plain traits the user owns (the route and the slug shape);
outputs are plain traits too, recomputed by ``@observe`` handlers whenever an
input changes, so views simply observe ``phases``/``summary`` and never
compute anything. Qt-free: it can be driven headlessly.
"""

# Third-party imports.
from shapely.geometry import Polygon

# Enthought library imports.
from traits.api import (
    Bool,
    Dict,
    Enum,
    Event,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Range,
    Str,
    Tuple,
    observe,
)

# Microdrop utils imports.
from microdrop_utils.wide_path_geometry import (
    IN_OUT,
    LEFT_RIGHT,
    Phase,
    is_loop,
    lattice_pitch,
    slug_phases,
    unroll,
)


class WidePathModel(HasTraits):
    # ------------------------------------------------------------ the device
    #: id -> shapely polygon, straight from the device SVG. Only the
    #: centroids matter here; the polygons are kept for the canvas.
    electrode_polygons = Dict(Str, Instance(Polygon))

    #: id -> neighbouring ids, the device's adjacency graph. Decides which
    #: picks are legal and, through the pitch, how far "one lane" is.
    electrode_neighbours = Dict(Str, List(Str))

    # ------------------------------------------------------------ the inputs
    #: Shown in the sidebar's path list.
    name = Str("path")

    #: SOURCE OF TRUTH — the centreline, in travel order. Each electrode is a
    #: neighbour of the previous; revisits are allowed (loops, knots).
    route_ids = List(Str)

    #: Extra lanes on each side of the route. In the left/right frame these
    #: are the screen sides of travel (left is up when heading right); in
    #: the in/out frame ``left`` is the inside of the turn and ``right`` the
    #: outside, resolved per corner.
    left = Range(0, 5, 1)
    right = Range(0, 5, 1)

    #: How ``left``/``right`` are read: screen sides, or inside/outside of
    #: the turn (lanes then hug the outer rung whichever way the route bends).
    lane_frame = Enum(IN_OUT, LEFT_RIGHT)

    #: Trail parameters with the meaning they have in the route sidebar;
    #: for a block they set how many route electrodes a phase advances.
    trail_length = Range(1, 20, 1)
    trail_overlay = Range(0, 19, 0)

    #: Keep the block's orientation fixed through corners: it only
    #: translates, so a 3x2 heading right becomes a 2x3 heading up. Squares
    #: behave this way regardless. On by default, like the in/out frame.
    rotation_lock = Bool(True)

    #: Soft start: before the first full phase the block comes on a row at a
    #: time from its tail. Soft end: after the last head it goes off the same
    #: way, down to the head row (the shipped ramps, a row at a time).
    soft_start = Bool(False)
    soft_terminate = Bool(False)

    #: How many times a loop plays its cycle before returning onto the start
    #: electrode (the device viewer's repetitions); an open route ignores it.
    repetitions = Range(1, 20, 1)

    #: Fired with a short message when ``pick`` refuses a click.
    note = Event(Str)

    # ----------------------------------------------------------- the outputs
    #: id -> (x, y) centroid, derived from the polygons.
    centroids = Dict(Str, Tuple(Float, Float))

    #: Lattice spacing, derived from the neighbour graph.
    pitch = Float(1.0)

    #: Whether the route is a loop: its first electrode repeated last.
    loop = Bool(False)

    #: The route the phases index: the route itself, or a loop unrolled over
    #: its repetitions plus the return onto the start (``cycle_length`` is
    #: the loop's period, 0 for an open route).
    unrolled_route = List(Str)
    cycle_length = Int(0)

    #: The phases in playing order — what is on at each; the whole point.
    phases = List(Instance(Phase))

    #: Every electrode any phase turns on (the canvas tints these).
    footprint_ids = List(Str)

    #: One line for the sidebar: shape, phase count, sizes.
    summary = Str

    # ------------------------------------------------------------- reactions
    @observe("[electrode_polygons, electrode_neighbours]")
    def _device_changed(self, event):
        self.centroids = {
            electrode_id: (polygon.centroid.x, polygon.centroid.y)
            for electrode_id, polygon in self.electrode_polygons.items()
        }
        self.pitch = lattice_pitch(self.centroids, self.electrode_neighbours)
        self._recompute(event)

    @observe(
        "[route_ids.items, left, right, lane_frame, trail_length, trail_overlay, "
        "rotation_lock, soft_start, soft_terminate, repetitions]"
    )
    def _recompute(self, event):
        """Every output follows from the inputs through ``slug_phases``."""
        phases = slug_phases(
            self.route_ids,
            self.centroids,
            self.electrode_neighbours,
            self.left,
            self.right,
            self.trail_length,
            self.trail_overlay,
            pitch=self.pitch,
            rotation_lock=self.rotation_lock,
            soft_terminate=self.soft_terminate,
            lane_frame=self.lane_frame,
            repetitions=self.repetitions,
            soft_start=self.soft_start,
        )
        self.loop = is_loop(self.route_ids)
        self.cycle_length = len(self.route_ids) - 1 if self.loop else 0
        self.unrolled_route = unroll(
            self.route_ids, self.repetitions, self.trail_length
        )

        # ``phases`` is what observers react to, so it is assigned last:
        # everything derived from it must already be in place by then.
        self.footprint_ids = sorted({i for phase in phases for i in phase.ids})
        self.summary = self._describe(phases)
        self.phases = phases

    def _describe(self, phases):
        if not self.route_ids:
            return "Click (or drag) a chain of neighbouring electrodes."
        sizes = [len(phase.ids) for phase in phases]
        # A locked block strides by its width across its original heading, so
        # the overlay reaches that far too.
        extent = self.trail_length
        if self.rotation_lock:
            extent = max(self.left + self.right + 1, self.trail_length)
        overlay = min(self.trail_overlay, extent - 1)
        locked = " · rotation locked" if self.rotation_lock else ""
        frame = " · in/out" if self.lane_frame == IN_OUT else ""
        loop = f" · loop ×{self.repetitions}" if self.loop else ""

        return (
            f"route {len(self.route_ids)} · {self.left + self.right + 1}x"
            f"{self.trail_length}{locked}{frame}{loop} · phases {len(phases)} (overlay "
            f"{overlay}) · size {min(sizes)}–{max(sizes)} · electrodes "
            f"{len(self.footprint_ids)}"
        )

    # --------------------------------------------------------------- editing
    def invert(self):
        """Reverse the route, as the device viewer's invert does. Every
        heading flips, so the in / out sides and the corner slides are
        re-decided from the new start."""
        self.route_ids = list(reversed(self.route_ids))

    def pick(self, electrode_id):
        """Extend the route to a neighbour of its last electrode.

        Revisits are allowed — loops, knots and back-and-forth are routes
        too, as in the device viewer — so undo is a separate call. Returns
        whether the route changed; a refusal fires ``note`` instead.
        """
        if electrode_id not in self.electrode_polygons:
            return False
        if not self.route_ids:
            self.route_ids = [electrode_id]
            return True
        last = self.route_ids[-1]
        if electrode_id == last:
            return False
        if electrode_id not in self.electrode_neighbours.get(last, []):
            self.note = "Pick an electrode next to the previous one"
            return False
        self.route_ids = self.route_ids + [electrode_id]
        return True

    def undo(self):
        """Drop the last electrode of the route."""
        self.route_ids = self.route_ids[:-1]

    def clear(self):
        self.route_ids = []
