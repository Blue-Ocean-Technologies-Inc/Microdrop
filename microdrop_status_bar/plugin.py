# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""
StatusBarPlugin — the one home for the application status bar.

Creates the window's StatusBarManager and owns the ``status_bar_icons``
extension point: other plugins contribute QWidget instances (typically at
runtime, from their dock panes) and this plugin places them in a single
icon container whose QHBoxLayout gives every icon the same gap, or, for a
widget marked ``status_bar_side = STATUS_BAR_SIDE_LEFT``, on the bar's
left, before the mode/step label. Removing a widget from the extension point
removes it from the bar and deletes it.

Dynamic contribution handling mirrors MessageRouterPlugin: apply the
current extensions once the container exists, then react to
``<name>_items`` delta events for runtime (hot load/unload) changes.
"""

# Enthought library imports.
from envisage.api import ExtensionPoint, Plugin
from pyface.qt.QtGui import QHBoxLayout, QWidget
from traits.api import Any, List, observe, on_trait_change

# Microdrop utils imports.
from microdrop_utils.pyface_helpers import StatusBarManager

# Local imports.
from .consts import (
    DEFAULT_STATUS_MESSAGE,
    ICON_PRIORITY_DEFAULT,
    ICON_SPACING,
    PKG,
    STATUS_BAR_CONTENTS_MARGINS,
    STATUS_BAR_ICONS,
    STATUS_BAR_SIDE_LEFT,
    PKG_name,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class StatusBarPlugin(Plugin):
    """Creates the app status bar and manages contributed status icons."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    status_bar_icons = ExtensionPoint(
        List(),
        id=STATUS_BAR_ICONS,
        desc="QWidget instances to show in the app status bar; this plugin "
        "owns their placement, spacing, and removal",
    )

    #: Single container appended to the status bar; its HBox layout gives
    #: every contributed icon the same gap.
    _icon_container = Any(None)

    #: The window's status bar, its persistent mode/step label, and the
    #: contributed widgets on its left, in arrival order before the label.
    _status_bar = Any(None)
    _persistent_label = Any(None)
    #: Container for the left widgets, inserted before the label; its HBox
    #: layout spaces them like the right-hand icons and trails one gap.
    _left_container = Any(None)
    _left_widgets = List()

    def start(self):
        # Wire the registry's extension-point listeners to this plugin's
        # traits so the handlers below fire when contributions change at
        # runtime. Opt-in (envisage never calls it for you), and only
        # possible once the plugin is attached to the application.
        self.connect_extension_point_traits()

    @observe("application:application_initialized")
    def _setup_status_bar(self, event):
        """Build the status bar once windows and their pane contents exist.

        Deliberately NOT ``application:active_window``: that fires on the
        first Qt focus-activation, mid ``window.open()`` — before dock-pane
        contents are created (their status-bar observers would run against
        half-built panes), and before the task-activation sweep (pyface
        ``TaskWindow._update_traits_given_new_active_state``) overwrites
        ``window.status_bar_manager`` with ``task.status_bar`` (None),
        discarding anything installed earlier. ``application_initialized``
        is set via ``set_trait_later`` after ``_create_windows()`` returns,
        so both hazards are past.
        """
        windows = self.application.windows
        window = self.application.active_window or (windows[0] if windows else None)
        if window is None or self._icon_container is not None:
            return
        if window.status_bar_manager is None:
            window.status_bar_manager = StatusBarManager(
                messages=[DEFAULT_STATUS_MESSAGE], size_grip=True
            )
        status_bar = window.status_bar_manager.status_bar
        status_bar.setContentsMargins(*STATUS_BAR_CONTENTS_MARGINS)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ICON_SPACING)
        # One container, appended once; icons order INSIDE it by their
        # ``status_bar_icon_priority`` attribute (see consts).
        status_bar.addPermanentWidget(container)
        self._icon_container = container
        self._status_bar = status_bar
        self._persistent_label = getattr(
            window.status_bar_manager, "persistent_label", None
        )

        left_container = QWidget()
        left_layout = QHBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, ICON_SPACING, 0)
        left_layout.setSpacing(ICON_SPACING)
        left_container.setVisible(False)
        status_bar.insertWidget(self._label_index(), left_container)
        self._left_container = left_container

        # Contributions made before the window existed already sit in the
        # extension point — apply them now; the _items handler below keeps
        # the bar in sync from here on.
        self._apply_icon_changes(added=self.status_bar_icons, removed=[])

    # ------------------------------------------------------------------ #
    # Extension-point sync                                                 #
    # ------------------------------------------------------------------ #

    def _apply_icon_changes(self, added, removed):
        """Apply contribution deltas to the icon container and the left side."""
        if self._icon_container is None:
            return  # no window yet; current extensions applied at setup
        try:
            layout = self._icon_container.layout()
        except RuntimeError as e:  # container died with the window (app exit)
            logger.debug(f"status-bar icon container gone: {e}")
            self._icon_container = None
            self._status_bar = None
            self._persistent_label = None
            self._left_container = None
            self._left_widgets = []
            return

        for widget in removed:
            try:
                if widget in self._left_widgets:
                    self._left_widgets.remove(widget)
                    self._left_container.layout().removeWidget(widget)

                else:
                    layout.removeWidget(widget)

                widget.deleteLater()
            except RuntimeError as e:
                logger.debug(f"status-bar icon already deleted: {e}")

        for widget in added:
            if getattr(widget, "status_bar_side", None) == STATUS_BAR_SIDE_LEFT:
                self._left_container.layout().addWidget(widget)
                self._left_widgets.append(widget)

            else:
                layout.insertWidget(self._insert_index(layout, widget), widget)

        self._left_container.setVisible(bool(self._left_widgets))

        logger.info(
            f"status bar icons changed: +{len(added)} -{len(removed)}; "
            f"{layout.count() + len(self._left_widgets)} in the bar"
        )

    def _label_index(self):
        """Slot of the persistent mode/step label in the status bar (the
        bar's start if the label is not found)."""
        widgets = list(_layout_widgets(self._status_bar.layout()))
        label = self._persistent_label

        return widgets.index(label) if label in widgets else 0

    @staticmethod
    def _insert_index(layout, widget):
        """Slot for ``widget`` in the priority-ordered container: before the
        first icon with a strictly greater ``status_bar_icon_priority``, so
        equal priorities keep arrival order (lower priority = further left).
        """
        priority = getattr(widget, "status_bar_icon_priority", ICON_PRIORITY_DEFAULT)
        for i in range(layout.count()):
            other = layout.itemAt(i).widget()
            if priority < getattr(
                other, "status_bar_icon_priority", ICON_PRIORITY_DEFAULT
            ):
                return i
        return layout.count()

    @on_trait_change("status_bar_icons_items")
    def _on_status_bar_icons_items_changed(self, event):
        """A contribution changed while the app is running.

        Plugin-driven changes (a contributing plugin mutating its
        contribution trait, plugins added/removed from the manager) always
        carry an index, which ExtensionPoint.connect surfaces as this
        synthetic "<name>_items" property event. No real
        ``status_bar_icons_items`` trait exists, so the string-matched
        on_trait_change must bind it — observe() rejects unknown names.
        """
        self._apply_icon_changes(event.added, event.removed)

    @observe("status_bar_icons")
    def _on_status_bar_icons_replaced(self, event):
        """Index-less wholesale replacement of the extension point
        (registry.set_extensions) — never fired for plugin contribution
        changes; covered for completeness."""
        self._apply_icon_changes(added=event.new, removed=event.old)


def _layout_widgets(layout):
    """The widgets of ``layout`` and its nested layouts, in order: a
    QStatusBar lays its widgets out in its own insertion order."""
    for index in range(layout.count()):
        item = layout.itemAt(index)

        if item.widget() is not None:
            yield item.widget()

        elif item.layout() is not None:
            yield from _layout_widgets(item.layout())
