# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notification settings kept in settings.json: loaded, saved after a
change, defaults when the file is missing or unreadable, saved choices for
categories declared later; and the start-up override."""

# Standard library imports.
import json

# Microdrop package imports.
from notifications.consts import (
    OPEN_AT_START_ENV,
    TONE_ALERT,
    TONE_SOFT,
    NotificationCategorySpec,
)
from notifications.models.settings import (
    DEFAULT_TOAST_SECONDS,
    NotificationSettings,
    opens_at_start,
)
from notifications.services.settings_store import NotificationSettingsStore

SPEC = NotificationCategorySpec(id="demo.done", group="Demo", label="Done")
LATE_SPEC = NotificationCategorySpec(id="late.done", group="Late", label="Done")


class _Later:
    """Stands in for the GUI's ``invoke_after``: holds the calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, milliseconds, callable):
        self.calls.append(callable)

    def run(self):
        calls, self.calls = self.calls, []

        for callable in calls:
            callable()


def _store(path, settings=None):
    later = _Later()
    store = NotificationSettingsStore(
        settings=settings or NotificationSettings(), path=path, invoke_after=later
    )

    return store, later


def test_the_override_wins_over_the_saved_setting():
    assert opens_at_start(True, {OPEN_AT_START_ENV: "0"}) is False
    assert opens_at_start(False, {OPEN_AT_START_ENV: "1"}) is True


def test_without_an_override_the_saved_setting_decides():
    assert opens_at_start(True, {}) is True
    assert opens_at_start(False, {}) is False
    assert opens_at_start(False, {OPEN_AT_START_ENV: "yes"}) is False


def test_a_missing_file_means_the_defaults(tmp_path):
    store, later = _store(tmp_path / "settings.json")

    store.load()

    assert store.settings.open_at_start is True
    assert store.settings.auto_dismiss_seconds == DEFAULT_TOAST_SECONDS
    assert later.calls == []


def test_an_unreadable_file_means_the_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    store = _store(path)[0]

    store.load()

    assert store.settings.open_at_start is True


def test_a_change_is_saved_once_and_loaded_back(tmp_path):
    path = tmp_path / "settings.json"
    settings = NotificationSettings()
    settings.declare([SPEC])
    store, later = _store(path, settings)
    store.load()

    settings.open_at_start = False
    settings.sound_volume = 30
    settings.category(SPEC.id).tone = TONE_SOFT

    assert len(later.calls) == 1

    later.run()
    saved = json.loads(path.read_text(encoding="utf-8"))
    loaded = NotificationSettings()
    loaded.declare([SPEC])
    _store(path, loaded)[0].load()

    assert saved["open_at_start"] is False
    assert loaded.open_at_start is False
    assert loaded.sound_volume == 30
    assert loaded.category(SPEC.id).tone == TONE_SOFT


def test_loading_saves_nothing(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"open_at_start": False}), encoding="utf-8")
    store, later = _store(path)

    store.load()

    assert store.settings.open_at_start is False
    assert later.calls == []


def test_a_category_declared_later_takes_its_saved_choices(tmp_path):
    path = tmp_path / "settings.json"
    state = {"categories": {LATE_SPEC.id: {"popup": False, "tone": TONE_ALERT}}}
    path.write_text(json.dumps(state), encoding="utf-8")
    store, later = _store(path)
    store.load()

    store.settings.declare([LATE_SPEC])
    category = store.settings.category(LATE_SPEC.id)

    assert category.popup is False
    assert category.tone == TONE_ALERT
    assert later.calls == []


def test_choices_of_categories_not_declared_are_saved_again(tmp_path):
    path = tmp_path / "settings.json"
    state = {"categories": {LATE_SPEC.id: {"popup": False}}}
    path.write_text(json.dumps(state), encoding="utf-8")
    store, later = _store(path)
    store.load()

    store.settings.sound_enabled = False
    store.flush()
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["categories"][LATE_SPEC.id] == {"popup": False}


def test_unusable_values_keep_their_defaults():
    settings = NotificationSettings()
    settings.declare([SPEC])

    rejected = settings.apply_state(
        {
            "auto_dismiss_seconds": 1000,
            "open_at_start": "no",
            "categories": {SPEC.id: {"tone": "trumpet"}},
        }
    )

    assert settings.auto_dismiss_seconds == DEFAULT_TOAST_SECONDS
    assert settings.open_at_start is True
    assert settings.category(SPEC.id).tone == SPEC.tone
    assert sorted(rejected) == [
        "auto_dismiss_seconds",
        f"categories.{SPEC.id}.tone",
        "open_at_start",
    ]
