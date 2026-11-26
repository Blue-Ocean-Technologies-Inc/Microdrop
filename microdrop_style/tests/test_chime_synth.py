# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The chime designer's synthesis: every timbre and melody renders, the set
shares one gain and a lead-in, and a WAV is written as rendered."""

# Standard library imports.
import wave

# Third-party imports.
import numpy as np

# Microdrop style imports.
from microdrop_style.sounds.chime_synth import (
    DEFAULT_DESIGN,
    LEAD_IN_MS,
    MELODIES,
    PEAK,
    SAMPLE_RATE,
    TIMBRES,
    render_chime,
    render_chime_set,
    write_wav,
)
from microdrop_style.sounds.chimes import CHIME_NAMES


def _design(**changes):
    return {**DEFAULT_DESIGN, **changes}


def test_every_timbre_and_melody_renders_finite_sound():

    for timbre in TIMBRES:
        for melody in MELODIES:
            for name in CHIME_NAMES:
                samples = render_chime(name, **_design(timbre=timbre, melody=melody))

                assert np.all(np.isfinite(samples))
                assert np.max(np.abs(samples)) > 0


def test_the_set_shares_one_gain_and_a_lead_in():
    designs = {name: _design(timbre="marimba") for name in CHIME_NAMES}

    chimes = render_chime_set(designs)
    lead_in = int(SAMPLE_RATE * LEAD_IN_MS / 1000)
    peaks = [np.max(np.abs(samples)) for samples in chimes.values()]

    assert set(chimes) == set(CHIME_NAMES)
    assert np.isclose(max(peaks), PEAK)
    assert all(not np.any(samples[:lead_in]) for samples in chimes.values())


def test_a_longer_ring_makes_a_longer_chime():
    short = render_chime("gentle", **_design(ring_length=50))
    long = render_chime("gentle", **_design(ring_length=200))

    assert len(long) > len(short)


def test_the_wav_holds_the_samples(tmp_path):
    path = tmp_path / "chime.wav"
    samples = render_chime_set({name: _design() for name in CHIME_NAMES})["alert"]

    write_wav(path, samples)

    with wave.open(str(path)) as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == SAMPLE_RATE
        assert wav.getnframes() == len(samples)
