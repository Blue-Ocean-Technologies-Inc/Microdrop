# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Synthesise notification chimes from a design, with numpy and no Qt.

A design is a timbre (how one struck note sounds), a melody (the scheme
giving each chime its own figure of notes and rhythm), a pitch shift in
semitones, and the room echo and ring length as percentages of the usual.
``render_chime_set`` renders the five chimes, scaled by one gain so the
set stays in proportion, each after the same lead-in of silence;
``write_wav`` saves one as a mono 16-bit WAV.

The default design ("current" timbre, "classic" melody, no shift, 100 %
room and length) stands for the shipped WAVs ``make_chimes`` writes:
callers play those files for it rather than rendering it here.
"""

# Standard library imports.
import math
import wave

# Third-party imports.
import numpy as np

# Local imports.
from .chimes import CHIME_NAMES

#: Samples per second of a rendered chime: high enough for the bright
#: partials of the marimba, kalimba and electric piano.
SAMPLE_RATE = 44100

#: The loudest chime's peak (of full scale) once normalised: the volume
#: setting scales it down, so the files themselves are not quiet.
PEAK = 0.9

#: Silence (ms) before each chime: an audio output waking from idle can
#: swallow the first moments of a sound, and this is all it swallows.
LEAD_IN_MS = 120

#: Milliseconds of fall at a chime's end, so nothing clicks.
FADE_MS = 60

#: The room: (delay ms, level) echoes added under each chime for depth.
ROOM_ECHOES = [
    (23, 0.22),
    (41, 0.18),
    (59, 0.14),
    (83, 0.11),
    (113, 0.08),
    (151, 0.05),
]

#: Seconds a chime rings past its last note's start, at 100 % length.
TAIL_S = 1.8

#: The design's ranges and defaults: pitch shift (semitones), room echo
#: and ring length (% of the usual).
PITCH_SHIFT_RANGE = (-12, 12)
ROOM_RANGE = (0, 200)
RING_LENGTH_RANGE = (40, 250)
DEFAULT_PITCH_SHIFT = 0
DEFAULT_ROOM = 100
DEFAULT_RING_LENGTH = 100


# --------------------------------------------------------------------------- #
# Timbres: voice(frequency Hz, t s, length factor) -> samples                  #
# --------------------------------------------------------------------------- #


def _additive(frequency, t, partials, decay, exponent, attack, tremolo=None):
    """Sine ``partials`` ((frequency ratio, level) pairs), each decaying
    from ``decay`` (s) divided by its ratio to ``exponent``, after a linear
    ``attack`` (s); ``tremolo`` is an optional (rate Hz, depth) pair."""
    out = np.zeros_like(t)

    for ratio, level in partials:
        partial_decay = decay / ratio**exponent if ratio >= 1 else decay * 1.2
        ring = np.exp(-t / partial_decay)
        out += level * ring * np.sin(2 * np.pi * frequency * ratio * t)

    out *= np.minimum(1.0, t / attack)

    if tremolo:
        rate, depth = tremolo
        out *= 1 - depth * (0.5 - 0.5 * np.cos(2 * np.pi * rate * t))

    return out / sum(level for _ratio, level in partials)


def _current(frequency, t, length):
    partials = [(0.5, 0.2), (1, 1), (2, 0.15), (3, 0.04)]

    return _additive(frequency, t, partials, 0.36 * length, 1.0, 0.014)


def _marimba(frequency, t, length):
    partials = [(1, 1), (3.93, 0.3), (9.2, 0.1)]

    return _additive(frequency, t, partials, 0.55 * length, 1.2, 0.003)


def _vibraphone(frequency, t, length):
    partials = [(1, 1), (4, 0.2), (10, 0.04)]

    return _additive(
        frequency, t, partials, 1.3 * length, 1.0, 0.004, tremolo=(5.0, 0.3)
    )


def _electric_piano(frequency, t, length):
    """Two-operator FM, its brightness falling away, with a short tine."""
    index = 2.2 * np.exp(-t / 0.25) + 0.3
    phase = 2 * np.pi * frequency * t
    body = np.sin(phase + index * np.sin(phase))
    tine = 0.15 * np.exp(-t / 0.05) * np.sin(14 * phase)
    envelope = np.minimum(1.0, t / 0.002) * np.exp(-t / (0.9 * length))

    return envelope * (body + tine) / 1.15


def _felt_piano(frequency, t, length):
    """Slightly stretched partials, each doubled a hair sharp for warmth."""
    out = np.zeros_like(t)
    total = 0.0

    for number in range(1, 9):
        level = 1 / number**1.6
        partial = frequency * number * math.sqrt(1 + 0.0004 * number * number)
        ring = np.exp(-t / (0.8 * length / number**0.6))

        out += level * ring * np.sin(2 * np.pi * partial * t)
        out += 0.5 * level * ring * np.sin(2 * np.pi * partial * 1.0015 * t)
        total += 1.5 * level

    return np.minimum(1.0, t / 0.008) * out / total


def _soft_bell(frequency, t, length):
    partials = [
        (0.5, 0.35),
        (1, 1),
        (1.2, 0.45),
        (1.5, 0.3),
        (2, 0.5),
        (2.5, 0.2),
        (3, 0.12),
    ]

    return _additive(frequency, t, partials, 1.6 * length, 0.6, 0.003)


def _kalimba(frequency, t, length):
    partials = [(1, 1), (2, 0.08), (5.6, 0.25)]

    return _additive(frequency, t, partials, 0.55 * length, 1.5, 0.002)


#: The timbres by key: their label and voice.
TIMBRE_CURRENT = "current"
TIMBRES = {
    TIMBRE_CURRENT: ("Current", _current),
    "marimba": ("Marimba", _marimba),
    "vibraphone": ("Vibraphone", _vibraphone),
    "electric_piano": ("Electric piano", _electric_piano),
    "felt_piano": ("Felt piano", _felt_piano),
    "soft_bell": ("Soft bell", _soft_bell),
    "kalimba": ("Kalimba", _kalimba),
}
TIMBRE_LABELS = {key: label for key, (label, _voice) in TIMBRES.items()}

# --------------------------------------------------------------------------- #
# Melodies: chime -> [(start ms, MIDI note, velocity)]; C4 = 60               #
# --------------------------------------------------------------------------- #

#: The melodies by key: their label and each chime's figure.
MELODY_CLASSIC = "classic"
MELODIES = {
    MELODY_CLASSIC: (
        "Classic",
        {
            "gentle": [(0, 64, 1.0)],
            "alert": [(0, 69, 0.9), (160, 74, 1.0)],
            "connected": [(0, 60, 1.0), (150, 67, 1.0)],
            "disconnected": [(0, 67, 1.0), (150, 60, 1.0)],
            "completion": [(0, 69, 1.0), (500, 69, 1.0), (1000, 69, 1.0)],
        },
    ),
    "arpeggio": (
        "Arpeggio",
        {
            "gentle": [(0, 64, 0.8), (90, 71, 1.0)],
            "alert": [(0, 69, 0.9), (140, 76, 1.0), (560, 69, 0.9), (700, 76, 1.0)],
            "connected": [(0, 60, 0.9), (110, 64, 0.95), (220, 67, 1.0)],
            "disconnected": [(0, 67, 0.9), (110, 64, 0.95), (220, 60, 1.0)],
            "completion": [
                (0, 60, 0.9),
                (150, 64, 0.9),
                (300, 67, 0.95),
                (480, 72, 1.0),
            ],
        },
    ),
    "pentatonic": (
        "Pentatonic",
        {
            "gentle": [(0, 67, 0.8), (110, 74, 1.0)],
            "alert": [(0, 72, 1.0), (150, 69, 0.9), (300, 72, 1.0)],
            "connected": [(0, 60, 0.9), (120, 62, 0.9), (240, 67, 1.0)],
            "disconnected": [(0, 67, 0.9), (120, 62, 0.9), (240, 60, 1.0)],
            "completion": [
                (0, 60, 0.85),
                (120, 62, 0.85),
                (240, 64, 0.9),
                (360, 67, 0.95),
                (600, 72, 1.0),
            ],
        },
    ),
    "doorbell": (
        "Doorbell",
        {
            "gentle": [(0, 64, 1.0)],
            "alert": [(0, 67, 1.0), (300, 64, 1.0)],
            "connected": [(0, 60, 1.0), (250, 67, 1.0)],
            "disconnected": [(0, 67, 1.0), (250, 60, 1.0)],
            "completion": [(0, 67, 1.0), (300, 64, 1.0), (600, 60, 1.0)],
        },
    ),
}
MELODY_LABELS = {key: label for key, (label, _figures) in MELODIES.items()}

#: The design the shipped WAVs stand for.
DEFAULT_DESIGN = {
    "timbre": TIMBRE_CURRENT,
    "melody": MELODY_CLASSIC,
    "pitch_shift": DEFAULT_PITCH_SHIFT,
    "room": DEFAULT_ROOM,
    "ring_length": DEFAULT_RING_LENGTH,
}


def midi_frequency(note):
    """The frequency (Hz) of MIDI ``note``; A4 = 69 = 440 Hz."""
    return 440.0 * 2 ** ((note - 69) / 12)


def render_chime(name, timbre, melody, pitch_shift, room, ring_length):
    """The samples of chime ``name`` as the design voices it, its tail
    faded; neither normalised nor led in. ``room`` and ``ring_length`` are
    percentages of the usual."""
    figure = MELODIES[melody][1][name]
    voice = TIMBRES[timbre][1]
    length = ring_length / 100
    last_start_s = max(start for start, _note, _velocity in figure) / 1000
    count = int(SAMPLE_RATE * (last_start_s + TAIL_S * length))
    samples = np.zeros(count)

    for start_ms, note, velocity in figure:
        start = int(SAMPLE_RATE * start_ms / 1000)
        t = np.arange(count - start) / SAMPLE_RATE
        frequency = midi_frequency(note + pitch_shift)

        samples[start:] += velocity * voice(frequency, t, length)

    dry = samples.copy()

    for delay_ms, level in ROOM_ECHOES:
        delay = int(SAMPLE_RATE * delay_ms / 1000)
        samples[delay:] += room / 100 * level * dry[:-delay]

    fade = int(SAMPLE_RATE * FADE_MS / 1000)
    samples[-fade:] *= np.linspace(1, 0, fade)

    return samples


def render_chime_set(designs):
    """The five chimes, by name, from ``designs`` (each chime's design as
    ``render_chime``'s keyword arguments): scaled by one gain, the loudest
    peaking at PEAK, so the set keeps its proportions; each led in by
    LEAD_IN_MS of silence."""
    chimes = {name: render_chime(name, **designs[name]) for name in CHIME_NAMES}
    loudest = max(np.max(np.abs(samples)) for samples in chimes.values())
    gain = PEAK / max(loudest, 1e-9)
    lead_in = np.zeros(int(SAMPLE_RATE * LEAD_IN_MS / 1000))

    return {
        name: np.concatenate([lead_in, samples * gain])
        for name, samples in chimes.items()
    }


def write_wav(path, samples):
    """``samples`` (-1 to 1) as a mono 16-bit WAV at ``path``."""
    frames = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)
