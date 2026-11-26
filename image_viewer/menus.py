# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from functools import partial

# Enthought library imports.
from pyface.action.api import Action
from pyface.action.schema.api import SGroup
from traits.api import Instance, Str, observe

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import YES, confirm, information

# Microdrop utils imports.
from microdrop_utils.environment_update_dialog import (
    offer_environment_update,
    report_package_still_missing,
)

# Local imports.
from .ai_install import install_ai_support
from .analysis.roi_model import roi_analysis_model
from .analysis.sam_detect import sam_available
from .consts import PRUNE_EXPERIMENTS_DESCRIPTION, TRASH_FEATURE, TRASH_PACKAGE
from .discovery import prunable_experiments
from .prune_job import PruneExperimentsJob, prune_experiments_job
from .view import show_image_viewer_shortcuts

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


class KeyboardShortcutsAction(Action):
    name = Str("Image Viewer &Keyboard Shortcuts…")
    tooltip = "List the keys the image view answers to while it has focus"

    def perform(self, event):
        show_image_viewer_shortcuts()


class PruneExperimentsAction(Action):
    name = Str("Prune Experiments…")
    tooltip = PRUNE_EXPERIMENTS_DESCRIPTION
    description = PRUNE_EXPERIMENTS_DESCRIPTION

    #: Moves the confirmed folders to the trash off the GUI thread.
    job = Instance(PruneExperimentsJob)

    @observe("job.running")
    def _disable_while_pruning(self, event):
        """Grey the action out while a prune runs, so no second one starts."""
        self.enabled = not self.job.running

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
            informative="The folders are moved to the Recycle Bin (Trash on "
            "macOS/Linux), where they can be restored.",
            detail="\n".join(path.name for path in targets),
        )

        if result != YES:
            return

        self._prune(targets, event)

    def _prune(self, targets, event, retry=True):
        """Move the confirmed ``targets`` to the trash in the background; a
        notification card reports how it went. Without send2trash, offer the
        environment update and, when it makes the package available, try
        once more."""
        self.job.start(
            targets, partial(self._offer_trash_update, targets, event, retry)
        )

    def _offer_trash_update(self, targets, event, retry):
        """Offer the environment update send2trash needs, then prune again
        if it makes the package available; on a retry, say it is still
        missing."""
        window = getattr(getattr(event, "task", None), "window", None)
        application = getattr(window, "application", None)

        if not retry:
            report_package_still_missing(TRASH_PACKAGE)
        elif offer_environment_update(
            TRASH_FEATURE, TRASH_PACKAGE, application=application
        ):
            self._prune(targets, event, retry=False)


def help_menu_factory():
    """Help-menu group: the keyboard shortcut sheet and the optional AI ROI
    support installer."""
    return SGroup(
        KeyboardShortcutsAction(),
        InstallAiSupportAction(),
        id="image_viewer_help_actions",
    )


def prune_menu_factory():
    """File-menu group: bulk removal of experiments holding only logs."""
    return SGroup(
        PruneExperimentsAction(job=prune_experiments_job),
        id="image_viewer_prune_actions",
    )
