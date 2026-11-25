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
exponential decay, with a short attack and fade so nothing clicks; mono,
16-bit, written with ``wave``.
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
ATTACK_MS = 4
FADE_MS = 12

#: The gentle chime (info, success, news): one soft A5 with its octave,
#: twelfth and a faint double octave, ringing out over about 0.6 s.
GENTLE_NOTES = [
    # (start ms, frequency Hz, peak, hold ms, decay time constant ms)
    (0, 880.0, 0.30, 20, 190),
]
GENTLE_PARTIALS = [(1.0, 1.0), (2.0, 0.30), (3.0, 0.08), (4.0, 0.03)]
GENTLE_MS = 600

#: The alert chime (warning, error, Needs attention): a rising C6 to E6
#: pair, a little louder and brighter, still short.
ALERT_NOTES = [
    (0, 1046.5, 0.34, 15, 120),
    (140, 1318.5, 0.38, 25, 210),
]
ALERT_PARTIALS = [(1.0, 1.0), (2.0, 0.35), (3.0, 0.12), (4.0, 0.04)]
ALERT_MS = 700

#: The connected and disconnected pair (a device or a chip coming and
#: going): one figure of two soft notes a fifth apart, E5 up to B5 for
#: connected and back down for disconnected. Lower and rounder than the
#: alert, and two notes where the soft chime has one.
CONNECTED_NOTES = [
    (0, 659.3, 0.26, 20, 120),
    (130, 987.8, 0.28, 30, 200),
]
DISCONNECTED_NOTES = [
    (0, 987.8, 0.26, 20, 120),
    (130, 659.3, 0.28, 30, 200),
]
PAIR_PARTIALS = [(1.0, 1.0), (2.0, 0.18), (3.0, 0.05)]
PAIR_MS = 560

#: The completion tone (a protocol finished), like a microwave's: three
#: even D6 beeps, each held, then rounded off; nearly pure sines, so it
#: carries without the edge of a square wave.
COMPLETION_NOTES = [
    (0, 1174.7, 0.42, 170, 45),
    (500, 1174.7, 0.42, 170, 45),
    (1000, 1174.7, 0.42, 170, 45),
]
COMPLETION_PARTIALS = [(1.0, 1.0), (2.0, 0.12), (3.0, 0.04)]
COMPLETION_MS = 1450


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

        for index in range(start, count):
            t = index - start
            fall = math.exp(-max(t - hold, 0) / decay)
            envelope = peak * min(1.0, t / attack) * fall
            tone = sum(
                level * math.sin(2 * math.pi * frequency * ratio * t / SAMPLE_RATE)
                for ratio, level in partials
            )
            samples[index] += envelope * tone / levels

    # The tail fades to silence.
    for index in range(max(count - int(fade), 0), count):
        samples[index] *= (count - index) / fade

    return samples


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

    # One gain for all three keeps them in proportion to one another.
    loudest = max(abs(sample) for samples in chimes.values() for sample in samples)
    gain = PEAK / loudest

    lead_in = [0.0] * int(SAMPLE_RATE * LEAD_IN_MS / 1000)

    for path, samples in chimes.items():
        write_wav(path, lead_in + [sample * gain for sample in samples])
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
