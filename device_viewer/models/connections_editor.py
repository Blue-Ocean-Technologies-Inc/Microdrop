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
from traits.api import HasTraits, Instance, List, Str, Tuple

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

    def remove_selected(self):
        self.svg_model.remove_connections(self.selected_connections)
        self.selected_connections = []
