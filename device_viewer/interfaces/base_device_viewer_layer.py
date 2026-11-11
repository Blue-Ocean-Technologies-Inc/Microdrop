# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""No-op defaults for the device viewer layer contract (#650)."""

# Enthought library imports.
from traits.api import HasTraits, Instance, Int, List, Str, provides

# Local imports.
from .descriptors import AlphaEntry, InteractionMode
from .i_device_viewer_layer import IDeviceViewerLayer
from .i_interaction_handler import IInteractionHandler
from .i_svg_layer_codec import ISvgLayerCodec
from .layer_context import LayerContext


@provides(IDeviceViewerLayer)
class BaseDeviceViewerLayer(HasTraits):
    """A layer with every facet empty; override only what a layer needs.

    ``attach`` keeps the context in ``context`` and ``detach`` drops it, so
    an override calls ``super()`` first in ``attach`` and last in
    ``detach``.
    """

    #: Stable id ("zones", "gamepad"); one layer per id is attached.
    id = Str()

    #: The ``LAYER_CONTRACT_VERSION`` the layer was built against; empty when
    #: undeclared. The base warns, and still mounts the layer, when it differs.
    contract_version = Str()

    #: Order of the layer's sidebar section after the built-in ones.
    priority = Int(50)

    #: Rows the layer adds to the layer-opacity table.
    alpha_entries = List(Instance(AlphaEntry))

    #: Values the layer adds to ``model.mode``.
    modes = List(Instance(InteractionMode))

    #: Behaviour for ``modes``; None for a layer without modes.
    interaction_handler = Instance(IInteractionHandler, allow_none=True)

    #: The layer's group in the device SVG; None if it stores nothing there.
    svg_codec = Instance(ISvgLayerCodec, allow_none=True)

    #: The pane this layer is attached to; None while detached.
    context = Instance(LayerContext)

    def attach(self, context):
        self.context = context

    def on_device_loaded(self, electrodes):
        pass

    def detach(self):
        self.context = None

    def build_sidebar_section(self, parent):
        return None

    def on_alpha_changed(self, key, opacity):
        pass

    def contribute_state(self, payload):
        pass

    def apply_state(self, message):
        pass
