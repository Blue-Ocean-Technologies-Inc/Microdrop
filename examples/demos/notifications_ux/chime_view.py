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
holds. The tone is the category's choice (none, soft, alert, completion);
an uncategorised arrival plays soft, or alert for a warning, an error or
Needs attention. A burst makes one sound, though a stronger tone still
sounds over a softer one just played. The sound effects are made on first
use and play asynchronously; with no multimedia module or audio device the
chime logs one warning and stays silent.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt import QtCore
from traits.api import Bool, Dict, Float, HasTraits, Instance, Str, observe

# Microdrop package imports.
from notifications.consts import SEVERITY_ERROR, SEVERITY_WARNING

# Microdrop style imports.
from microdrop_style.sounds.chimes import CHIME_ALERT, CHIME_COMPLETION, CHIME_GENTLE

# Local imports.
from .settings_models import TONE_ALERT, TONE_COMPLETION, TONE_SOFT
from .ux_models import UxPaneModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Least time (s) between two chimes: a burst or a flood makes one sound.
CHIME_MIN_INTERVAL_S = 1.5


#: Each tone's sound, weakest first: within the rate limit only a stronger
#: tone than the last one sounds.
TONE_SOUNDS = {
    TONE_SOFT: CHIME_GENTLE,
    TONE_ALERT: CHIME_ALERT,
    TONE_COMPLETION: CHIME_COMPLETION,
}
TONE_STRENGTH = {tone: strength for strength, tone in enumerate(TONE_SOUNDS)}


def tone_for(entry, settings):
    """The tone ``entry`` plays: its category's, else by its severity."""
    kind = settings.category(entry.category_id)

    if kind is not None:
        return kind.tone

    urgent = entry.severity in (SEVERITY_WARNING, SEVERITY_ERROR)

    return TONE_ALERT if urgent or entry.needs_attention else TONE_SOFT


class NotificationChime(HasTraits):
    """Plays the chime the pane model's ``rang`` calls for, as the toast
    settings allow."""

    pane_model = Instance(UxPaneModel)

    #: QSoundEffects by sound path, made on first use.
    _effects = Dict()

    #: time.monotonic() of the last chime, and its tone.
    _last_played = Float(-CHIME_MIN_INTERVAL_S)
    _last_tone = Str()

    #: Set once sound proved unavailable: warned once, then silent.
    _unavailable = Bool(False)

    @observe("pane_model:rang")
    def _ring(self, event):
        settings = self.pane_model.toasts.settings
        tone = tone_for(event.new, settings)
        now = time.monotonic()

        if not settings.sound_enabled or tone not in TONE_SOUNDS:
            return

        recent = now - self._last_played < CHIME_MIN_INTERVAL_S
        stronger = TONE_STRENGTH[tone] > TONE_STRENGTH.get(self._last_tone, -1)

        if recent and not stronger:
            return

        self._last_played = now
        self._last_tone = tone
        self.play(TONE_SOUNDS[tone])

    @observe("pane_model:toasts:settings:test_sound")
    def _test(self, event):
        """The chosen tone, at the chosen volume."""
        self.play(TONE_SOUNDS[self.pane_model.toasts.settings.test_tone])

    def play(self, path):
        """Start ``path`` playing at the settings' volume; returns at once."""
        effect = self._effect(path)

        if effect is None:
            logger.debug(f"Chime {path.name}: no sound effect")

            return

        effect.setVolume(self.pane_model.toasts.settings.sound_volume / 100)
        effect.play()

        logger.debug(
            f"Chime {path.name}: play() with status {effect.status().name},"
            f" loaded {effect.isLoaded()}, volume {effect.volume():.2f},"
            f" muted {effect.isMuted()}, playing {effect.isPlaying()}"
        )

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
        effect.playingChanged.connect(
            lambda: logger.debug(f"Chime {path.name}: playing {effect.isPlaying()}")
        )
        effect.setSource(QtCore.QUrl.fromLocalFile(str(path)))
        self._effects[path] = effect

        return effect

    def _check(self, effect):
        """A sound that cannot load or play (e.g. no audio device) turns the
        chime off for the session."""
        status = effect.status()

        logger.debug(f"Chime {effect.source().fileName()}: status {status.name}")

        if status == effect.Status.Error:
            self._give_up(f"could not play {effect.source().toLocalFile()}")

    def _give_up(self, reason):

        if not self._unavailable:
            self._unavailable = True
            logger.warning(f"Notification chime off for this session: {reason}")
