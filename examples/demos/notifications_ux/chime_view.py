# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The bell's chime: a short sound as the bell rings for a new arrival.

Driven by the pane model's ``rang`` event, so it hears exactly what the
toasts decided is news: no start-up history, no repeats, nothing quiet mode
holds. A burst makes one sound. The sound effects are made on first use and
play asynchronously; with no multimedia module or audio device the chime
logs one warning and stays silent.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt import QtCore
from traits.api import Any, Bool, Dict, Float, HasTraits, Instance, observe

# Microdrop package imports.
from notifications.consts import SEVERITY_ERROR, SEVERITY_WARNING

# Microdrop style imports.
from microdrop_style.sounds.chimes import CHIME_ALERT, CHIME_GENTLE

# Local imports.
from .ux_models import UxPaneModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Least time (s) between two chimes: a burst or a flood makes one sound.
CHIME_MIN_INTERVAL_S = 1.5

#: Delay (ms) between the two chimes the settings' Test button plays.
TEST_GAP_MS = 700


def chime_for(entry):
    """The alert chime for a warning, an error or Needs attention; the
    gentle one for the rest, news included."""
    urgent = entry.severity in (SEVERITY_WARNING, SEVERITY_ERROR)

    return CHIME_ALERT if urgent or entry.needs_attention else CHIME_GENTLE


class NotificationChime(HasTraits):
    """Plays the chime the pane model's ``rang`` calls for, as the toast
    settings allow."""

    pane_model = Instance(UxPaneModel)

    #: QSoundEffects by sound path, made on first use.
    _effects = Dict()

    #: time.monotonic() of the last chime.
    _last_played = Float(-CHIME_MIN_INTERVAL_S)

    #: Set once sound proved unavailable: warned once, then silent.
    _unavailable = Bool(False)

    #: The QtMultimedia module, once imported.
    _multimedia = Any()

    @observe("pane_model:rang")
    def _ring(self, event):
        settings = self.pane_model.toasts.settings
        now = time.monotonic()

        if not settings.sound_enabled or now - self._last_played < CHIME_MIN_INTERVAL_S:
            return

        self._last_played = now
        self.play(chime_for(event.new))

    @observe("pane_model:toasts:settings:test_sound")
    def _test(self, event):
        """Both chimes, gentle then alert, at the chosen volume."""
        self.play(CHIME_GENTLE)
        QtCore.QTimer.singleShot(TEST_GAP_MS, lambda: self.play(CHIME_ALERT))

    def play(self, path):
        """Start ``path`` playing at the settings' volume; returns at once."""
        effect = self._effect(path)

        if effect is not None:
            effect.setVolume(self.pane_model.toasts.settings.sound_volume / 100)
            effect.play()

    def _effect(self, path):
        effect = self._effects.get(path)

        if effect is not None or self._unavailable:
            return effect

        # Imported here, so the chime costs nothing until it first sounds.
        try:
            from pyface.qt import QtMultimedia

        except ImportError as error:
            self._give_up(f"Qt Multimedia is not available ({error})")

            return None

        effect = QtMultimedia.QSoundEffect()
        effect.statusChanged.connect(lambda: self._check(effect))
        effect.setSource(QtCore.QUrl.fromLocalFile(str(path)))
        self._effects[path] = effect

        return effect

    def _check(self, effect):
        """A sound that cannot load or play (e.g. no audio device) turns the
        chime off for the session."""

        if effect.status() == effect.Status.Error:
            self._give_up(f"could not play {effect.source().toLocalFile()}")

    def _give_up(self, reason):

        if not self._unavailable:
            self._unavailable = True
            logger.warning(f"Notification chime off for this session: {reason}")
