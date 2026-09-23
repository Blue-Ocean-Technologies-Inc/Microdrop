# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Qt-free state of the Edit Connections dialog."""

# Enthought library imports.
from traits.api import (
    Bool,
    Dict,
    Event,
    HasTraits,
    Instance,
    List,
    Property,
    Str,
    Tuple,
)

# Local imports.
from ..utils.dmf_utils import SvgUtil


class ConnectionsEditorModel(HasTraits):
    """The device's connections plus the editor's current selection. The
    connections themselves stay on the SVG model — the editor edits them
    in place, so the main device view and Save follow along."""

    #: SOURCE OF TRUTH for the connections (``neighbours``) and the
    #: electrode centroids the editor draws between.
    svg_model = Instance(SvgUtil)

    #: The selected connections, as (electrode id, electrode id) pairs.
    selected_connections = List(Tuple(Str, Str))

    #: ``svg_model.neighbours`` as it was when the dialog opened — the
    #: revert-all baseline. Deep-copied so it never aliases the live dict.
    _baseline_neighbours = Dict(Str, List(Str))

    #: Undo/redo snapshots of ``svg_model.neighbours`` (deep-copied dicts
    #: of lists), newest last; uncapped, mirroring the zones editor's
    #: history (#596, ``device_viewer/models/zones.py``).
    _undo_stack = List()
    _redo_stack = List()

    #: Fired after each undo snapshot is taken. Zones mirrors the same
    #: event onto the app's pyface CommandStack via ZonesController /
    #: ZoneStateCommand; this dialog is a transient, non-modal window
    #: outside that task's menu/shortcut plumbing, so its history stays
    #: dialog-local instead — see the toolbar buttons and canvas
    #: Ctrl+Z/Ctrl+Shift+Z handling for how it is exposed to the user.
    undo_snapshot_pushed = Event()

    can_undo = Property(Bool, observe="_undo_stack.items")
    can_redo = Property(Bool, observe="_redo_stack.items")

    #: Whether ``revert_all`` would change anything.
    can_revert = Property(Bool, observe="svg_model:neighbours")

    def traits_init(self):
        self._baseline_neighbours = self._copy_neighbours()

    def _get_can_undo(self):
        return bool(self._undo_stack)

    def _get_can_redo(self):
        return bool(self._redo_stack)

    def _get_can_revert(self):
        return self.svg_model.neighbours != self._baseline_neighbours

    # --------------------------------------------------------------- edits
    def add_connection(self, from_id, to_id):
        """Connect two electrodes, snapshotting first so the edit can be
        undone; a self-connection or an existing one changes nothing and
        takes no snapshot."""

        if from_id == to_id or to_id in self.svg_model.neighbours.get(from_id, []):
            return

        self._push_undo()
        self.svg_model.add_connection(from_id, to_id)

    def remove_selected(self):
        if not self.selected_connections:
            return

        self._push_undo()
        self.svg_model.remove_connections(self.selected_connections)
        self.selected_connections = []

    def revert_all(self):
        """Restore the connections to how they were when the dialog opened.
        Itself undoable; a no-op when nothing has changed."""

        if not self.can_revert:
            return

        self._push_undo()
        self._restore(self._copy_neighbours(self._baseline_neighbours))

    # ---------------------------------------------------------------- undo
    def undo(self):
        """Restore the connections before the last add/delete/revert."""

        if not self._undo_stack:
            return False

        state = self._undo_stack[-1]
        self._undo_stack = self._undo_stack[:-1]
        self._redo_stack = self._redo_stack + [self._copy_neighbours()]
        self._restore(state)

        return True

    def redo(self):
        """Re-apply the last undone edit."""

        if not self._redo_stack:
            return False

        state = self._redo_stack[-1]
        self._redo_stack = self._redo_stack[:-1]
        # Directly, not via _push_undo — redo must not clear its own stack.
        self._undo_stack = self._undo_stack + [self._copy_neighbours()]
        self._restore(state)

        return True

    def _push_undo(self):
        self._undo_stack = self._undo_stack + [self._copy_neighbours()]
        # A new edit forks history; the redone future is gone.
        self._redo_stack = []
        self.undo_snapshot_pushed = True

    def _copy_neighbours(self, neighbours=None):
        source = self.svg_model.neighbours if neighbours is None else neighbours
        return {key: list(ids) for key, ids in source.items()}

    def _restore(self, neighbours):
        self.svg_model.neighbours = neighbours
        self.svg_model.connections_modified = True
