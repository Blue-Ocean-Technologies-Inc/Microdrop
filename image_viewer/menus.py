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
from pyface.action.api import Action
from pyface.action.schema.api import SGroup
from traits.api import Str

# Local imports.
from .ai_install import install_ai_support
from .analysis.roi_model import roi_analysis_model
from .analysis.sam_detect import sam_available


class InstallAiSupportAction(Action):
    name = Str("Install &AI ROI Support...")
    tooltip = "Install the SAM segmentation stack (osam) with pixi"

    def perform(self, event):
        if install_ai_support():
            # sam_available() retries the osam import in-process, so a
            # successful install becomes usable without an app restart;
            # a failed/partial install (returns False) still leaves the
            # toolbar disabled instead of lying about availability.
            roi_analysis_model.ai_available = sam_available()


def help_menu_factory():
    """Help-menu group: the optional AI ROI support installer."""
    return SGroup(InstallAiSupportAction(), id="image_viewer_help_actions")
