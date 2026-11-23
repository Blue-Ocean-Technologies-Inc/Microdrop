# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The dock pane that stands in for a deferred plugin's pane while it loads.

It carries the real pane's id, so the window's saved layout places it, and
the real pane takes its place when the plugin has loaded
(``add_dock_pane_live`` replaces a pane mounted under the same id). Runs
standalone against just its model::

    PlaceholderPaneModel(pane_name="Image Viewer").edit_traits(
        view=placeholder_pane_view()
    )
"""

# Enthought library imports.
from pyface.tasks.api import TraitsDockPane
from traits.api import Instance
from traitsui.api import HGroup, UItem, VGroup, View, spring

# Microdrop style imports.
from microdrop_style.helpers import is_dark_mode

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import LOAD_FAILED

# Local imports.
from .consts import (
    PLACEHOLDER_LOADING_COLORS,
    PLACEHOLDER_TEXT_STYLE,
    PLUGIN_LOAD_STATE_COLORS,
)
from .placeholder_pane_model import PlaceholderPaneModel


def _message_item(color, visible_when):
    """The centred, wrapping message in ``color``."""
    return HGroup(
        spring,
        UItem(
            "message",
            style="readonly",
            resizable=True,
            visible_when=visible_when,
            style_sheet=f"{PLACEHOLDER_TEXT_STYLE} color: {color};",
        ),
        spring,
    )


def placeholder_pane_view():
    """The placeholder's view, muted for the current colour scheme."""
    return View(
        VGroup(
            spring,
            _message_item(PLACEHOLDER_LOADING_COLORS[is_dark_mode()], "not failed"),
            _message_item(PLUGIN_LOAD_STATE_COLORS[LOAD_FAILED], "failed"),
            spring,
        ),
    )


class DeferredPanePlaceholder(TraitsDockPane):
    """Holds a deferred pane's place, and says it is loading or has failed.

    Created with the real pane's ``id``, ``name``, ``dock_area`` and
    ``visible`` as the run configuration declares them.
    """

    #: The pane's name and its plugin's load record.
    model = Instance(PlaceholderPaneModel)

    def default_traits_view(self):
        return placeholder_pane_view()
