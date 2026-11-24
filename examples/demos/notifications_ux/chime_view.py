# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The bell's chime: a sound with each pop-up, so the rule is simply "when
a notification pops up, it makes a sound".

Driven by the pane model's ``rang`` event (every arrival the bell rings
for, the drawer open or not) and ``silenced`` (one it does not: start-up
history, a repeat, one held while quiet). The tone is the category's
choice (none, soft, alert, completion); an uncategorised arrival plays
soft, or alert for a warning, an error or Needs attention. Within
CHIME_OVERLAP_S of a chime only a stronger tone plays, so a burst makes
one or two sounds. Every decision is logged at debug level and shown in
the settings as the last sound and the last skip, with why.

The three sounds load together the first time anything arrives after
start-up or the settings open, not at launch; each tone has its own
effect, restarted cleanly when played again. Without Qt Multimedia or an
audio device the chime logs one warning and stays silent.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt import QtCore
from traits.api import Any, Bool, Dict, Float, HasTraits, Instance, Str, observe

# Microdrop package imports.
from notifications.consts import SEVERITY_ERROR, SEVERITY_WARNING

# Microdrop style imports.
from microdrop_style.sounds.chimes import (
    CHIME_ALERT,
    CHIME_COMPLETION,
    CHIME_CONNECTED,
    CHIME_DISCONNECTED,
    CHIME_GENTLE,
)

# Local imports.
from .settings_models import (
    TONE_ALERT,
    TONE_COMPLETION,
    TONE_CONNECTED,
    TONE_DISCONNECTED,
    TONE_LABELS,
    TONE_SOFT,
)
from .ux_consts import SKIP_START_UP
from .ux_models import UxPaneModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Within this time (s) of a chime only a stronger tone plays: it stops
#: exact overlaps, not a second notification a moment later.
CHIME_OVERLAP_S = 0.4

#: Why an arrival the bell rang for made no sound.
SKIP_SOUND_OFF = "sound off"
SKIP_TONE_NONE = "category tone none"
SKIP_OVERLAP = "rate limit"
SKIP_FLAP = "state changing again"

#: Each tone's sound, weakest first: within CHIME_OVERLAP_S only a
#: stronger tone than the last one sounds.
TONE_SOUNDS = {
    TONE_SOFT: CHIME_GENTLE,
    TONE_CONNECTED: CHIME_CONNECTED,
    TONE_DISCONNECTED: CHIME_DISCONNECTED,
    TONE_ALERT: CHIME_ALERT,
    TONE_COMPLETION: CHIME_COMPLETION,
}

#: A state that keeps changing (a connection flapping) chimes at most once
#: in this time (s), unless the change is stronger than the last one.
STATE_FLAP_S = 2.0
TONE_STRENGTH = {tone: strength for strength, tone in enumerate(TONE_SOUNDS)}


def linear_volume(percent):
    """The settings' volume (a 0-100 slider, even to the ear) as the linear
    gain Qt's sound effects take."""
    from pyface.qt.QtMultimedia import QtAudio

    return QtAudio.convertVolume(
        percent / 100,
        QtAudio.VolumeScale.LogarithmicVolumeScale,
        QtAudio.VolumeScale.LinearVolumeScale,
    )


def tone_for(entry, settings):
    """The tone ``entry`` plays: its category's, else by its severity."""
    kind = settings.category(entry.category_id)

    if kind is not None:
        return kind.tone

    urgent = entry.severity in (SEVERITY_WARNING, SEVERITY_ERROR)

    return TONE_ALERT if urgent or entry.needs_attention else TONE_SOFT


class NotificationChime(HasTraits):
    """Plays the chime the pane model's ``rang`` calls for, as the
    settings allow, and reports what it did and did not play."""

    pane_model = Instance(UxPaneModel)

    #: QSoundEffects by sound path, one per tone, made on first use.
    _effects = Dict()

    #: Lists the audio outputs: a change (headphones plugged in) remakes
    #: the effects, so the next sound goes to the new default output.
    _devices = Any()

    #: time.monotonic() of the last chime, and its tone.
    _last_played = Float(-CHIME_OVERLAP_S)
    _last_tone = Str()

    #: ``(time, tone)`` of each state entry's last chime, by its key.
    _state_chimes = Dict()

    #: Set once sound proved unavailable: warned once, then silent.
    _unavailable = Bool(False)

    @observe("pane_model:rang")
    def _ring(self, event):
        entry = event.new
        settings = self.pane_model.toasts.settings
        tone = tone_for(entry, settings)
        now = time.monotonic()

        self.preload()

        if not settings.sound_enabled:
            self._skip(entry, SKIP_SOUND_OFF)

            return

        if tone not in TONE_SOUNDS:
            self._skip(entry, SKIP_TONE_NONE)

            return

        recent = now - self._last_played < CHIME_OVERLAP_S
        stronger = TONE_STRENGTH[tone] > TONE_STRENGTH.get(self._last_tone, -1)

        if recent and not stronger:
            self._skip(entry, SKIP_OVERLAP)

            return

        # A state entry (one updated in place, e.g. a connection) that
        # changes again within STATE_FLAP_S chimes only if it got worse.
        state = entry.key[0] == "thread" if isinstance(entry.key, tuple) else False

        if state:
            when, last = self._state_chimes.get(entry.key, (-STATE_FLAP_S, ""))
            worse = TONE_STRENGTH[tone] > TONE_STRENGTH.get(last, -1)

            if now - when < STATE_FLAP_S and not worse:
                self._skip(entry, SKIP_FLAP)

                return

            self._state_chimes[entry.key] = (now, tone)

        self._last_played = now
        self._last_tone = tone
        self.play(TONE_SOUNDS[tone])

        logger.debug(f"Chime for {entry.title!r}: played {tone}")
        settings.last_sound = (
            f"Last sound: {TONE_LABELS[tone]} · {entry.title} · {_clock()}"
        )

    @observe("pane_model:silenced")
    def _silenced(self, event):
        entry, reason = event.new

        if reason != SKIP_START_UP:
            self.preload()

        self._skip(entry, reason)

    @observe("pane_model:toasts:settings:opened")
    def _settings_opened(self, event):
        self.preload()

    @observe("pane_model:toasts:settings:test_sound")
    def _test(self, event):
        """The chosen tone, at the chosen volume."""
        self.play(TONE_SOUNDS[self.pane_model.toasts.settings.test_tone])

    def _skip(self, entry, reason):
        logger.debug(f"Chime for {entry.title!r}: skipped ({reason})")
        self.pane_model.toasts.settings.last_skipped = (
            f"Last skipped: {reason} · {entry.title} · {_clock()}"
        )

    def preload(self):
        """Load every tone's sound now, so a first chime is not also a
        first load."""

        for path in TONE_SOUNDS.values():
            self._effect(path)

    def play(self, path):
        """Start ``path`` playing at the settings' volume, from its start if
        it is still playing; returns at once. Called while the sound still
        loads, Qt plays it once loaded."""
        effect = self._effect(path)

        if effect is None:
            logger.debug(f"Chime {path.name}: no sound effect")

            return

        effect.setVolume(linear_volume(self.pane_model.toasts.settings.sound_volume))

        if effect.isPlaying():
            effect.stop()

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

        if self._devices is None:
            self._devices = QtMultimedia.QMediaDevices()
            self._devices.audioOutputsChanged.connect(self._outputs_changed)

        effect = QtMultimedia.QSoundEffect()
        effect.statusChanged.connect(lambda: self._check(effect))
        effect.playingChanged.connect(
            lambda: logger.debug(f"Chime {path.name}: playing {effect.isPlaying()}")
        )
        effect.setSource(QtCore.QUrl.fromLocalFile(str(path)))
        self._effects[path] = effect

        return effect

    def _outputs_changed(self):
        """New effects for the new default output; the old ones finish."""
        logger.debug("Chime: audio outputs changed; sounds reload")

        for effect in self._effects.values():
            effect.deleteLater()

        self._effects = {}

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


def _clock():
    return time.strftime("%H:%M:%S")
