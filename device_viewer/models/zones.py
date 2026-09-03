# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free models for electrode zones (#596).

Zone types are tracked by id (id == name unless that collides, then a
generated id); regions store their member electrode ids as the source of
truth, and the drawn outline is *computed* as the union boundary of the
member electrodes' polygons. See docs/superpowers/specs/
2026-08-26-electrode-zones-design.md.
"""

# Standard library imports.
import math

# Third-party imports.
from shapely import STRtree
from shapely.geometry import JOIN_STYLE, Point, Polygon, box
from shapely.ops import unary_union

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Dict,
    Enum,
    Event,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
    cached_property,
    observe,
)

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from ..consts import (
    ZONE_COLOR_CYCLE,
    ZONE_DRAW_MODE,
    ZONE_OUTLINE_GAP_CLOSING_FRACTION,
    ZONE_SELECT_MODE,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


class ZoneType(HasTraits):
    #: Stable key; equals ``name`` unless that would collide with an existing id.
    id = Str()

    #: Display name, e.g. "heating", "mixing". Not necessarily unique.
    name = Str()

    #: Hex fill/outline color, e.g. "#f5e050" (the sidebar tree's color cell
    #: opens a picker and writes the hex back, so the model stays a string).
    color = Str()

    #: Number of regions of this type; maintained by ZoneLayerManager.
    region_count = Int(0)

    #: Bulk switch: toggling it shows or hides every region of this type
    #: (ZoneLayerManager applies it). Regions can still be toggled one by
    #: one afterwards; this does not track them back.
    visible = Bool(True)

    #: Fired by the row's delete glyph in the sidebar tree.
    delete_requested = Event()


class ZoneRegion(HasTraits):
    #: Stable key within the manager, e.g. "heating-1"; never reused.
    id = Str()

    #: Id of the ZoneType this region belongs to.
    zone_id = Str()

    #: Whether the region is drawn on the device view.
    visible = Bool(True)

    #: Fired by the row's delete glyph in the sidebar tree.
    delete_requested = Event()

    #: SOURCE OF TRUTH for the region — ids of the member electrodes.
    electrode_ids = List(Str)

    #: electrode id -> channel (may be None) for the member electrodes.
    electrode_id_to_channel_map = Dict(Str)

    #: Channels covered by the region, derived from the member electrodes.
    channels = Property(
        List(Int), observe="[electrode_ids.items, electrode_id_to_channel_map.items]"
    )

    @cached_property
    def _get_channels(self):
        channels = {
            self.electrode_id_to_channel_map.get(electrode_id)
            for electrode_id in self.electrode_ids
        }
        return sorted(channel for channel in channels if channel is not None)


class ZoneLayerManager(HasTraits):
    zone_types = List(Instance(ZoneType))
    regions = List(Instance(ZoneRegion))

    #: Id of the type new regions are created as.
    active_zone_id = Str()

    #: Zone row selected in the sidebar tree; drives ``active_zone_id``.
    selected_zone_type = Instance(ZoneType)

    #: Regions picked in select mode; ctrl+click accumulates several (for
    #: merging), a plain click collapses back to one.
    selected_regions = List(Instance(ZoneRegion))

    #: Primary selected region (last of ``selected_regions``); assigning to
    #: it collapses the multi-selection to that one region (None clears).
    selected_region = Property(observe="selected_regions.items")

    #: Whether ``merge_selected_regions`` would succeed: two or more selected
    #: regions of one zone whose electrodes form one contiguous block. Tracks
    #: the selection, its regions' electrodes and their zone.
    can_merge = Property(
        Bool,
        observe=(
            "selected_regions.items.electrode_ids.items, selected_regions.items.zone_id"
        ),
    )

    #: Region whose electrode set is being re-edited via the pending
    #: selection; hidden from the committed layer until commit or clear.
    editing_region = Instance(ZoneRegion)

    #: Geometry of the active device: electrode id -> shapely Polygon (SVG coords).
    electrode_polygons = Dict(Str, Instance(Polygon))

    #: electrode id -> channel (may be None) for the active device.
    electrode_id_to_channel_map = Dict(Str)

    #: electrode id -> adjacent electrode ids, from the device SVG's own
    #: neighbour graph — the contiguity authority for splitting/merging.
    electrode_neighbours = Dict(Str, List(Str))

    #: In-progress selection: electrodes accumulated by rubber-band drags and
    #: click toggles, turned into a ZoneRegion by ``commit_pending_region``.
    pending_electrode_ids = List(Str)

    #: Morphological closing distance used to bridge inter-electrode gaps when
    #: computing a region's union outline.
    outline_closing_distance = Property(Float, observe="electrode_polygons")

    #: Sidebar tool: "" (zone tools off) or one of the two zone modes.
    #: ZonesController keeps it in step with DeviceViewMainModel.mode.
    mode = Enum("", ZONE_DRAW_MODE, ZONE_SELECT_MODE)

    #: The two tool buttons as Bools over ``mode``: setting one True picks
    #: that tool, setting the active one False turns the zone tools off.
    draw_tool_active = Property(Bool, observe="mode")
    select_tool_active = Property(Bool, observe="mode")

    def _get_draw_tool_active(self):
        return self.mode == ZONE_DRAW_MODE

    def _set_draw_tool_active(self, active):
        self._set_tool(ZONE_DRAW_MODE, active)

    def _get_select_tool_active(self):
        return self.mode == ZONE_SELECT_MODE

    def _set_select_tool_active(self, active):
        self._set_tool(ZONE_SELECT_MODE, active)

    def _set_tool(self, tool_mode, active):
        if active:
            self.mode = tool_mode
        elif self.mode == tool_mode:
            self.mode = ""

    #: app_globals key the zoning snapshot mirrors to; empty disables the
    #: mirror (tests, headless). Set from device_viewer.consts.ZONES_KEY.
    globals_key = Str()

    #: Fired after each undo snapshot is taken (one per undoable mutation);
    #: the controller pushes a matching command onto the app's undo stack.
    undo_snapshot_pushed = Event()

    #: Fired when ``translate_regions`` refuses a drag (an electrode would
    #: leave the device or a region would split); the view reports it.
    move_rejected = Event()

    #: Whether the floating button strips show on the device view at all.
    show_canvas_overlays = Bool(True)

    #: Touch-friendly ctrl: while on, a click in zone-select mode toggles a
    #: region in the selection instead of replacing it.
    multi_select = Bool(False)

    #: Touch-friendly ctrl+drag: while on, rubber bands in draw mode remove
    #: electrodes from the pending selection.
    subtract_mode = Bool(False)

    # Sidebar / overlay actions; ZonesController turns them into calls.
    commit_button = Button("check")
    clear_pending_button = Button("delete")
    add_zone_type_button = Button("add")
    move_zone_type_up_button = Button("arrow_upward")
    move_zone_type_down_button = Button("arrow_downward")
    edit_region_button = Button("edit")
    delete_region_button = Button("delete")
    hide_region_button = Button("visibility_off")
    merge_regions_button = Button("merge")

    #: zone id -> highest region number ever handed out; never reused.
    _region_id_counters = Dict(Str, Int)

    #: region -> (electrode-id tuple, computed outline geometry) cache.
    _outline_cache = Dict()

    #: Undo snapshots (plain dicts), newest last; uncapped so it stays in
    #: lock-step with the app's own (unbounded) pyface CommandStack.
    _undo_stack = List()

    #: Redo snapshots; refilled by undo, cleared by any new operation.
    _redo_stack = List()

    can_undo = Property(Bool, observe="_undo_stack.items")
    can_redo = Property(Bool, observe="_redo_stack.items")

    def _get_selected_region(self):
        return self.selected_regions[-1] if self.selected_regions else None

    def _set_selected_region(self, region):
        self.selected_regions = [region] if region is not None else []

    def _get_can_merge(self):
        selection = self.selected_regions
        return (
            len(selection) >= 2
            and len({region.zone_id for region in selection}) == 1
            and len(self._connected_components(self._selected_electrode_ids())) == 1
        )

    def _selected_electrode_ids(self):
        """Sorted union of the selected regions' electrodes."""
        return sorted(
            electrode_id
            for region in self.selected_regions
            for electrode_id in region.electrode_ids
        )

    def _get_can_undo(self):
        return bool(self._undo_stack)

    def _get_can_redo(self):
        return bool(self._redo_stack)

    # ------------------------------------------------------------------ query
    def get(self, zone_id):
        return [region for region in self.regions if region.zone_id == zone_id]

    def region_count(self, zone_id):
        return len(self.get(zone_id))

    def zone_type_for(self, zone_id):
        for zone_type in self.zone_types:
            if zone_type.id == zone_id:
                return zone_type
        return None

    def channels_for(self, zone_id):
        """Channels covered by the zone: the UNION over its regions."""
        channels = set()
        for region in self.get(zone_id):
            channels.update(region.channels)
        return sorted(channels)

    def next_color(self):
        return ZONE_COLOR_CYCLE[len(self.zone_types) % len(ZONE_COLOR_CYCLE)]

    # ---------------------------------------------------------------- mutate
    def set_device(
        self, electrode_polygons, electrode_id_to_channel_map, electrode_neighbours=None
    ):
        """Swap in a new device's geometry; existing regions reference stale
        electrode ids, so they are dropped (zone types persist)."""
        self.regions = []
        self.selected_regions = []
        self.editing_region = None
        self.pending_electrode_ids = []
        self.electrode_polygons = dict(electrode_polygons)
        self.electrode_id_to_channel_map = dict(electrode_id_to_channel_map)
        self.electrode_neighbours = dict(electrode_neighbours or {})
        self._outline_cache = {}
        # A new device starts a new history (the app's stack is cleared too).
        self._undo_stack = []
        self._redo_stack = []
        if self.electrode_polygons and not self.electrode_neighbours:
            logger.warning(
                "Device has no electrode neighbour graph; contiguity checks "
                "are disabled"
            )

    def update_channel_map(self, electrode_id_to_channel_map):
        """Re-derive every region's channels after the device's electrode ->
        channel mapping changed (channel edits in the device viewer)."""
        self.electrode_id_to_channel_map = dict(electrode_id_to_channel_map)
        for region in self.regions:
            self._set_region_electrodes(region, region.electrode_ids)

    def add_zone_type(self, name="", color=None):
        """Append a zone type; a blank name becomes ``zone-<row number>``."""
        name = name.strip() or self._default_zone_name(len(self.zone_types))
        self._push_undo()
        zone_type = ZoneType(
            id=self._generate_zone_id(name), name=name, color=color or self.next_color()
        )
        self.zone_types.append(zone_type)
        return zone_type

    def move_zone_type(self, zone_type, delta):
        """Move the zone ``delta`` places in ``zone_types`` — the layer order,
        first row on top. The move is clamped to the list, and a move that
        would not shift the zone changes nothing and takes no snapshot."""
        if zone_type not in self.zone_types:
            return
        index = self.zone_types.index(zone_type)
        target = max(0, min(len(self.zone_types) - 1, index + delta))
        if target == index:
            return
        self._push_undo()
        zone_types = list(self.zone_types)
        zone_types.insert(target, zone_types.pop(index))
        self.zone_types = zone_types

    def remove_zone_type(self, zone_id):
        if self.zone_type_for(zone_id) is None:
            return
        self._push_undo()
        self.selected_regions = [
            region for region in self.selected_regions if region.zone_id != zone_id
        ]
        if self.editing_region is not None and self.editing_region.zone_id == zone_id:
            self.clear_pending()
        self.regions = [region for region in self.regions if region.zone_id != zone_id]
        self.zone_types = [
            zone_type for zone_type in self.zone_types if zone_type.id != zone_id
        ]
        if self.active_zone_id == zone_id:
            self.selected_zone_type = self.zone_types[0] if self.zone_types else None
            self.active_zone_id = self.zone_types[0].id if self.zone_types else ""

    def _add_region_from_electrode_ids(self, electrode_ids, zone_id=None):
        zone_id = zone_id or self.active_zone_id
        if not electrode_ids or not zone_id:
            return None
        region = ZoneRegion(
            id=self._generate_region_id(zone_id),
            zone_id=zone_id,
            electrode_ids=sorted(electrode_ids),
            electrode_id_to_channel_map={
                electrode_id: self.electrode_id_to_channel_map.get(electrode_id)
                for electrode_id in electrode_ids
            },
        )
        self.regions.append(region)
        logger.debug(
            f"Added region of zone '{region.zone_id}' covering "
            f"{len(region.electrode_ids)} electrodes (channels {region.channels})"
        )
        return region

    def remove_region(self, region):
        if region not in self.regions:
            return
        self._push_undo()
        self.regions.remove(region)
        self._outline_cache.pop(region, None)
        if region in self.selected_regions:
            self.selected_regions = [
                other for other in self.selected_regions if other is not region
            ]
        if self.editing_region is region:
            self.clear_pending()

    def add_to_pending(self, electrode_ids):
        """Union the electrodes into the in-progress selection."""
        self.pending_electrode_ids.extend(
            electrode_id
            for electrode_id in electrode_ids
            if electrode_id not in self.pending_electrode_ids
        )

    def toggle_electrode_in_pending(self, electrode_id):
        """Click refinement for irregular shapes: toggle one electrode in and
        out of the in-progress selection."""
        if not electrode_id:
            return
        if electrode_id in self.pending_electrode_ids:
            self.pending_electrode_ids.remove(electrode_id)
        else:
            self.pending_electrode_ids.append(electrode_id)

    def remove_from_pending(self, electrode_ids):
        """Subtract the electrodes from the in-progress selection (the
        ctrl+rubber-band gesture in draw mode)."""
        removal = set(electrode_ids)
        self.pending_electrode_ids = [
            electrode_id
            for electrode_id in self.pending_electrode_ids
            if electrode_id not in removal
        ]

    def clear_pending(self):
        """Discard the in-progress selection without committing it; cancels an
        in-progress region edit (the region reappears unchanged)."""
        self.editing_region = None
        self.pending_electrode_ids = []

    def begin_edit_region(self, region):
        """Re-open the region's electrode set as the pending selection; the
        next commit updates the region in place instead of adding a new one."""
        if region is None:
            return
        self.editing_region = region
        self.selected_zone_type = self.zone_type_for(region.zone_id)
        self.pending_electrode_ids = list(region.electrode_ids)

    def commit_pending_region(self):
        """Turn the in-progress selection into ZoneRegion(s) of the active
        type and clear the selection. Disjoint electrode groups commit as one
        region per contiguous component. When a region is being edited, it
        keeps the largest component (an empty selection leaves it unchanged)
        and any other components become new regions of the same zone."""
        components = self._connected_components(self.pending_electrode_ids)
        if self.editing_region is not None:
            region = self.editing_region
            if components:
                self._push_undo()
                self._set_region_electrodes(region, components[0])
                for component in components[1:]:
                    self._add_region_from_electrode_ids(
                        component, zone_id=region.zone_id
                    )
            self.editing_region = None
            self.pending_electrode_ids = []
            return region
        if components and self.active_zone_id:
            self._push_undo()
        committed = [
            region
            for component in components
            if (region := self._add_region_from_electrode_ids(component)) is not None
        ]
        if committed:
            self.pending_electrode_ids = []
        return committed[0] if committed else None

    def cancel_current_interaction(self):
        """Escape semantics: cancel the innermost thing first — an in-progress
        selection or edit, then the region selection. Returns True when
        something was cancelled."""
        if self.pending_electrode_ids or self.editing_region is not None:
            self.clear_pending()
            return True
        if self.selected_regions:
            self.selected_regions = []
            return True
        return False

    def toggle_region_in_selection(self, region):
        """Ctrl+click multi-select: toggle the region in ``selected_regions``."""
        if region is None:
            return
        selection = [other for other in self.selected_regions if other is not region]
        if len(selection) == len(self.selected_regions):
            selection.append(region)
        self.selected_regions = selection

    def merge_selected_regions(self):
        """Merge the multi-selected regions into one region of their common
        zone when ``can_merge`` allows it; otherwise nothing changes and None
        is returned."""
        if not self.can_merge:
            return None
        selection = list(self.selected_regions)
        union_ids = self._selected_electrode_ids()
        self._push_undo()
        merged = min(selection, key=self.regions.index)
        if self.editing_region in selection and self.editing_region is not merged:
            self.clear_pending()
        self._set_region_electrodes(merged, union_ids)
        self.regions = [
            region
            for region in self.regions
            if region is merged or region not in selection
        ]
        for region in selection:
            if region is not merged:
                self._outline_cache.pop(region, None)
        self.selected_regions = [merged]
        return merged

    def change_region_zone(self, region, zone_id):
        """Reassign the region to another zone type; it gets a fresh id in
        the new zone's namespace (ids embed the zone, and are never reused)."""
        if region not in self.regions or self.zone_type_for(zone_id) is None:
            return
        if zone_id == region.zone_id:
            return
        self._push_undo()
        region.zone_id = zone_id
        region.id = self._generate_region_id(zone_id)

    def _translated_electrode_ids(self, region, dx, dy):
        """New membership for the region moved by (dx, dy) — each member
        snaps to the electrode whose centroid is nearest its own centroid
        plus the delta — or None when the move is invalid."""
        centroids = {
            electrode_id: polygon.centroid
            for electrode_id, polygon in self.electrode_polygons.items()
        }
        if not centroids:
            return None
        new_ids = []
        for electrode_id in region.electrode_ids:
            if electrode_id not in centroids:
                return None
            x = centroids[electrode_id].x + dx
            y = centroids[electrode_id].y + dy
            target = min(
                centroids,
                key=lambda other: (
                    (centroids[other].x - x) ** 2 + (centroids[other].y - y) ** 2
                ),
            )
            new_ids.append(target)
        if len(set(new_ids)) != len(new_ids):
            return None
        if len(self._connected_components(new_ids)) != 1:
            return None
        return new_ids

    def translate_regions(self, regions, dx, dy):
        """Move several regions by the same snapped delta, all-or-nothing."""
        moves = []
        for region in regions:
            new_ids = self._translated_electrode_ids(region, dx, dy)
            if new_ids is None:
                self.move_rejected = True
                return False
            moves.append((region, new_ids))
        self._push_undo()
        for region, new_ids in moves:
            self._set_region_electrodes(region, new_ids)
        return True

    # -------------------------------------------------------------- geometry
    def _set_region_electrodes(self, region, electrode_ids):
        region.electrode_id_to_channel_map = {
            electrode_id: self.electrode_id_to_channel_map.get(electrode_id)
            for electrode_id in electrode_ids
        }
        region.electrode_ids = sorted(electrode_ids)

    def _connected_components(self, electrode_ids):
        """Group the electrodes into contiguity components, largest first,
        walking the device's own neighbour graph."""
        remaining = {
            electrode_id
            for electrode_id in electrode_ids
            if electrode_id in self.electrode_polygons
        }
        if remaining and not self.electrode_neighbours:
            # No adjacency information: treat the whole set as one blob
            # rather than splitting every commit into singletons.
            return [sorted(remaining)]
        components = []
        while remaining:
            seed = remaining.pop()
            component = {seed}
            frontier = [seed]
            while frontier:
                near = remaining & set(
                    self.electrode_neighbours.get(frontier.pop(), [])
                )
                remaining -= near
                component |= near
                frontier.extend(near)
            components.append(sorted(component))
        components.sort(key=len, reverse=True)
        return components

    def electrode_id_at(self, x, y):
        """Id of the electrode whose polygon contains the point, or None."""
        point = Point(x, y)
        for electrode_id, polygon in self.electrode_polygons.items():
            if polygon.contains(point):
                return electrode_id
        return None

    def capture_electrode_ids_touching(self, min_x, min_y, max_x, max_y):
        """Electrode ids whose polygons overlap the rectangle (SVG coords):
        touching any part of an electrode is enough to select it."""
        selection_box = box(min_x, min_y, max_x, max_y)
        return sorted(
            electrode_id
            for electrode_id, polygon in self.electrode_polygons.items()
            if polygon.intersects(selection_box) and not polygon.touches(selection_box)
        )

    def electrode_union(self, electrode_ids):
        """Plain union of the electrodes' polygons (no gap closing) — the
        pending-selection highlight. None when no member is known."""
        member_polygons = [
            self.electrode_polygons[electrode_id]
            for electrode_id in electrode_ids
            if electrode_id in self.electrode_polygons
        ]
        if not member_polygons:
            return None
        return unary_union(member_polygons)

    def region_outline(self, region):
        """Union boundary of the region's member electrodes, with gaps between
        adjacent members bridged by a buffer-out/buffer-in closing so the
        outline hugs the block's outer corners. Cached per region keyed by
        its electrode set."""
        key = tuple(region.electrode_ids)
        cached = self._outline_cache.get(region)
        if cached is not None and cached[0] == key:
            return cached[1]
        member_polygons = [
            self.electrode_polygons[electrode_id]
            for electrode_id in region.electrode_ids
            if electrode_id in self.electrode_polygons
        ]
        if not member_polygons:
            return None
        closing_distance = self.outline_closing_distance
        merged = unary_union(
            [
                polygon.buffer(closing_distance, join_style=JOIN_STYLE.mitre)
                for polygon in member_polygons
            ]
        )
        outline_geometry = merged.buffer(-closing_distance, join_style=JOIN_STYLE.mitre)
        self._outline_cache[region] = (key, outline_geometry)
        return outline_geometry

    @cached_property
    def _get_outline_closing_distance(self):
        polygons = list(self.electrode_polygons.values())
        if len(polygons) < 2:
            return 0.0
        tree = STRtree(polygons)
        smallest_gap = math.inf
        for polygon in polygons:
            _indices, distances = tree.query_nearest(
                polygon, exclusive=True, return_distance=True
            )
            gaps = [distance for distance in distances if distance > 0]
            if gaps:
                smallest_gap = min(smallest_gap, min(gaps))
        if not math.isfinite(smallest_gap):
            return 0.0
        return ZONE_OUTLINE_GAP_CLOSING_FRACTION * smallest_gap

    # ----------------------------------------------------------- persistence
    def to_records(self):
        """Plain-dict records of every region, carrying its zone's name and
        color so a device SVG stays self-describing."""
        records = []
        for region in self.regions:
            zone_type = self.zone_type_for(region.zone_id)
            records.append(
                {
                    "id": region.id,
                    "zone_id": region.zone_id,
                    "zone_name": zone_type.name if zone_type else region.zone_id,
                    "zone_color": zone_type.color if zone_type else self.next_color(),
                    "visible": region.visible,
                    "electrode_ids": list(region.electrode_ids),
                }
            )
        return records

    def load_records(self, records):
        """Replace the regions with the given records (a device SVG's Zones
        layer). A zone id with no local type gets one auto-created from the
        record's name/color; region-id counters resume past the loaded ids.

        Returns
        -------
        int
            Number of records that referenced at least one unknown electrode
            id — dropped entirely (none of their electrodes are known) or
            trimmed to the known subset.
        """
        self.selected_regions = []
        self.editing_region = None
        self.pending_electrode_ids = []
        regions = []
        unloaded_count = 0
        for record in records:
            zone_id = record["zone_id"]
            if self.zone_type_for(zone_id) is None:
                self.zone_types.append(
                    ZoneType(
                        id=zone_id,
                        name=record.get("zone_name") or zone_id,
                        color=record.get("zone_color") or self.next_color(),
                    )
                )
            recorded_ids = record["electrode_ids"]
            electrode_ids = [
                electrode_id
                for electrode_id in recorded_ids
                if electrode_id in self.electrode_polygons
            ]
            if not electrode_ids:
                logger.warning(
                    f"Zone region {record['id']} references no known electrode; skipped"
                )
                unloaded_count += 1
                continue
            if len(electrode_ids) < len(recorded_ids):
                unknown_count = len(recorded_ids) - len(electrode_ids)
                logger.warning(
                    f"Zone region {record['id']} references {unknown_count} "
                    "unknown electrode(s); trimmed"
                )
                unloaded_count += 1
            regions.append(
                ZoneRegion(
                    id=record["id"],
                    zone_id=zone_id,
                    visible=record.get("visible", True),
                    electrode_ids=sorted(electrode_ids),
                    electrode_id_to_channel_map={
                        electrode_id: self.electrode_id_to_channel_map.get(electrode_id)
                        for electrode_id in electrode_ids
                    },
                )
            )
            self._advance_region_counter(record["id"], zone_id)
        self.regions = regions
        self._outline_cache = {}
        return unloaded_count

    def snapshot_for_app_globals(self):
        """JSON-serializable zoning state keyed by zone id."""
        return {
            zone_type.id: {
                "name": zone_type.name,
                "color": zone_type.color,
                "regions": [
                    {
                        "id": region.id,
                        "electrode_ids": list(region.electrode_ids),
                        "channels": list(region.channels),
                    }
                    for region in self.get(zone_type.id)
                ],
            }
            for zone_type in self.zone_types
        }

    @observe(
        "[regions, regions.items, regions:items:electrode_ids.items, "
        "regions:items:zone_id, zone_types, zone_types.items, "
        "zone_types:items:name, zone_types:items:color]"
    )
    def _mirror_to_app_globals(self, event):
        if not self.globals_key:
            return
        try:
            app_globals[self.globals_key] = self.snapshot_for_app_globals()
        except Exception:
            # No Redis (tests, headless runs): the mirror is best-effort.
            logger.debug("Zones app_globals mirror skipped", exc_info=True)

    # -------------------------------------------------------------- internal
    def _advance_region_counter(self, region_id, zone_id):
        prefix = f"{zone_id}-"
        if region_id.startswith(prefix) and region_id[len(prefix) :].isdigit():
            number = int(region_id[len(prefix) :])
            if number > self._region_id_counters.get(zone_id, 0):
                self._region_id_counters[zone_id] = number

    def _generate_region_id(self, zone_id):
        existing_ids = {region.id for region in self.regions}
        number = self._region_id_counters.get(zone_id, 0) + 1
        while f"{zone_id}-{number}" in existing_ids:
            number += 1
        self._region_id_counters[zone_id] = number
        return f"{zone_id}-{number}"

    @staticmethod
    def _default_zone_name(row_index):
        return f"zone-{row_index + 1}"

    @observe("zone_types:items:visible")
    def _apply_zone_visibility(self, event):
        for region in self.get(event.object.id):
            region.visible = event.new

    @observe("zone_types:items:name")
    def _fill_blank_zone_name(self, event):
        # A name cleared in the tree falls back to its row's default.
        if not event.new.strip():
            event.object.name = self._default_zone_name(
                self.zone_types.index(event.object)
            )

    def _generate_zone_id(self, name):
        existing_ids = {zone_type.id for zone_type in self.zone_types}
        if name not in existing_ids:
            return name
        suffix = 2
        while f"{name}-{suffix}" in existing_ids:
            suffix += 1
        return f"{name}-{suffix}"

    @observe("selected_zone_type")
    def _selected_zone_type_changed(self, event):
        if event.new is not None:
            self.active_zone_id = event.new.id

    @observe(
        "[regions, regions.items, regions:items:zone_id, zone_types, zone_types.items]"
    )
    def _update_region_counts(self, event):
        for zone_type in self.zone_types:
            zone_type.region_count = self.region_count(zone_type.id)

    # --------------------------------------------------------------- undo
    def _snapshot(self):
        return {
            "zone_types": [
                {"id": z.id, "name": z.name, "color": z.color} for z in self.zone_types
            ],
            "regions": [
                {
                    "id": r.id,
                    "zone_id": r.zone_id,
                    "visible": r.visible,
                    "electrode_ids": list(r.electrode_ids),
                }
                for r in self.regions
            ],
            "active_zone_id": self.active_zone_id,
        }

    def _push_undo(self):
        self._undo_stack = self._undo_stack + [self._snapshot()]
        # A new operation forks history; the redone future is gone.
        self._redo_stack = []
        self.undo_snapshot_pushed = True

    def undo(self):
        """Restore the state before the last mutating operation."""
        if not self._undo_stack:
            return False
        state = self._undo_stack[-1]
        self._undo_stack = self._undo_stack[:-1]
        self._redo_stack = self._redo_stack + [self._snapshot()]
        self._restore(state)
        return True

    def redo(self):
        """Re-apply the last undone operation."""
        if not self._redo_stack:
            return False
        state = self._redo_stack[-1]
        self._redo_stack = self._redo_stack[:-1]
        # Directly, not via _push_undo — redo must not clear its own stack.
        self._undo_stack = self._undo_stack + [self._snapshot()]
        self._restore(state)
        return True

    def _restore(self, state):
        self.selected_regions = []
        self.editing_region = None
        self.pending_electrode_ids = []
        self.zone_types = [ZoneType(**data) for data in state["zone_types"]]
        self.regions = [
            ZoneRegion(
                id=data["id"],
                zone_id=data["zone_id"],
                visible=data["visible"],
                electrode_ids=list(data["electrode_ids"]),
                electrode_id_to_channel_map={
                    electrode_id: self.electrode_id_to_channel_map.get(electrode_id)
                    for electrode_id in data["electrode_ids"]
                },
            )
            for data in state["regions"]
        ]
        self._outline_cache = {}
        # Id counters are deliberately NOT restored: ids stay monotonic
        # across undo so an undone region's id is never handed out again.
        self.selected_zone_type = self.zone_type_for(state["active_zone_id"])
        self.active_zone_id = state["active_zone_id"]
