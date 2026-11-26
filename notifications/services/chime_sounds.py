# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The sound file each tone plays, from the chime designer, Qt-free.

A tone whose design is the default plays its shipped WAV. The others are
rendered (``microdrop_style.sounds.chime_synth``) into a folder, named by a
digest of the whole set's designs: one gain scales the set, so a tone's
file depends on every design, and a new name per design keeps Qt's sound
effects, which cache by path, from playing an old one. A file already
rendered for the same designs is reused.
"""

# Standard library imports.
import hashlib
import json

# Microdrop style imports.
from microdrop_style.sounds.chime_synth import render_chime_set, write_wav
from microdrop_style.sounds.chimes import SHIPPED_CHIMES

# Local imports.
from ..consts import (
    TONE_ALERT,
    TONE_COMPLETION,
    TONE_CONNECTED,
    TONE_DISCONNECTED,
    TONE_SOFT,
)
from ..models.chime_designer import SOUNDING_TONES

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Each tone's chime, by the name the shipped files and melodies use.
TONE_CHIME_NAMES = {
    TONE_SOFT: "gentle",
    TONE_CONNECTED: "connected",
    TONE_DISCONNECTED: "disconnected",
    TONE_ALERT: "alert",
    TONE_COMPLETION: "completion",
}

#: Each tone's shipped sound.
SHIPPED_TONE_SOUNDS = {
    tone: SHIPPED_CHIMES[name] for tone, name in TONE_CHIME_NAMES.items()
}

#: Part of every digest: raise it when the synthesis changes, so files
#: rendered by the old one are not reused.
RENDER_VERSION = 1

#: Characters of the digest in a rendered file's name.
DIGEST_LENGTH = 10


def designs_digest(designs):
    """A short digest of ``designs`` (each chime's design, by name)."""
    text = json.dumps([RENDER_VERSION, designs], sort_keys=True)

    return hashlib.sha1(text.encode()).hexdigest()[:DIGEST_LENGTH]


def tone_sound_paths(designer, folder):
    """Each sounding tone's sound file: the shipped one for a tone of the
    default design, else one rendered into ``folder``, rendering the set
    there first if needed."""
    paths = dict(SHIPPED_TONE_SOUNDS)
    custom = [tone for tone in SOUNDING_TONES if not designer.design(tone).is_default()]

    if not custom:
        return paths

    designs = {
        TONE_CHIME_NAMES[tone]: designer.design(tone).to_state()
        for tone in SOUNDING_TONES
    }
    digest = designs_digest(designs)

    for tone in custom:
        paths[tone] = folder / f"chime_{TONE_CHIME_NAMES[tone]}_{digest}.wav"

    missing = [tone for tone in custom if not paths[tone].exists()]

    if missing:
        rendered = render_chime_set(designs)
        folder.mkdir(parents=True, exist_ok=True)

        for tone in missing:
            _write_whole(paths[tone], rendered[TONE_CHIME_NAMES[tone]])

        logger.debug(f"Rendered chimes {digest} for {missing} into {folder}")

    return paths


def remove_stale_sounds(folder, keep):
    """Delete the rendered sounds in ``folder`` not among ``keep``; one
    still open (on Windows) stays until a later call."""

    if not folder.is_dir():
        return

    for path in folder.glob("chime_*.wav"):
        if path in keep:
            continue

        try:
            path.unlink()

        except OSError as error:
            logger.debug(f"Old chime {path.name} kept for now: {error}")


def _write_whole(path, samples):
    """Write ``path`` by way of a temporary file, so a rendering cut short
    never leaves a partial file under the name that is reused."""
    partial = path.with_suffix(".partial")

    write_wav(partial, samples)
    partial.replace(path)
