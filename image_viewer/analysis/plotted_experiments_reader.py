# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Read plotted experiments' saved analyses off the GUI thread (#1086).

One experiment's analysis can take a second to read, and the plotted set
grows with every experiment shown (#1072), so reading them as the image
viewer mounted froze the window. The reader works through them on a
worker thread and hands them back on the GUI thread, the ones read
meanwhile together — up to PLOTTED_EXPERIMENTS_PER_TURN — one paced
turn per hand-back.

Qt-free: the hand-back goes through ``GUI.invoke_later`` and
``invoke_paced``.
"""

# Standard library imports.
import threading
import time

# Enthought library imports.
from pyface.api import GUI
from traits.api import Callable, HasTraits, List

# Microdrop utils imports.
from microdrop_utils.gui_pacing import invoke_paced

# Local imports.
from .consts import (
    PLOTTED_EXPERIMENTS_PER_TURN,
    PLOTTED_EXPERIMENTS_READER_REST_S,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PlottedExperimentsReader(HasTraits):
    """Reads experiments' saved analyses on a worker thread."""

    #: directory -> the ImportedExperiment read from it; runs on the
    #: worker thread, so it must not touch anything the GUI thread uses.
    load = Callable()

    #: Called on the GUI thread with the (loading experiment, experiment
    #: read for it — None when it could not be read) pairs read since the
    #: last call.
    on_read = Callable()

    #: The pairs read and not handed back yet.
    _arrived = List()

    def read(self, loading):
        """Read the saved analysis of each of the ``loading`` experiments,
        in order."""
        directories = [experiment.directory for experiment in loading]

        def read_each():
            for experiment, directory in zip(loading, directories):
                try:
                    read_experiment = self.load(directory)
                except Exception as error:
                    # One unreadable folder must not stop the rest.
                    logger.error(f"Could not read experiment {directory}: {error}")
                    read_experiment = None

                GUI.invoke_later(self._arrive, experiment, read_experiment)

                # Reading holds the GIL: left to run on, it halves the
                # speed of the GUI thread, filling in the panes meanwhile.
                time.sleep(PLOTTED_EXPERIMENTS_READER_REST_S)

        threading.Thread(
            target=read_each, name="plotted-experiments", daemon=True
        ).start()

    def _arrive(self, loading, read_experiment):
        """Keep a pair read; the first since the last hand-back schedules
        the next, so the pairs read meanwhile join it."""
        self._arrived.append((loading, read_experiment))

        if len(self._arrived) == 1:
            invoke_paced(self._hand_back)

    def _hand_back(self):
        """Hand back the oldest pairs, up to PLOTTED_EXPERIMENTS_PER_TURN;
        the rest wait for the next paced turn."""
        count = PLOTTED_EXPERIMENTS_PER_TURN
        arrived, self._arrived = self._arrived[:count], self._arrived[count:]

        if self._arrived:
            invoke_paced(self._hand_back)

        self.on_read(arrived)
