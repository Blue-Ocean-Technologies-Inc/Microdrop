# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The chime designer: the base and each tone's own design, editing them
through one set of fields, saving them, and the sound file each tone plays."""

# Microdrop package imports.
from notifications.consts import TONE_ALERT, TONE_COMPLETION, TONE_SOFT
from notifications.models.chime_designer import (
    ALL_TONES,
    BASE_KEY,
    OVERRIDES_KEY,
    ChimeDesigner,
)
from notifications.models.settings import CHIME_KEY, NotificationSettings
from notifications.services.chime_sounds import (
    SHIPPED_TONE_SOUNDS,
    remove_stale_sounds,
    tone_sound_paths,
)


def test_the_default_design_is_the_shipped_set(tmp_path):
    designer = ChimeDesigner()

    assert designer.is_default()
    assert tone_sound_paths(designer, tmp_path) == SHIPPED_TONE_SOUNDS
    assert list(tmp_path.iterdir()) == []


def test_editing_all_tones_changes_the_base():
    designer = ChimeDesigner()

    designer.timbre = "marimba"

    assert designer.base.timbre == "marimba"
    assert designer.overrides == {}
    assert designer.design(TONE_ALERT).timbre == "marimba"


def test_editing_one_tone_gives_it_its_own_design_from_the_base():
    designer = ChimeDesigner()
    designer.room = 50

    designer.editing_tone = TONE_ALERT
    designer.timbre = "kalimba"

    assert designer.has_override
    assert designer.design(TONE_ALERT).timbre == "kalimba"
    assert designer.design(TONE_ALERT).room == 50
    assert designer.design(TONE_SOFT).timbre == "current"


def test_choosing_a_tone_shows_its_design_without_editing_it():
    designer = ChimeDesigner()
    designer.editing_tone = TONE_ALERT
    designer.pitch_shift = 3

    designer.editing_tone = TONE_SOFT

    assert designer.pitch_shift == 0
    assert TONE_SOFT not in designer.overrides

    designer.editing_tone = ALL_TONES

    assert designer.pitch_shift == 0


def test_use_the_base_drops_the_tone_override():
    designer = ChimeDesigner(editing_tone=TONE_ALERT)
    designer.melody = "doorbell"

    designer.use_base = True

    assert TONE_ALERT not in designer.overrides
    assert designer.melody == "classic"
    assert not designer.has_override


def test_reset_restores_the_default_set():
    designer = ChimeDesigner()
    designer.ring_length = 150
    designer.editing_tone = TONE_COMPLETION
    designer.timbre = "vibraphone"

    designer.reset_to_default = True

    assert designer.is_default()
    assert designer.overrides == {}


def test_every_change_fires_updated():
    designer = ChimeDesigner()
    updates = []
    designer.observe(updates.append, "updated")

    designer.room = 120
    designer.editing_tone = TONE_ALERT
    designer.room = 80
    designer.use_base = True

    assert len(updates) == 3


def test_a_preview_button_asks_for_its_tone():
    designer = ChimeDesigner()
    previews = []
    designer.observe(lambda event: previews.append(event.new), "preview")

    designer.play_completion = True

    assert previews == [TONE_COMPLETION]


def test_the_designs_survive_a_save_and_load():
    settings = NotificationSettings()
    settings.chime.timbre = "felt_piano"
    settings.chime.editing_tone = TONE_ALERT
    settings.chime.pitch_shift = -5

    loaded = NotificationSettings()
    rejected = loaded.apply_state(settings.to_state())

    assert rejected == []
    assert loaded.chime.base.timbre == "felt_piano"
    assert loaded.chime.design(TONE_ALERT).pitch_shift == -5
    assert loaded.chime.design(TONE_SOFT).pitch_shift == 0


def test_unusable_saved_designs_are_reported_and_ignored():
    state = {
        CHIME_KEY: {
            BASE_KEY: {"timbre": "tuba"},
            OVERRIDES_KEY: {TONE_ALERT: {"room": 999}, "nonsense": {}},
        }
    }
    settings = NotificationSettings()

    rejected = settings.apply_state(state)

    assert sorted(rejected) == [
        f"{CHIME_KEY}.{BASE_KEY}",
        f"{CHIME_KEY}.{OVERRIDES_KEY}.{TONE_ALERT}",
        f"{CHIME_KEY}.{OVERRIDES_KEY}.nonsense",
    ]
    assert settings.chime.is_default()


def test_only_customised_tones_are_rendered(tmp_path):
    designer = ChimeDesigner(editing_tone=TONE_ALERT)
    designer.timbre = "marimba"

    paths = tone_sound_paths(designer, tmp_path)

    assert paths[TONE_SOFT] == SHIPPED_TONE_SOUNDS[TONE_SOFT]
    assert paths[TONE_ALERT].parent == tmp_path
    assert list(tmp_path.iterdir()) == [paths[TONE_ALERT]]


def test_a_new_design_renders_under_a_new_name(tmp_path):
    designer = ChimeDesigner()
    designer.timbre = "marimba"
    first = tone_sound_paths(designer, tmp_path)

    assert tone_sound_paths(designer, tmp_path) == first

    designer.room = 40
    second = tone_sound_paths(designer, tmp_path)
    rendered = sorted(path for path in second.values() if path.parent == tmp_path)

    assert second[TONE_ALERT] != first[TONE_ALERT]

    remove_stale_sounds(tmp_path, set(second.values()))

    assert sorted(tmp_path.iterdir()) == rendered
