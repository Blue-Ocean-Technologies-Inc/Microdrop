# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Synthesise the notification chimes into this folder's WAV files::

    python -m microdrop_style.sounds.make_chimes

Each note is a few sine partials held for a moment, then under an
exponential decay, with a soft attack and fade so nothing clicks. Higher
partials die away faster than the fundamental, as on a struck bar, and a
few short echoes give the set a little room; mono, 16-bit, written with
``wave``. Pitches sit around the fourth and fifth octave, low and warm
like a desktop's system sounds rather than a beeper's.
"""

# Standard library imports.
import math
import struct
import wave

# Local imports.
from .chimes import (
    CHIME_ALERT,
    CHIME_COMPLETION,
    CHIME_CONNECTED,
    CHIME_DISCONNECTED,
    CHIME_GENTLE,
)

#: Samples per second: plenty for tones under 4 kHz, and small files.
SAMPLE_RATE = 22050

#: The loudest chime's peak (of full scale) once normalised: the volume
#: setting scales it down, so the files themselves are not quiet.
PEAK = 0.9

#: Silence (ms) before each chime: an audio output waking from idle can
#: swallow the first moments of a sound, and this is all it swallows.
LEAD_IN_MS = 120

#: Milliseconds of rise at a note's start and fall at the file's end.
ATTACK_MS = 14
FADE_MS = 60

#: How much faster a partial decays than the fundamental: its decay time
#: is divided by its frequency ratio to this power, so the upper partials
#: fade first and the tail settles into a warm fundamental.
PARTIAL_DECAY_EXPONENT = 1.0

#: The room: (delay ms, level) echoes added under each chime for depth.
ROOM_ECHOES = [
    (23, 0.22),
    (41, 0.18),
    (59, 0.14),
    (83, 0.11),
    (113, 0.08),
    (151, 0.05),
]

#: The gentle chime (info, success, news): one soft E4 over a quiet
#: sub-octave, with a little of its octave, ringing out over a second.
GENTLE_NOTES = [
    # (start ms, frequency Hz, peak, hold ms, decay time constant ms)
    (0, 329.6, 0.32, 10, 420),
]
GENTLE_PARTIALS = [(0.5, 0.25), (1.0, 1.0), (2.0, 0.15), (3.0, 0.04)]
GENTLE_MS = 1300

#: The alert chime (warning, error, Needs attention): a rising A4 to D5
#: fourth, a little louder and brighter than the gentle chime.
ALERT_NOTES = [
    (0, 440.0, 0.34, 10, 220),
    (160, 587.3, 0.38, 15, 360),
]
ALERT_PARTIALS = [(1.0, 1.0), (2.0, 0.22), (3.0, 0.07)]
ALERT_MS = 1150

#: The connected and disconnected pair (a device or a chip coming and
#: going): two soft notes a fifth apart, C4 up to G4 for connected.
#: Rounder and lower than the alert, and two notes where the gentle chime
#: has one.
CONNECTED_NOTES = [
    (0, 261.6, 0.30, 10, 220),
    (150, 392.0, 0.30, 15, 360),
]

#: Disconnected is connected's exact mirror: the same rhythm and voicing
#: with the two pitches swapped, so the pair reads as up, then down.
DISCONNECTED_NOTES = [
    (start, CONNECTED_NOTES[-1 - index][1], peak, hold, decay)
    for index, (start, _pitch, peak, hold, decay) in enumerate(CONNECTED_NOTES)
]
PAIR_PARTIALS = [(0.5, 0.20), (1.0, 1.0), (2.0, 0.15), (3.0, 0.04)]
PAIR_MS = 1100

#: The completion tone (a protocol finished), like an appliance's: three
#: even A4 notes, each held briefly, then rung out; it carries across a
#: room without the edge of a square wave.
COMPLETION_NOTES = [
    (0, 440.0, 0.40, 120, 120),
    (500, 440.0, 0.40, 120, 120),
    (1000, 440.0, 0.40, 120, 220),
]
COMPLETION_PARTIALS = [(1.0, 1.0), (2.0, 0.15), (3.0, 0.04)]
COMPLETION_MS = 1900


def synthesise(notes, partials, length_ms):
    """The samples, -1 to 1, of ``notes`` voiced with ``partials``
    ((frequency ratio, level) pairs) over ``length_ms``."""
    count = int(SAMPLE_RATE * length_ms / 1000)
    attack = SAMPLE_RATE * ATTACK_MS / 1000
    fade = SAMPLE_RATE * FADE_MS / 1000
    levels = sum(level for _ratio, level in partials)
    samples = [0.0] * count

    for start_ms, frequency, peak, hold_ms, decay_ms in notes:
        start = int(SAMPLE_RATE * start_ms / 1000)
        hold = SAMPLE_RATE * hold_ms / 1000
        decay = SAMPLE_RATE * decay_ms / 1000

        # Each partial's own decay: the higher, the shorter.
        voices = [
            (ratio, level, decay / ratio**PARTIAL_DECAY_EXPONENT)
            for ratio, level in partials
        ]

        for index in range(start, count):
            t = index - start
            rise = peak * min(1.0, t / attack)
            ringing = max(t - hold, 0)
            tone = sum(
                level
                * math.exp(-ringing / voice_decay)
                * math.sin(2 * math.pi * frequency * ratio * t / SAMPLE_RATE)
                for ratio, level, voice_decay in voices
            )
            samples[index] += rise * tone / levels

    # The tail fades to silence.
    for index in range(max(count - int(fade), 0), count):
        samples[index] *= (count - index) / fade

    return samples


def add_room(samples):
    """``samples`` with ROOM_ECHOES mixed in under them, for depth."""
    roomy = list(samples)

    for delay_ms, level in ROOM_ECHOES:
        delay = int(SAMPLE_RATE * delay_ms / 1000)

        for index in range(delay, len(samples)):
            roomy[index] += level * samples[index - delay]

    return roomy


def write_wav(path, samples):
    """``samples`` as a mono 16-bit WAV at ``path``."""
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
        for sample in samples
    )

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)


def main():
    chimes = {
        CHIME_GENTLE: synthesise(GENTLE_NOTES, GENTLE_PARTIALS, GENTLE_MS),
        CHIME_ALERT: synthesise(ALERT_NOTES, ALERT_PARTIALS, ALERT_MS),
        CHIME_COMPLETION: synthesise(
            COMPLETION_NOTES, COMPLETION_PARTIALS, COMPLETION_MS
        ),
        CHIME_CONNECTED: synthesise(CONNECTED_NOTES, PAIR_PARTIALS, PAIR_MS),
        CHIME_DISCONNECTED: synthesise(DISCONNECTED_NOTES, PAIR_PARTIALS, PAIR_MS),
    }
    chimes = {path: add_room(samples) for path, samples in chimes.items()}

    # One gain for all three keeps them in proportion to one another.
    loudest = max(abs(sample) for samples in chimes.values() for sample in samples)
    gain = PEAK / loudest

    lead_in = [0.0] * int(SAMPLE_RATE * LEAD_IN_MS / 1000)

    for path, samples in chimes.items():
        write_wav(path, lead_in + [sample * gain for sample in samples])
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
