# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The bell's chime: a sound with each arrival the bell rings for, so the
rule is simply "when a notification pops up, it makes a sound".

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

Each tone plays its shipped sound until the chime designer gives it a
design of its own; the designed sounds are rendered (``chime_sounds``) the
next time a sound is needed after a change, not on every slider step.
"""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from pyface.qt import QtCore, QtGui
from traits.api import Any, Bool, Dict, Float, HasTraits, Instance, List, Str, observe

# Local imports.
from ..consts import (
    CHIME_SOUNDS_DIRNAME,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    TONE_ALERT,
    TONE_LABELS,
    TONE_SOFT,
    notifications_data_dir,
)
from ..controllers.toast_controller import SKIP_START_UP
from ..models.notifications_pane_model import NotificationsPaneModel
from . import chime_trace
from .chime_sounds import SHIPPED_TONE_SOUNDS, remove_stale_sounds, tone_sound_paths

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
SKIP_VOLUME_ZERO = "volume 0"

#: Times a play is retried when its sound reports an error.
PLAY_RETRIES = 1
SKIP_FLAP = "state changing again"

#: Each tone's shipped sound, weakest first: within CHIME_OVERLAP_S only a
#: stronger tone than the last one sounds.
TONE_SOUNDS = SHIPPED_TONE_SOUNDS

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
    settings allow, and reports what it did and did not play.

    A tone asked to play while its sound is not Ready waits for Ready; one
    whose sound reports an error is rebuilt and played once it loads, once.
    A requested play is never dropped without a trace line saying why."""

    pane_model = Instance(NotificationsPaneModel)

    #: Where the designed sounds are rendered.
    sounds_dir = Instance(Path)

    #: Each tone's sound file as designed; empty until needed after a
    #: design change.
    _sounds = Dict()

    #: QSoundEffects by sound path, one per tone, made on first use.
    _effects = Dict()

    #: Plays waiting for their sound to be Ready: retries left, by path.
    _pending = Dict()

    #: Lists the audio outputs: a change (headphones plugged in) remakes
    #: the effects, so the next sound goes to the new default output.
    _devices = Any()

    #: The outputs as last seen, for the trace.
    _outputs = List()

    #: time.monotonic() of the last chime, and its tone.
    _last_played = Float(-CHIME_OVERLAP_S)
    _last_tone = Str()

    #: ``(time, tone)`` of each state entry's last chime, by its key.
    _state_chimes = Dict()

    #: Set when Qt Multimedia cannot be imported: warned once, then silent.
    _unavailable = Bool(False)

    def _sounds_dir_default(self):
        return notifications_data_dir() / CHIME_SOUNDS_DIRNAME

    def traits_init(self):

        if chime_trace.enabled():
            self._trace_application()

    # ------------------------------------------------------------------ #
    # Deciding                                                            #
    # ------------------------------------------------------------------ #

    @observe("pane_model:rang")
    def _ring(self, event):
        entry = event.new
        settings = self.pane_model.center.settings
        tone = tone_for(entry, settings)
        now = time.monotonic()

        self.preload()

        if not settings.sound_enabled:
            self._skip(entry, SKIP_SOUND_OFF)

            return

        if not settings.sound_volume:
            self._skip(entry, SKIP_VOLUME_ZERO)

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
        if entry.is_thread:
            when, last = self._state_chimes.get(entry.key, (-STATE_FLAP_S, ""))
            worse = TONE_STRENGTH[tone] > TONE_STRENGTH.get(last, -1)

            if now - when < STATE_FLAP_S and not worse:
                self._skip(entry, SKIP_FLAP)

                return

            self._state_chimes[entry.key] = (now, tone)

        self._last_played = now
        self._last_tone = tone

        logger.debug(f"Chime for {entry.title!r}: played {tone}")
        chime_trace.trace(
            "arrival",
            decision="play",
            tone=tone,
            title=entry.title,
            category=entry.category_id,
        )
        settings.last_sound = (
            f"Last sound: {TONE_LABELS[tone]} · {entry.title} · {_clock()}"
        )
        self.play(self.sound(tone))

    @observe("pane_model:silenced")
    def _silenced(self, event):
        entry, reason = event.new

        if reason != SKIP_START_UP:
            self.preload()

        self._skip(entry, reason)

    @observe("pane_model:center:settings:opened")
    def _settings_opened(self, event):
        chime_trace.trace("settings window opened")
        self.preload()

    @observe("pane_model:center:settings:test_sound")
    def _test(self, event):
        """The chosen tone, at the chosen volume."""
        tone = self.pane_model.center.settings.test_tone

        chime_trace.trace("test", tone=tone)
        self.play(self.sound(tone))

    @observe("pane_model:center:settings:chime:preview")
    def _preview(self, event):
        """A tone as the designer now has it, at the chosen volume."""
        chime_trace.trace("preview", tone=event.new)
        self.play(self.sound(event.new))

    @observe("pane_model:center:settings:chime:updated")
    def _design_changed(self, event):
        self._sounds = {}

    def _skip(self, entry, reason):
        logger.debug(f"Chime for {entry.title!r}: skipped ({reason})")
        chime_trace.trace(
            "arrival",
            decision="skip",
            reason=reason,
            title=entry.title,
            category=entry.category_id,
        )
        self.pane_model.center.settings.last_skipped = (
            f"Last skipped: {reason} · {entry.title} · {_clock()}"
        )

    # ------------------------------------------------------------------ #
    # Playing                                                             #
    # ------------------------------------------------------------------ #

    def preload(self):
        """Load every tone's sound now, so a first chime is not also a
        first load."""

        for tone in TONE_SOUNDS:
            self._effect(self.sound(tone))

    def sound(self, tone):
        """The sound file ``tone`` plays, rendering the designed sounds
        first if they changed since last needed."""

        if not self._sounds:
            self._render_sounds()

        return self._sounds[tone]

    def _render_sounds(self):
        """Each tone's sound as designed; the shipped ones if rendering
        fails. Effects and files of sounds no longer used are let go."""
        designer = self.pane_model.center.settings.chime

        try:
            sounds = tone_sound_paths(designer, self.sounds_dir)

        except OSError as error:
            logger.warning(f"Designed chimes could not be written: {error}")
            sounds = dict(TONE_SOUNDS)

        self._sounds = sounds
        kept = set(sounds.values())
        unused = [path for path in self._effects if path not in kept]

        for path in unused:
            self._pending.pop(path, None)
            self._effects.pop(path).deleteLater()

        remove_stale_sounds(self.sounds_dir, kept)
        chime_trace.trace(
            "sounds", sounds={tone: path.name for tone, path in sounds.items()}
        )

    def play(self, path):
        """Start ``path`` at the settings' volume, from its start if still
        playing; returns at once. Not Ready yet, it plays once Ready; in
        error, its sound is rebuilt first."""
        effect = self._effect(path)

        if effect is None:
            chime_trace.trace(
                "play dropped", sound=path.name, reason="no Qt Multimedia"
            )
            logger.debug(f"Chime {path.name}: no sound effect")

            return

        status = effect.status()

        chime_trace.trace(
            "play",
            sound=path.name,
            status=status.name,
            loaded=effect.isLoaded(),
            volume=round(effect.volume(), 3),
            muted=effect.isMuted(),
            source=effect.source().toLocalFile(),
        )

        if status == effect.Status.Error:
            self._pending[path] = PLAY_RETRIES
            self._rebuild(path, "error status when asked to play")

            return

        if status != effect.Status.Ready:
            self._pending.setdefault(path, PLAY_RETRIES)
            chime_trace.trace("play waits", sound=path.name, status=status.name)

            return

        self._start(effect, path)

    def _start(self, effect, path):
        volume = self.pane_model.center.settings.sound_volume
        effect.setVolume(linear_volume(volume))
        restarted = effect.isPlaying()

        if restarted:
            effect.stop()

        effect.play()

        chime_trace.trace(
            "start",
            sound=path.name,
            volume_percent=volume,
            gain=round(effect.volume(), 4),
            restarted=restarted,
        )

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
            self._outputs = _outputs_now()

        effect = QtMultimedia.QSoundEffect()
        effect.statusChanged.connect(lambda: self._status_changed(effect, path))
        effect.loadedChanged.connect(
            lambda: chime_trace.trace(
                "loaded", sound=path.name, loaded=effect.isLoaded()
            )
        )
        effect.playingChanged.connect(lambda: self._playing_changed(effect, path))
        effect.setSource(QtCore.QUrl.fromLocalFile(str(path)))
        self._effects[path] = effect

        chime_trace.trace("effect made", sound=path.name)

        return effect

    def _status_changed(self, effect, path):
        """Play what waited for Ready; rebuild a sound in error, once."""
        status = effect.status()

        logger.debug(f"Chime {path.name}: status {status.name}")
        chime_trace.trace("status", sound=path.name, status=status.name)

        # A rebuilt sound's old effect may still report: only the current
        # one counts.
        if self._effects.get(path) is not effect:
            return

        if status == effect.Status.Ready and path in self._pending:
            del self._pending[path]
            self._start(effect, path)

        elif status == effect.Status.Error:
            retries = self._pending.get(path, 0)

            if retries > 0:
                self._pending[path] = retries - 1
                self._rebuild(path, "error status while loading")

            else:
                self._pending.pop(path, None)
                chime_trace.trace(
                    "play dropped", sound=path.name, reason="error after retry"
                )
                logger.warning(f"Notification chime {path.name} could not play")

    def _playing_changed(self, effect, path):
        logger.debug(f"Chime {path.name}: playing {effect.isPlaying()}")
        chime_trace.trace("playing", sound=path.name, playing=effect.isPlaying())

    def _rebuild(self, path, reason):
        """A new effect for ``path``; a play waiting on it plays once it is
        Ready."""
        chime_trace.trace("rebuild", sound=path.name, reason=reason)
        old = self._effects.pop(path, None)

        if old is not None:
            old.deleteLater()

        self._effect(path)

    def _outputs_changed(self):
        """New effects for the new default output; plays waiting on them
        still play once they are Ready."""
        before, self._outputs = self._outputs, _outputs_now()

        logger.debug("Chime: audio outputs changed; sounds reload")
        chime_trace.trace("audio outputs changed", before=before, after=self._outputs)

        for path in list(self._effects):
            self._rebuild(path, "audio outputs changed")

    def _give_up(self, reason):

        if not self._unavailable:
            self._unavailable = True
            logger.warning(f"Notification chime off for this session: {reason}")
            chime_trace.trace("chime off", reason=reason)

    # ------------------------------------------------------------------ #
    # The trace's context                                                 #
    # ------------------------------------------------------------------ #

    @observe("pane_model:center:settings:[sound_enabled, sound_volume]")
    def _trace_setting(self, event):
        chime_trace.trace("setting", name=event.name, value=event.new)

    @observe("pane_model:center:settings:groups:items:categories:items:tone")
    def _trace_category_tone(self, event):
        chime_trace.trace("category tone", category=event.object.id, tone=event.new)

    @observe("pane_model:is_open")
    def _trace_drawer(self, event):
        chime_trace.trace("drawer", open=event.new)

    @observe("pane_model:toasts:quiet")
    def _trace_quiet(self, event):
        chime_trace.trace("quiet", on=event.new)

    def _trace_application(self):
        """Theme and focus changes, from the application."""
        app = QtGui.QGuiApplication.instance()

        chime_trace.trace("trace started", outputs=_outputs_now())
        app.styleHints().colorSchemeChanged.connect(
            lambda scheme: chime_trace.trace("theme", scheme=scheme.name)
        )
        app.applicationStateChanged.connect(
            lambda state: chime_trace.trace("application state", state=state.name)
        )


def _outputs_now():
    """The audio outputs, ``(id, description)``, the default marked."""
    from pyface.qt import QtMultimedia

    default = QtMultimedia.QMediaDevices.defaultAudioOutput()

    return [
        (
            bytes(device.id()).decode(errors="replace"),
            device.description(),
            "default" if device == default else "",
        )
        for device in QtMultimedia.QMediaDevices.audioOutputs()
    ]


def _clock():
    return time.strftime("%H:%M:%S")
