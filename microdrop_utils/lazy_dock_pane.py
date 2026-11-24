# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dock panes whose contents are built the first time they are shown (#1085).

A pane opts in by listing the mixin before its pyface base::

    class LogPane(LazyContentDockPane, TraitsDockPane):
        ...

Its dock widget is made at launch as pyface makes it — named for the saved
layout, titled, docked where the pane says — so layouts, the View menu,
floating, ``raise_()`` and the staged loader's placeholder swap work as for
any pane. Only its contents wait: the dock shows a muted loading line until
the pane is first painted on screen, then a paced turn builds the contents
with the pane's own ``create_contents`` and puts them in place
(``microdrop_utils.first_show_builder`` says why a paint is the trigger). A
pane visible at launch is so built just after the window's first paint; a
pane behind another tab, closed or hidden is not built until it is shown.

Code that needs the contents before then calls ``ensure_built()`` or
``when_content_built(...)``. A failed build shows its reason in the pane and
is recorded in the application's plugin load status under the pane's id.

A view-layer helper: it imports Qt through ``pyface.qt``.
"""

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, Bool, Event, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR, GREY
from microdrop_style.helpers import is_dark_mode

# Local imports.
from .deferred_content import CONTENT_BUILT, CONTENT_FAILED, DeferredContent
from .first_paint import call_after_first_paint
from .first_show_builder import FirstShowBuilder

#: Text style of a pane's loading or failure line, before the colour.
STATUS_TEXT_STYLE = "font-size: 13pt; padding: 12px;"

#: The loading line's muted colour, by whether the app is in dark mode.
LOADING_TEXT_COLORS = {False: GREY["dark"], True: GREY["lighter"]}

#: Added to a failed pane's reason: where the details are.
FAILURE_HINT = "Click the plugin status icon in the status bar for details."


class LazyContentDockPane(HasTraits):
    """Mixin for a pyface ``DockPane``: build its contents on first show.

    List it before the pane's pyface base class. Never instantiated alone.
    """

    #: The pane's contents: loading until first shown, then built or failed.
    deferred_contents = Instance(DeferredContent)

    #: Builds the contents once the pane is first on screen.
    first_show_builder = Instance(FirstShowBuilder)

    #: True while the built contents are on screen: not before they are
    #: built, and not while the pane is closed or behind another tab
    #: (pyface's ``visible`` stays True behind a tab).
    showing_contents = Bool(False)

    #: Fired once the contents are built and in place.
    contents_built = Event()

    #: Holds the status line, then the built contents.
    _contents_stack = Any()

    #: The loading (or failure) line; None once the contents are in. A plain
    #: label, not a TraitsUI view: every lazy pane makes one at launch, where
    #: a TraitsUI panel costs over ten times as much.
    _status_line = Any()

    def _deferred_contents_default(self):
        return DeferredContent(title=self.name, build=self._build_contents)

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def ensure_built(self):
        """Build the contents now, shown or not. A no-op before the pane is
        created, after it is destroyed, or once the contents are built."""

        if self.first_show_builder is not None:
            self.first_show_builder.ensure_built()

    def when_content_built(self, on_built, on_failed=None):
        """Call ``on_built(contents)`` now, or once the contents are built;
        ``on_failed(error)`` instead if their build fails."""
        self.deferred_contents.when_built(on_built, on_failed)

    # ------------------------------------------------------------------ #
    # 'IDockPane' interface                                               #
    # ------------------------------------------------------------------ #

    def create(self, parent):
        """Create the dock widget as pyface's Qt ``DockPane.create`` does,
        with the status line in place of the contents.

        The pane's own ``create_contents`` runs later, on first show, so
        overriding it is all a pane does to say what its contents are.
        """
        self.control = control = QtWidgets.QDockWidget(parent)

        control.setObjectName(f"{self.task.id}:{self.id}")
        control.setAttribute(QtCore.Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        self._set_dock_features(event=None)
        self._set_dock_title(event=None)
        self._set_floating(event=None)
        self._set_visible(event=None)

        control.dockLocationChanged.connect(self._receive_dock_area)
        control.topLevelChanged.connect(self._receive_floating)
        control.visibilityChanged.connect(self._receive_visible)
        control.visibilityChanged.connect(self._follow_dock_visibility)

        control.setWidget(self._create_status_contents(control))
        self._fit_dock_to(self._contents_stack)

        control.hide()

        self.first_show_builder = FirstShowBuilder(
            contents=self.deferred_contents,
            watch_first_paint=partial(call_after_first_paint, self._contents_stack),
            is_exposed=self._contents_exposed,
        )
        self.first_show_builder.start()

    def destroy(self):
        """Stop any build still to come, then destroy the pane as usual."""

        if self.first_show_builder is not None:
            self.first_show_builder.dispose()

        if self.control is not None:
            self.control.visibilityChanged.disconnect(self._follow_dock_visibility)

        self._status_line = None
        self.showing_contents = False

        super().destroy()

    # ------------------------------------------------------------------ #
    # Private interface                                                   #
    # ------------------------------------------------------------------ #

    def _create_status_contents(self, parent):
        """The stack the contents go in, showing the status line meanwhile."""
        self._contents_stack = stack = QtWidgets.QStackedWidget(parent)

        self._status_line = status_line = QtWidgets.QLabel(stack)
        status_line.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        status_line.setWordWrap(True)
        self._show_status()

        stack.addWidget(status_line)

        return stack

    def _build_contents(self):
        """The pane's own contents, made in their stack."""
        return self.create_contents(self._contents_stack)

    def _contents_exposed(self):
        """Whether any of the pane's contents area is on screen now."""
        stack = self._contents_stack

        return (
            stack is not None
            and stack.isVisible()
            and not stack.visibleRegion().isEmpty()
        )

    def _fit_dock_to(self, contents):
        """Keep the dock no smaller than ``contents`` and its title bar, as
        pyface does when it creates a pane."""
        minimum = contents.minimumSize()
        style = self.control.style()

        minimum.setHeight(
            minimum.height()
            + style.pixelMetric(style.PixelMetric.PM_DockWidgetHandleExtent)
        )
        self.control.setMinimumSize(minimum)

    def _follow_dock_visibility(self, visible):
        """Qt's flag, not ``isVisible()``: it turns False behind a tab."""
        built = self.deferred_contents.state == CONTENT_BUILT

        self.showing_contents = visible and built

    @observe("name")
    def _retitle_contents(self, event):
        self.deferred_contents.title = event.new

    @observe("deferred_contents:status_text")
    def _show_status(self, event=None):
        """Say loading in muted text, or why the build failed in red."""
        status_line = self._status_line

        if status_line is None:
            return

        contents = self.deferred_contents

        if contents.state == CONTENT_FAILED:
            status_line.setText(f"{contents.status_text}\n\n{FAILURE_HINT}")
            status_line.setStyleSheet(f"{STATUS_TEXT_STYLE} color: {ERROR_COLOR};")
            status_line.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )

        else:
            color = LOADING_TEXT_COLORS[is_dark_mode()]

            status_line.setText(contents.status_text)
            status_line.setStyleSheet(f"{STATUS_TEXT_STYLE} color: {color};")

    @observe("deferred_contents:state")
    def _show_contents_state(self, event):

        if event.new == CONTENT_BUILT:
            self._swap_in_contents(self.deferred_contents.content)

        elif event.new == CONTENT_FAILED:
            self._record_build_failure()

    def _swap_in_contents(self, contents):
        """Put the built contents where the status line was."""
        stack = self._contents_stack

        stack.addWidget(contents)
        stack.setCurrentWidget(contents)

        status_line, self._status_line = self._status_line, None
        stack.removeWidget(status_line)
        status_line.deleteLater()

        self._fit_dock_to(contents)

        self.showing_contents = self._contents_exposed()
        self.contents_built = True

    def _record_build_failure(self):
        """List the failure with the plugin load records, under the pane's
        id, so the status bar's plugin icon reports it."""
        window = getattr(self.task, "window", None)
        load_status = getattr(
            getattr(window, "application", None), "plugin_load_status", None
        )
        contents = self.deferred_contents

        if load_status is None:
            return

        load_status.mark_failed(
            self.id, contents.error, contents.error_traceback, name=f"{self.name} pane"
        )
