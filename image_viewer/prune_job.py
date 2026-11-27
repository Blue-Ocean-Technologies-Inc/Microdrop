# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""File › Prune Experiments' worker (#1197): moves the confirmed experiment
folders to the trash off the GUI thread, so the window stays usable, and
reports the outcome as a notification card rather than a dialog.

Qt-free: the card is posted over pub/sub, which any thread may do; only the
end of the job is handed back to the GUI thread, through
``GUI.invoke_later``.
"""

# Standard library imports.
from threading import Thread

# Enthought library imports.
from pyface.api import GUI
from traits.api import Bool, HasTraits

# Microdrop package imports.
from notifications.consts import (
    LOG_RECORDED_EXTRA,
    SEVERITY_ERROR,
    SEVERITY_SUCCESS,
    notification_publisher,
)

# Local imports.
from .consts import PKG, PRUNE_EXPERIMENTS_CATEGORY_ID
from .discovery import TrashUnavailableError, prune_experiments

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PruneExperimentsJob(HasTraits):
    """Moves experiment folders to the trash on a worker thread, one prune
    at a time."""

    #: A prune is under way. Set and cleared on the GUI thread only, so the
    #: menu action can follow it.
    running = Bool(False)

    def start(self, targets, on_trash_unavailable):
        """Move ``targets`` to the trash on a worker thread and post the
        outcome as a card. Without send2trash nothing moves, no card is
        posted, and ``on_trash_unavailable()`` is called on the GUI thread
        once the job has ended."""
        self.running = True

        Thread(
            target=self._prune,
            args=(targets, on_trash_unavailable),
            name="prune-experiments",
            daemon=True,
        ).start()

    def _prune(self, targets, on_trash_unavailable):
        """Worker thread: trash ``targets`` and report how it went, in a card
        and in the log, which keeps it when no notifications plugin is
        loaded."""
        removed = []
        then = None

        try:
            for directory in prune_experiments(targets):
                removed.append(directory)
        except TrashUnavailableError:
            then = on_trash_unavailable
        except Exception as e:
            # A trash failure (OSError) or a bug alike: the error card reports
            # it, so the log forwarder must not repeat it.
            logger.exception(
                f"Pruning experiments stopped after {len(removed)} folder(s): {e}",
                extra=LOG_RECORDED_EXTRA,
            )
            notification_publisher.publish(prune_failed_card(e, removed))
        else:
            logger.info(f"Moved {len(removed)} experiment folder(s) to the trash")
            notification_publisher.publish(pruned_card(removed))
        finally:
            GUI.invoke_later(self._finish, then)

    def _finish(self, then):
        """GUI thread: end the job, then call ``then`` if given."""
        self.running = False

        if then is not None:
            then()


def pruned_card(removed):
    """The notification for the ``removed`` experiment folders, now in the
    trash."""
    names = "\n".join(directory.name for directory in removed)

    return {
        "title": f"Moved {len(removed)} experiment folder(s) to the trash",
        "detail": f"They can be restored from the Recycle Bin / Trash.\n{names}",
        "severity": SEVERITY_SUCCESS,
        "source": PKG,
        "category_id": PRUNE_EXPERIMENTS_CATEGORY_ID,
    }


def prune_failed_card(error, removed):
    """The notification for a prune that stopped on ``error`` after moving
    the ``removed`` experiment folders to the trash."""
    return {
        "title": "Pruning experiments stopped",
        "detail": f"{len(removed)} experiment folder(s) had been moved to the "
        f"trash when it stopped on this error: {error}",
        "severity": SEVERITY_ERROR,
        "source": PKG,
        "category_id": PRUNE_EXPERIMENTS_CATEGORY_ID,
    }


#: The one job every Prune Experiments action shares, so a second window
#: cannot start a prune while another runs.
prune_experiments_job = PruneExperimentsJob()
