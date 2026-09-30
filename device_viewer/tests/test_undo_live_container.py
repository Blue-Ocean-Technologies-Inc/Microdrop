# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Undo commands must act on the container the trait holds now.

A Set/ListChangeEvent carries the container object itself. When the trait is
later reassigned (``model.channels = {...}``), that container is detached; a
command that still edits it changes nothing visible, which read as "undo does
nothing" in the viewer. Route playback makes exactly such reassignments while
the pane is not recording, so the earlier click and draw commands must still
find the live container afterwards.
"""

# Standard library imports.
from contextlib import contextmanager

# Enthought library imports.
from pyface.undo.api import CommandStack, UndoManager
from traits.api import Bool, HasTraits, Instance, Int, List, Set, Str, observe
from traits.observation.api import ListChangeEvent, SetChangeEvent, TraitChangeEvent

# Microdrop package imports.
from device_viewer.utils.commands import ListChangeCommand, TraitChangeCommand

# Microdrop utils imports.
from microdrop_utils.trait_change_commands import SetChangeCommand


class Recorded(HasTraits):
    """A model whose set and list changes are pushed onto an undo stack the
    way the device viewer pane records them: mutations and reassignments
    alike, except while undoing or while recording is suspended (as the pane
    suspends it during route playback)."""

    channels = Set(Int)
    route = List(Str)
    stack = Instance(CommandStack)
    recording = Bool(True)
    _undoing = Bool(False)

    def _stack_default(self):
        manager = UndoManager(active_stack=CommandStack())
        manager.active_stack.undo_manager = manager

        return manager.active_stack

    def undo(self):
        self._undoing = True

        try:
            self.stack.undo()
        finally:
            self._undoing = False

    def redo(self):
        self._undoing = True

        try:
            self.stack.redo()
        finally:
            self._undoing = False

    @contextmanager
    def playback(self):
        """Changes made inside are not recorded, like route playback's."""
        self.recording = False

        try:
            yield
        finally:
            self.recording = True

    @observe("channels.items, route.items")
    def _record(self, event):
        if self._undoing or not self.recording:
            return

        if isinstance(event, SetChangeEvent):
            self.stack.push(SetChangeCommand(event=event))
        elif isinstance(event, ListChangeEvent):
            self.stack.push(ListChangeCommand(event=event))
        elif isinstance(event, TraitChangeEvent):
            self.stack.push(TraitChangeCommand(event=event))


def test_set_undo_survives_an_unrecorded_reassignment():
    model = Recorded()
    model.channels.add(1)

    with model.playback():
        model.channels = {1, 6}

    model.undo()

    assert model.channels == {6}


def test_set_redo_survives_an_unrecorded_reassignment():
    model = Recorded()
    model.channels.add(1)
    model.undo()

    with model.playback():
        model.channels = {6}

    model.redo()

    assert model.channels == {1, 6}


def test_list_undo_survives_an_unrecorded_reassignment():
    model = Recorded()
    model.route.append("a")
    model.route.append("b")

    with model.playback():
        model.route = ["a", "b"]  # equal content, new container object

    model.undo()

    assert model.route == []


def test_recorded_reassignment_is_its_own_undo_step():
    model = Recorded()
    model.channels.add(1)
    model.channels = {1, 6}

    model.undo()
    assert model.channels == {1}

    model.undo()
    assert model.channels == set()
