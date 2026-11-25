# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The settings window's rules: its size on the screen, which "By kind"
sections start expanded, the filter and the section summary; and the
kinds' reset to their declared defaults."""

# Microdrop package imports.
from notifications.consts import TONE_ALERT, TONE_SOFT, NotificationCategorySpec
from notifications.models.settings import NotificationSettings
from notifications.models.settings_window import (
    EXPAND_ALL_MAX_KINDS,
    MIN_WINDOW_SIZE,
    fitted_window_size,
    kind_matches,
    kinds_summary,
    sections_expanded_at_first,
)

SPECS = [
    NotificationCategorySpec(id="demo.done", group="Demo", label="Done"),
    NotificationCategorySpec(
        id="demo.failed", group="Demo", label="Failed", tone=TONE_ALERT
    ),
    NotificationCategorySpec(
        id="demo.lost", group="Demo", label="Lost", drawer=False, critical=True
    ),
]


def test_window_fits_the_screen_height():
    assert fitted_window_size((540, 600), 1000) == (540, 600)
    assert fitted_window_size((540, 600), 600) == (540, 480)


def test_window_never_below_its_minimum_width():
    assert fitted_window_size((100, 600), 1000)[0] == MIN_WINDOW_SIZE[0]


def test_few_kinds_expand_every_section():
    assert sections_expanded_at_first([3, 4, 2]) == [True, True, True]


def test_many_kinds_expand_only_the_first_section():
    counts = [EXPAND_ALL_MAX_KINDS, 1, 2]

    assert sections_expanded_at_first(counts) == [True, False, False]


def test_filter_matches_every_word_ignoring_case():
    assert kind_matches("Step completed", "")
    assert kind_matches("Step completed", "STEP")
    assert kind_matches("Step completed", "comp step")
    assert not kind_matches("Step completed", "step failed")


def test_summary_counts_kinds_shown_and_changed():
    assert kinds_summary(1, 0) == "1 kind"
    assert kinds_summary(4, 2) == "4 kinds · 2 changed"
    assert kinds_summary(4, 0, shown=1) == "1 of 4 kinds"


def test_reset_restores_the_declared_defaults():
    settings = NotificationSettings()
    settings.declare(SPECS)
    group = settings.group("Demo")
    done, failed, lost = group.categories

    done.popup = False
    failed.tone = TONE_SOFT

    assert group.changed_count == 2

    group.reset()

    assert done.popup and failed.tone == TONE_ALERT
    assert group.changed_count == 0


def test_critical_kind_defaults_to_kept():
    settings = NotificationSettings()
    settings.declare(SPECS)
    lost = settings.category("demo.lost")

    assert lost.in_drawer and not lost.changed


def test_reset_categories_keeps_the_general_settings():
    settings = NotificationSettings(sound_enabled=False)
    settings.declare(SPECS)
    settings.category("demo.done").popup = False

    settings.reset_categories()

    assert settings.category("demo.done").popup
    assert not settings.sound_enabled
