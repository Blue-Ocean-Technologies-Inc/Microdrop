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

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import (
    YES,
    confirm,
    error,
    information,
)

# Local imports.
from .ai_install import install_ai_support
from .analysis.roi_model import roi_analysis_model
from .analysis.sam_detect import sam_available
from .consts import PRUNE_EXPERIMENTS_DESCRIPTION
from .discovery import prunable_experiments, prune_experiments

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


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


class PruneExperimentsAction(Action):
    name = Str("Prune Experiments…")
    tooltip = PRUNE_EXPERIMENTS_DESCRIPTION
    description = PRUNE_EXPERIMENTS_DESCRIPTION

    def perform(self, event):
        # The viewer's discovery poll drops the pruned folders from its
        # Experiments list on its next rescan; nothing to refresh here.
        targets = prunable_experiments()

        if not targets:
            information(
                None,
                "No experiments to prune: every experiment folder holds "
                "captures or other data.",
                title="Prune Experiments",
                cancel=False,
            )

            return

        result = confirm(
            parent=None,
            message=f"Delete {len(targets)} experiment folder(s) that hold only logs?",
            title="Prune Experiments",
            informative="This removes the folders from disk and cannot be undone.",
            detail="\n".join(path.name for path in targets),
        )

        if result != YES:
            return

        try:
            removed = prune_experiments(targets)
        except OSError as e:
            logger.exception(f"Failed to prune experiments: {e}")
            error(
                None,
                f"Pruning stopped, could not delete an experiment folder: {e}",
                title="Prune Experiments",
            )

            return

        information(
            None,
            f"Deleted {len(removed)} experiment folder(s).",
            title="Prune Experiments",
            cancel=False,
        )


def help_menu_factory():
    """Help-menu group: the optional AI ROI support installer."""
    return SGroup(InstallAiSupportAction(), id="image_viewer_help_actions")


def prune_menu_factory():
    """File-menu group: bulk removal of experiments holding only logs."""
    return SGroup(PruneExperimentsAction(), id="image_viewer_prune_actions")
