# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from traits.api import HasTraits, Instance, Str

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel


class ElectrodeSteppingService(HasTraits):
    """Move, grow, shrink, and split the actuated electrodes by direction.

    Qt-free: the keyboard arrows and the gamepad D-pad both drive it, and it
    only reads and writes the shared device-view model. One instance is
    shared per loaded device so the split session and the electrode cursor
    are the same whichever input moved them last.
    """

    #: Device view Model
    model = Instance(DeviceViewMainModel)

    #: The electrode a step moves from when nothing is actuated; the pointer
    #: handlers keep it at the last clicked / dragged electrode.
    last_electrode_id_visited = Str(allow_none=True)

    # NOTE: Traits `Str` does not accept None reliably; use "" as the unset sentinel.
    _split_axis = Str("", desc="Split axis: 'h' or 'v'. Empty means unset.")
    _split_arm_neg = Str(
        "", desc="Negative-direction split arm electrode id. Empty means unset."
    )
    _split_arm_pos = Str(
        "", desc="Positive-direction split arm electrode id. Empty means unset."
    )

    def traits_init(self):
        # Split-mode history (for contracting back toward the mirror point).
        self._split_sessions: list[dict] = []
        self._split_base_ids: set[str] | None = None

    def map_direction_for_device_rotation(self, direction: str) -> str:
        """
        Map an input direction (controller/keyboard) to the device-frame direction
        based on the current view rotation.

        Example: if view is rotated +90 deg, pressing "up" should move visually up,
        which corresponds to device-frame "left".
        """
        if direction not in {"up", "right", "down", "left"}:
            return direction

        rotation_deg = int(self.model.device_rotation_deg or 0) % 360
        steps = (rotation_deg // 90) % 4
        dirs = ["up", "right", "down", "left"]
        idx = dirs.index(direction)
        return dirs[(idx - steps) % 4]

    def get_active_electrode_ids(self) -> set[str]:
        """
        Return electrode IDs implied by active channels.

        Note: channel -> electrode_ids is one-to-many, so this returns the union.
        """
        active_ids: set[str] = set()
        channels_map = self.model.electrodes.channels_electrode_ids_map or {}
        for ch in self.model.electrodes.actuated_channels:
            for electrode_id in channels_map.get(ch, []):
                active_ids.add(electrode_id)
        return active_ids

    def apply_active_electrode_ids(self, desired_electrode_ids: set[str]) -> None:
        """
        Apply desired electrode IDs by mapping to channels and setting
        actuated_channels.
        """
        electrode_to_channel = self.model.electrodes.electrode_ids_channels_map or {}

        desired_channels: set[int] = set()
        for electrode_id in desired_electrode_ids:
            ch = electrode_to_channel.get(electrode_id, None)
            if ch is not None:
                desired_channels.add(int(ch))

        self.model.electrodes.actuated_channels = desired_channels

    def _direction_vec(self, direction: str) -> tuple[float, float]:
        # SVG coordinate system typically has +y downward.
        if direction == "left":
            return (-1.0, 0.0)
        if direction == "right":
            return (1.0, 0.0)
        if direction == "up":
            return (0.0, -1.0)
        if direction == "down":
            return (0.0, 1.0)
        raise ValueError(f"Unknown direction: {direction}")

    def _neighbor_in_direction(self, electrode_id: str, direction: str) -> str | None:
        """
        Pick the "best" neighbor in the requested direction using electrode centroid
        geometry. Returns None if no neighbor is reasonably in that direction.
        """
        svg = getattr(self.model.electrodes, "svg_model", None)
        if (
            svg is None
            or not getattr(svg, "neighbours", None)
            or not getattr(svg, "electrode_centers", None)
        ):
            return None

        neighbors = svg.neighbours.get(electrode_id, []) or []
        if not neighbors:
            return None

        cx, cy = svg.electrode_centers.get(electrode_id, (None, None))
        if cx is None:
            return None

        dx, dy = self._direction_vec(direction)

        best_id = None
        best_score = None
        for nid in neighbors:
            nx, ny = svg.electrode_centers.get(nid, (None, None))
            if nx is None:
                continue
            vx = nx - cx
            vy = ny - cy
            # Prefer large projection in requested direction, penalize sideways
            # motion a bit.
            proj = vx * dx + vy * dy
            if proj <= 0:
                continue
            perp = abs(vx * (-dy) + vy * dx)
            score = proj - 0.35 * perp
            if best_score is None or score > best_score:
                best_score = score
                best_id = nid

        return best_id

    def step_active_electrodes(self, direction: str) -> None:
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        active_ids = self.get_active_electrode_ids()
        if not active_ids:
            # Fallback: if user hasn't actuated anything, try last visited.
            if self.last_electrode_id_visited:
                active_ids = {self.last_electrode_id_visited}
            else:
                return

        new_ids: set[str] = set()
        moved_any = False
        for eid in active_ids:
            nid = self._neighbor_in_direction(eid, direction)
            if nid is None:
                new_ids.add(eid)
            else:
                moved_any = True
                new_ids.add(nid)

        if moved_any:
            self.apply_active_electrode_ids(new_ids)
            # Update "current" electrode for subsequent steps.
            # Pick one of the moved electrodes (arbitrary but stable).
            self.last_electrode_id_visited = next(iter(new_ids))

    def extend_active_electrodes(self, direction: str) -> None:
        """
        Extend active electrodes by adding one layer on the frontier in `direction`
        (A held + D-pad).
        """
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        active_ids = self.get_active_electrode_ids()
        if not active_ids:
            if self.last_electrode_id_visited:
                active_ids = {self.last_electrode_id_visited}
            else:
                return

        svg = getattr(self.model.electrodes, "svg_model", None)
        centers = getattr(svg, "electrode_centers", None) if svg else None
        if not centers:
            base = self.last_electrode_id_visited or next(iter(active_ids))
            nid = self._neighbor_in_direction(base, direction)
            if nid:
                desired = set(active_ids)
                desired.add(nid)
                self.apply_active_electrode_ids(desired)
                self.last_electrode_id_visited = nid
            return

        dx, dy = self._direction_vec(direction)
        projections: dict[str, float] = {}
        for eid in active_ids:
            cx, cy = centers.get(eid, (None, None))
            if cx is None:
                continue
            projections[eid] = cx * dx + cy * dy

        if not projections:
            return

        max_proj = max(projections.values())
        eps = 1e-6
        frontier = [eid for eid, p in projections.items() if (max_proj - p) <= eps]

        additions: set[str] = set()
        for eid in frontier:
            nid = self._neighbor_in_direction(eid, direction)
            if nid is not None:
                additions.add(nid)

        if additions:
            desired = set(active_ids) | additions
            self.apply_active_electrode_ids(desired)
            self.last_electrode_id_visited = next(iter(additions))

    def shrink_active_electrodes(self, direction: str) -> None:
        """
        Shrink active electrodes by removing the "frontier" layer in `direction`
        (B held + D-pad).
        """
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        active_ids = self.get_active_electrode_ids()
        if not active_ids:
            return

        if len(active_ids) <= 1:
            # Can't shrink further—treat as clear.
            self.model.electrodes.clear_electrode_states()
            self.reset_split_state()
            return

        svg = getattr(self.model.electrodes, "svg_model", None)
        centers = getattr(svg, "electrode_centers", None) if svg else None
        if not centers:
            # No geometry; remove the last visited if active.
            if self.last_electrode_id_visited in active_ids and len(active_ids) > 1:
                desired = set(active_ids)
                desired.remove(self.last_electrode_id_visited)
                self.apply_active_electrode_ids(desired)
            return

        dx, dy = self._direction_vec(direction)
        projections: dict[str, float] = {}
        for eid in active_ids:
            cx, cy = centers.get(eid, (None, None))
            if cx is None:
                continue
            projections[eid] = cx * dx + cy * dy

        if not projections:
            return

        max_proj = max(projections.values())
        eps = 1e-6
        frontier = {eid for eid, p in projections.items() if (max_proj - p) <= eps}

        desired = set(active_ids) - frontier
        if not desired:
            self.model.electrodes.clear_electrode_states()
            self.reset_split_state()
            return

        self.apply_active_electrode_ids(desired)
        self.last_electrode_id_visited = next(iter(desired))

    def reset_split_state(self) -> None:
        self._split_axis = ""
        self._split_arm_neg = ""
        self._split_arm_pos = ""
        try:
            self._split_sessions.clear()
        except Exception:
            self._split_sessions = []
        self._split_base_ids = None

    def _get_active_components(self, active_ids: set[str]) -> list[set[str]]:
        """
        Partition active electrode IDs into connected components using the SVG
        neighbour graph. Each component corresponds to an independent "droplet
        blob" for splitting.
        """
        if not active_ids:
            return []

        svg = getattr(self.model.electrodes, "svg_model", None)
        neighbours = getattr(svg, "neighbours", None) if svg else None
        if not neighbours:
            return [set(active_ids)]

        remaining = set(active_ids)
        components: list[set[str]] = []
        while remaining:
            start = next(iter(remaining))
            stack = [start]
            comp = {start}
            remaining.remove(start)
            while stack:
                cur = stack.pop()
                for nb in neighbours.get(cur, []) or []:
                    if nb in remaining:
                        remaining.remove(nb)
                        comp.add(nb)
                        stack.append(nb)
            components.append(comp)
        return components

    def split_step(self, direction: str) -> None:
        """
        Split stepping while X is held.

        Behavior:
        - The first arrow press selects the split axis (left/right => horizontal,
          up/down => vertical) and starts a fresh split session (mirror point
          fixed for the duration of holding X).
        - Right/Down: move *further away* from the mirror point (expand).
        - Left/Up: move *closer* to the mirror point (contract).

        Each connected component of active electrodes is treated as an independent
        droplet blob.
        """
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        svg = getattr(self.model.electrodes, "svg_model", None)
        centers = getattr(svg, "electrode_centers", None) if svg else None

        # If nothing is active, split should do nothing and should not "remember"
        # old state.
        active_now = self.get_active_electrode_ids()
        if not active_now:
            self.reset_split_state()
            return

        axis = "h" if direction in ("left", "right") else "v"
        expand = direction in ("right", "down")
        contract = direction in ("left", "up")

        # Initialize / re-initialize sessions when axis changes.
        if (self._split_axis or "") != axis:
            self.reset_split_state()
            self._split_axis = axis

            self._split_base_ids = set(active_now)
            self._split_sessions = []
            for comp in self._get_active_components(active_now):
                ids_list = list(comp)
                if not ids_list:
                    continue
                if centers:
                    if axis == "h":
                        ids_list.sort(key=lambda eid: centers.get(eid, (0.0, 0.0))[0])
                    else:
                        ids_list.sort(key=lambda eid: centers.get(eid, (0.0, 0.0))[1])
                n = len(ids_list)
                if n == 1:
                    left_ids = {ids_list[0]}
                    right_ids = {ids_list[0]}
                    mirror_ids: set[str] = set()
                else:
                    mid = n // 2
                    if n % 2 == 1:
                        mirror_ids = {ids_list[mid]}
                        left_ids = set(ids_list[:mid])
                        right_ids = set(ids_list[mid + 1 :])
                    else:
                        mirror_ids = set()
                        left_ids = set(ids_list[:mid])
                        right_ids = set(ids_list[mid:])
                self._split_sessions.append(
                    {
                        # Track two "groups" on either side of the mirror point.
                        "left_ids": left_ids,
                        "right_ids": right_ids,
                        "mirror_ids": mirror_ids,
                        "history": [],  # list[tuple[set[str], set[str]]]
                        # first expand: only remove middle (or split single)
                        "normalized": False,
                    }
                )

        neg_dir = "left" if axis == "h" else "up"
        pos_dir = "right" if axis == "h" else "down"

        # Helper: shift a set by one neighbor step in `direction`.
        def _shift(ids: set[str], direction: str) -> tuple[set[str], bool]:
            moved = False
            out: set[str] = set()
            for eid in ids:
                nid = self._neighbor_in_direction(eid, direction)
                if nid is None:
                    out.add(eid)
                else:
                    moved = True
                    out.add(nid)
            return out, moved

        if contract:
            desired_all: set[str] = set()
            any_change = False
            for sess in self._split_sessions:
                hist = sess.get("history") or []
                if hist:
                    prev_left, prev_right = hist.pop()
                    sess["left_ids"] = set(prev_left)
                    sess["right_ids"] = set(prev_right)
                    any_change = True
                desired_all |= set(sess.get("left_ids") or set())
                desired_all |= set(sess.get("right_ids") or set())
            if any_change and desired_all:
                self.apply_active_electrode_ids(desired_all)
                self.last_electrode_id_visited = next(iter(desired_all))
                return

            # Fully contracted: merge back to the original pre-split selection.
            if not any_change and self._split_base_ids:
                base_ids = set(self._split_base_ids)
                self.apply_active_electrode_ids(base_ids)
                self.last_electrode_id_visited = next(iter(base_ids))

                # Reinitialize sessions from the merged state so the next expand
                # starts cleanly.
                self._split_sessions = []
                for comp in self._get_active_components(base_ids):
                    ids_list = list(comp)
                    if not ids_list:
                        continue
                    if centers:
                        if axis == "h":
                            ids_list.sort(
                                key=lambda eid: centers.get(eid, (0.0, 0.0))[0]
                            )
                        else:
                            ids_list.sort(
                                key=lambda eid: centers.get(eid, (0.0, 0.0))[1]
                            )
                    n = len(ids_list)
                    if n == 1:
                        left_ids = {ids_list[0]}
                        right_ids = {ids_list[0]}
                        mirror_ids: set[str] = set()
                    else:
                        mid = n // 2
                        if n % 2 == 1:
                            mirror_ids = {ids_list[mid]}
                            left_ids = set(ids_list[:mid])
                            right_ids = set(ids_list[mid + 1 :])
                        else:
                            mirror_ids = set()
                            left_ids = set(ids_list[:mid])
                            right_ids = set(ids_list[mid:])
                    self._split_sessions.append(
                        {
                            "left_ids": left_ids,
                            "right_ids": right_ids,
                            "mirror_ids": mirror_ids,
                            "history": [],
                            "normalized": False,
                        }
                    )
            return

        if not expand:
            return

        # First expand after starting split:
        # - If 3+ electrodes selected, only turn off the middle (mirror electrode)
        #   and keep the rest.
        # - If 1 electrode selected, perform the actual split into its two neighbors.
        # Subsequent expands: move left/right groups outward as groups.
        desired_all: set[str] = set()
        moved_any = False
        for sess in self._split_sessions:
            left_ids: set[str] = set(sess.get("left_ids") or set())
            right_ids: set[str] = set(sess.get("right_ids") or set())
            mirror_ids: set[str] = set(sess.get("mirror_ids") or set())

            if not sess.get("normalized", False):
                # Save current groups for contraction.
                try:
                    sess["history"].append((set(left_ids), set(right_ids)))
                except Exception:
                    pass

                if len(left_ids) == 1 and left_ids == right_ids and not mirror_ids:
                    # Single-electrode case: split into neighbors (both sides)
                    # immediately.
                    center = next(iter(left_ids))
                    new_left = self._neighbor_in_direction(center, neg_dir) or center
                    new_right = self._neighbor_in_direction(center, pos_dir) or center
                    left_ids = {new_left}
                    right_ids = {new_right}
                    sess["left_ids"] = left_ids
                    sess["right_ids"] = right_ids
                    sess["normalized"] = True
                    desired_all |= left_ids | right_ids
                    moved_any = True
                    continue

                # Multi-electrode case:
                # - Odd count: deactivate the single middle (mirror) and keep the
                #   rest.
                # - Even count: there is no single middle; immediately begin
                #   expanding outward.
                sess["normalized"] = True

                if mirror_ids:
                    desired_all |= left_ids | right_ids
                    moved_any = True
                    continue

                # Even-count: move ONLY the positive-side group on the first step.
                # This creates a *single* gap between the two sides (instead of two).
                new_right, moved_right = _shift(right_ids, pos_dir)
                sess["left_ids"] = left_ids
                sess["right_ids"] = new_right
                desired_all |= left_ids | new_right
                moved_any = moved_any or moved_right
                continue

            # Save current groups for contraction.
            try:
                sess["history"].append((set(left_ids), set(right_ids)))
            except Exception:
                pass

            # Expand away from mirror: left group moves neg_dir, right group moves
            # pos_dir.
            new_left, moved_left = _shift(left_ids, neg_dir)
            new_right, moved_right = _shift(right_ids, pos_dir)
            moved_any = moved_any or moved_left or moved_right

            sess["left_ids"] = new_left
            sess["right_ids"] = new_right
            desired_all |= new_left | new_right

        if moved_any and desired_all:
            self.apply_active_electrode_ids(desired_all)
            self.last_electrode_id_visited = next(iter(desired_all))
        return
