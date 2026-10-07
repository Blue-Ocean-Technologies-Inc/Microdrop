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
from traits.api import List

# Microdrop package imports.
from microdrop_application.consts import PKG as microdrop_application_PKG
from user_help_plugin.consts import TUTORIALS, TutorialEntry

# Local imports.
from .consts import ANALYSIS_HELP_HTML_PATH, IMAGE_FILTERS, PKG, PKG_name


class ImageViewerPlugin(Plugin):
    """Browse an experiment's captured images and measure regions of
    interest across them: the Image Viewer and ROI Intensities panes."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    #: Filename-derived filters for the image list (e.g. LED wavelength).
    #: See consts.IMAGE_FILTERS for the contract.
    image_filters = ExtensionPoint(
        List, id=IMAGE_FILTERS, desc="Filename-derived filters for the image list"
    )

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    #: Help > Tutorials entries for this plugin's panes.
    tutorials = List(contributes_to=TUTORIALS)

    def _tutorials_default(self):
        return [
            TutorialEntry(title="Image Analysis Tutorial", path=ANALYSIS_HELP_HTML_PATH)
        ]

    def _contributed_task_extensions_default(self):
        from pyface.action.schema.api import SchemaAddition

        from .analysis.plot_pane import RoiPlotDockPane
        from .dock_pane import ImageViewerDockPane
        from .menus import help_menu_factory

        return [
            TaskExtension(
                task_id=f"{microdrop_application_PKG}.task",
                dock_pane_factories=[ImageViewerDockPane, RoiPlotDockPane],
                actions=[
                    SchemaAddition(factory=help_menu_factory, path="MenuBar/Help")
                ],
            )
        ]

    def _preferences_panes_default(self):
        from .preferences import ImageViewerPreferencesPane

        return [ImageViewerPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import image_viewer_tab

        return [image_viewer_tab]

    def start(self):
        from .preferences import migrate_legacy_preferences

        migrate_legacy_preferences(self.application.preferences)
