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
from envisage.api import (
    PREFERENCES_CATEGORIES,
    PREFERENCES_PANES,
    TASK_EXTENSIONS,
    ExtensionPoint,
    Plugin,
)
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import Callable, List, Str, on_trait_change

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG
from microdrop_status_bar.consts import STATUS_BAR_ICONS

# Local imports.
from .consts import (
    ACTOR_TOPIC_DICT,
    CAMERA_SOURCES,
    DEVICE_VIEWER_LAYERS,
    PKG,
    PKG_name,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class DeviceViewerPlugin(Plugin):
    """The device viewer: its dock panes, preferences, and extension points."""

    #### 'IPlugin' interface ##################################################

    # The plugin's unique identifier.
    id = PKG

    # The plugin's name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    #### Contributions to extension points made by this plugin ################
    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    #: Status-bar widgets contributed at runtime: the device-viewer dock
    #: pane extends this list (the recording icon); the
    #: microdrop_status_bar plugin places, spaces, and removes them.
    status_bar_icons = List(contributes_to=STATUS_BAR_ICONS)

    #: Extra camera sources (e.g. the fluorescence plugin's ASI cameras):
    #: zero-arg provider factories, rendered through the same video layer
    #: as QtMultimedia cameras. See consts.CAMERA_SOURCES for the contract.
    camera_sources = ExtensionPoint(
        List,
        id=CAMERA_SOURCES,
        desc="Zero-arg factories returning camera-source providers for the "
        "device viewer's video layer",
    )

    #: Device viewer layers (#650): zero-arg factories returning an
    #: IDeviceViewerLayer, contributed by sibling plugins with
    #: ``List(contributes_to=DEVICE_VIEWER_LAYERS)``. The live pane builds
    #: one layer per factory and follows plugins loaded or unloaded later.
    layers = ExtensionPoint(
        List(Callable),
        id=DEVICE_VIEWER_LAYERS,
        desc="Zero-arg factories returning the IDeviceViewerLayer instances "
        "mounted on the device viewer pane",
    )

    def start(self):
        """Follow layer contributions that change while the app runs."""
        super().start()

        # Opt-in, and only possible once attached to the application: the
        # ``_items`` handler below fires only after this connects it.
        self.connect_extension_point_traits()

        # The registry reports changes only to extension points it has
        # already resolved, so resolve this one now.
        logger.debug(f"Device viewer layers contributed at start: {len(self.layers)}")

    @on_trait_change("layers_items")
    def _on_layers_changed(self, event):
        """A plugin contributing layers was loaded or unloaded at runtime.

        The synthetic ``_items`` event needs ``on_trait_change``: observe()
        rejects the name, as no such trait exists. A pane not built yet
        reads the current contributions when it is.
        """
        logger.info(
            f"Device viewer layers changed: +{len(event.added)} -{len(event.removed)}"
        )

        pane = self._live_dock_pane()

        if pane is not None and pane.layer_host is not None:
            pane.layer_host.apply_change(added=event.added, removed=event.removed)

    def _live_dock_pane(self):
        """Return the mounted device viewer pane, or None."""
        window = getattr(self.application, "active_window", None)

        if window is None:
            windows = getattr(self.application, "windows", None) or []
            window = windows[0] if windows else None

        if window is None:
            return None

        return window.get_dock_pane(PKG + ".dock_pane")

    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _preferences_panes_default(self):
        from .preferences import (
            DeviceViewerAdvancedPreferencesPane,
            DeviceViewerPreferencesPane,
        )
        from .views.camera_control_view.preferences import CameraPreferencesPane

        return [
            DeviceViewerPreferencesPane,
            CameraPreferencesPane,
            DeviceViewerAdvancedPreferencesPane,
        ]

    def _preferences_categories_default(self):
        from .preferences import device_viewer_tab
        from .views.camera_control_view.preferences import video_settings_tab

        return [device_viewer_tab, video_settings_tab]

    def _contributed_task_extensions_default(self):
        from .menus import tools_menu_factory
        from .views.device_view_dock_pane import DeviceViewerDockPane
        from .views.video_viewer.dock_pane import VideoViewerDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[DeviceViewerDockPane, VideoViewerDockPane],
                actions=[
                    SchemaAddition(
                        factory=tools_menu_factory,
                        path="MenuBar/File",
                        before="Exit",
                    ),
                ],
            )
        ]
