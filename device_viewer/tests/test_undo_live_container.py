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
later reassigned (``model.channels = {...}``, as route playback and phase
navigation do), that container is detached; a command that still edits it
changes nothing visible, which read as "undo does nothing" in the viewer.
"""

# Enthought library imports.
from pyface.undo.api import CommandStack, UndoManager
from traits.api import Bool, HasTraits, Instance, Int, List, Set, Str, observe
from traits.observation.api import ListChangeEvent, SetChangeEvent

# Microdrop package imports.
from device_viewer.utils.commands import ListChangeCommand

# Microdrop utils imports.
from microdrop_utils.trait_change_commands import SetChangeCommand


class Recorded(HasTraits):
    """A model whose set and list edits are pushed onto an undo stack the way
    the device viewer pane records electrode and route changes, including
    the guard that keeps an undo's own edits off the stack."""

    channels = Set(Int)
    route = List(Str)
    stack = Instance(CommandStack)
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

    @observe("channels.items, route.items")
    def _record(self, event):
        if self._undoing:
            return

        if isinstance(event, SetChangeEvent):
            self.stack.push(SetChangeCommand(event=event))
        elif isinstance(event, ListChangeEvent):
            self.stack.push(ListChangeCommand(event=event))


def test_set_undo_edits_the_live_container_after_reassignment():
    model = Recorded()
    model.channels.add(1)

    # Playback / phase navigation swap the container object wholesale.
    model.channels = {1, 6}

    model.undo()

    assert model.channels == {6}


def test_set_redo_edits_the_live_container_after_reassignment():
    model = Recorded()
    model.channels.add(1)
    model.undo()

    model.channels = {6}

    model.redo()

    assert model.channels == {1, 6}


def test_list_undo_edits_the_live_container_after_reassignment():
    model = Recorded()
    model.route.append("a")
    model.route.append("b")

    model.route = ["a", "b"]  # equal content, new container object

    model.undo()

    assert model.route == []
