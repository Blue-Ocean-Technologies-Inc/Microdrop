# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The protocol tree's TimelineBar reused as the phase timeline: one cell per
phase of the selected path, click or drag to seek. The bar is a pure view; a
Qt-free bridge pushes the model's phase titles and step into it, and the
bar's seek signal writes ``step`` back."""

# Enthought library imports.
from traits.api import Any, HasTraits, Instance, observe

# Microdrop package imports.
from pluggable_protocol_tree.views.timeline_bar import TimelineBar

# Local imports.
from .models import WidePathDemoModel


class _TimelineBridge(HasTraits):
    model = Instance(WidePathDemoModel)
    bar = Any

    @observe("model:phase_titles")
    def _titles_changed(self, event):
        self.bar.rebuild(self.model.phase_titles)
        self._push_position()

    @observe("model:step")
    def _step_changed(self, event):
        self._push_position()

    def _push_position(self):
        total = len(self.model.phase_titles)
        self.bar.set_position(self.model.step if total else -1, total, 0, 0)


def timeline_factory(parent, editor):
    """``CustomEditor`` widget factory over the demo model."""
    model = editor.object
    bar = TimelineBar()
    bar.step_seek_requested.connect(lambda index: setattr(model, "step", index))
    # The bridge must outlive this call; the bar keeps it alive.
    bar.bridge = _TimelineBridge(model=model, bar=bar)
    bar.bridge._titles_changed(None)
    return bar
