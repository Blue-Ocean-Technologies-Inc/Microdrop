# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""UpdatesModel: the versions list, the policy and the switch action, against
real throwaway git repositories."""

# Standard library imports.
import logging
import shutil

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences

# Microdrop utils imports.
from microdrop_utils import source_update_startup
from microdrop_utils.source_update_startup import (
    AUTO_UPDATE_PREFERENCE_PATH,
    LAST_ANNOUNCED_PREFERENCE_PATH,
    PROJECT_ROOT,
    SKIP_GIT_UPDATE_ENV_VAR,
)
from microdrop_utils.source_version import (
    DEVELOPMENT,
    NO_GIT,
    SourceVersionError,
    describe,
    exact_release,
)
from microdrop_utils.tests.git_repo_fixtures import run_git

# Local imports.
from .. import model as model_module
from ..consts import (
    NO_CHANGELOG_TEXT,
    POLICY_LATEST,
    POLICY_STAY,
    PREFERENCES_PATH,
    UNKNOWN_VERSION_TEXT,
)
from ..model import UpdatesModel
from ..preferences import AppUpdatesPreferences
from .model_factory import make_model

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)


def _row(model, name):
    return next(row for row in model.versions if row.name == name)


def test_rows_mark_latest_current_and_missing_panel(model_at_v1_2):
    markers = {row.name: (row.marker, row.panel_note) for row in model_at_v1_2.versions}

    assert markers == {
        "v1.10.0": ("latest", ""),
        "v1.2.0": ("current", ""),
        "v1.1.0": ("", "no update panel"),
        "v1.0.0": ("", "no update panel"),
    }
    assert [row.name for row in model_at_v1_2.versions] == [
        "v1.10.0",
        "v1.2.0",
        "v1.1.0",
        "v1.0.0",
    ]
    assert model_at_v1_2.current_description == "v1.2.0"


def test_marker_combines_latest_and_current(clone, preferences):
    run_git(clone, "checkout", "--detach", "v1.10.0")

    model = make_model(clone, preferences)

    assert _row(model, "v1.10.0").marker == "latest, current"
    assert model.action_enabled is False
    assert model.action_label == "Up to date"


def test_latest_policy_targets_newest_panel_version(model_at_v1_2):
    assert model_at_v1_2.policy == POLICY_LATEST
    assert model_at_v1_2.target.name == "v1.10.0"
    assert model_at_v1_2.action_label == "Switch to v1.10.0 and close"
    assert model_at_v1_2.action_enabled is True


def test_latest_policy_disabled_when_ahead_of_newest_tag(model_on_main_tip):
    assert model_on_main_tip.current_description.startswith("v1.10.0-1-g")
    assert not any(row.is_current for row in model_on_main_tip.versions)
    assert model_on_main_tip.target.name == "v1.10.0"
    assert model_on_main_tip.action_enabled is False
    assert model_on_main_tip.action_label == "Up to date"


def test_stay_policy_targets_selection_and_disables_on_current(model_at_v1_2):
    model_at_v1_2.policy = POLICY_STAY
    model_at_v1_2.selected = _row(model_at_v1_2, "v1.2.0")

    assert model_at_v1_2.target.name == "v1.2.0"
    assert model_at_v1_2.action_enabled is False
    assert model_at_v1_2.action_label == "Up to date"

    model_at_v1_2.selected = _row(model_at_v1_2, "v1.0.0")

    assert model_at_v1_2.target.name == "v1.0.0"
    assert model_at_v1_2.action_enabled is True
    assert model_at_v1_2.action_label == "Switch to v1.0.0 and close"
    assert model_at_v1_2.drops_unreleased_commits() is False


def test_stay_policy_without_selection_asks_for_one(model_at_v1_2):
    model_at_v1_2.policy = POLICY_STAY
    model_at_v1_2.selected = None

    assert model_at_v1_2.target is None
    assert model_at_v1_2.action_enabled is False
    assert model_at_v1_2.action_label == "Select a version"


def test_latest_is_the_newest_tag_with_the_panel(clone, preferences):
    run_git(clone, "rm", "-q", "app_updates/plugin.py")
    run_git(clone, "commit", "-m", "chore: release v1.11.0")
    run_git(clone, "tag", "v1.11.0")
    run_git(clone, "checkout", "--detach", "v1.2.0")

    model = make_model(clone, preferences)

    assert model.versions[0].name == "v1.11.0"
    assert model.versions[0].marker == ""
    assert model.versions[0].panel_note == "no update panel"
    assert _row(model, "v1.10.0").marker == "latest"
    assert model.target.name == "v1.10.0"
    assert model.action_label == "Switch to v1.10.0 and close"


def _head(repo_root):
    return run_git(repo_root, "rev-parse", "HEAD").stdout.strip()


def test_switch_refuses_under_latest_when_ahead_of_newest_tag(model_on_main_tip):
    head = _head(model_on_main_tip.repo_root)

    assert model_on_main_tip.action_enabled is False

    with pytest.raises(SourceVersionError):
        model_on_main_tip.switch()

    assert _head(model_on_main_tip.repo_root) == head


def test_switch_refuses_to_the_current_release(model_at_v1_2):
    model_at_v1_2.policy = POLICY_STAY
    model_at_v1_2.selected = _row(model_at_v1_2, "v1.2.0")

    with pytest.raises(SourceVersionError):
        model_at_v1_2.switch()

    assert describe(model_at_v1_2.repo_root) == "v1.2.0"


def test_action_notifies_when_policy_or_selection_changes(model_at_v1_2):
    labels = []

    model_at_v1_2.observe(
        lambda event: labels.append(model_at_v1_2.action_label), "action_label"
    )
    model_at_v1_2.policy = POLICY_STAY
    model_at_v1_2.selected = _row(model_at_v1_2, "v1.1.0")

    assert labels[0] == "Up to date"
    assert labels[-1] == "Switch to v1.1.0 and close"


def test_stay_policy_allows_stepping_back_from_unreleased_commits(
    model_on_main_tip,
):
    model_on_main_tip.policy = POLICY_STAY
    model_on_main_tip.selected = _row(model_on_main_tip, "v1.10.0")

    assert model_on_main_tip.action_enabled is True
    assert model_on_main_tip.action_label == "Switch to v1.10.0 and close"
    assert model_on_main_tip.drops_unreleased_commits() is True


def test_policy_change_is_saved_immediately(model_at_v1_2, preferences):
    model_at_v1_2.policy = POLICY_STAY

    assert preferences.get(AUTO_UPDATE_PREFERENCE_PATH) == "False"

    # Flushed: a fresh read of the file, as the next startup makes, agrees.
    saved = Preferences(filename=preferences.filename)

    assert saved.get(AUTO_UPDATE_PREFERENCE_PATH) == "False"


def test_default_policy_is_latest(model_at_v1_2, preferences):
    assert model_at_v1_2.policy == POLICY_LATEST
    assert model_at_v1_2.preferences.auto_update is True


def test_policy_initialises_from_saved_preference(clone_at_v1_2, preferences):
    preferences.set(AUTO_UPDATE_PREFERENCE_PATH, "False")

    model = make_model(clone_at_v1_2, preferences)

    assert model.policy == POLICY_STAY


def test_saved_policy_is_read_without_writing(clone_at_v1_2, preferences, monkeypatch):
    preferences.set(AUTO_UPDATE_PREFERENCE_PATH, "False")
    writes = []

    monkeypatch.setattr(preferences, "flush", lambda: writes.append("flush"))
    monkeypatch.setattr(
        preferences, "set", lambda path, value: writes.append((path, value))
    )

    model = make_model(clone_at_v1_2, preferences)
    model.refresh()

    assert model.policy == POLICY_STAY
    assert writes == []


def test_outside_preference_change_updates_policy(model_at_v1_2):
    model_at_v1_2.preferences.auto_update = False

    assert model_at_v1_2.policy == POLICY_STAY

    model_at_v1_2.preferences.auto_update = True

    assert model_at_v1_2.policy == POLICY_LATEST


def test_failed_save_is_logged(model_at_v1_2, preferences, monkeypatch, caplog):
    def locked():
        raise PermissionError(13, "Permission denied", preferences.filename)

    monkeypatch.setattr(preferences, "flush", locked)

    with caplog.at_level(logging.ERROR, logger=model_module.__name__):
        model_at_v1_2.policy = POLICY_STAY

    assert model_at_v1_2.policy == POLICY_STAY
    assert "Permission denied" in caplog.text
    assert AUTO_UPDATE_PREFERENCE_PATH in caplog.text


def test_changelog_follows_selection_with_fallback(model_at_v1_2):
    model_at_v1_2.selected = _row(model_at_v1_2, "v1.10.0")

    assert model_at_v1_2.changelog_markdown.startswith("## [v1.10.0]")
    assert "the v1.10.0 release" in model_at_v1_2.changelog_markdown

    model_at_v1_2.selected = _row(model_at_v1_2, "v1.0.0")

    assert model_at_v1_2.changelog_markdown == NO_CHANGELOG_TEXT


def test_development_checkout_disables_action(model_on_feature_branch):
    assert model_on_feature_branch.state == DEVELOPMENT
    assert model_on_feature_branch.state_reason == "branch feat/x"
    assert model_on_feature_branch.is_managed is False
    assert model_on_feature_branch.versions != []
    assert model_on_feature_branch.action_enabled is False

    with pytest.raises(SourceVersionError):
        model_on_feature_branch.switch()

    with pytest.raises(SourceVersionError):
        model_on_feature_branch.fetch()


def test_no_git_gives_empty_list(tmp_path, preferences):
    model = make_model(tmp_path / "no-git", preferences)

    assert model.state == NO_GIT
    assert model.current_description == UNKNOWN_VERSION_TEXT
    assert model.versions == []
    assert model.selected is None
    assert model.target is None
    assert model.action_enabled is False

    with pytest.raises(SourceVersionError):
        model.switch()


def test_refresh_keeps_selection_by_name(model_at_v1_2):
    model_at_v1_2.selected = _row(model_at_v1_2, "v1.1.0")
    old_row = model_at_v1_2.selected

    model_at_v1_2.refresh()

    assert model_at_v1_2.selected is not old_row
    assert model_at_v1_2.selected.name == "v1.1.0"


def test_initial_selection_is_the_current_row(model_at_v1_2):
    assert model_at_v1_2.selected.name == "v1.2.0"


def test_initial_selection_between_releases_is_the_built_on_release(
    model_on_main_tip,
):
    assert model_on_main_tip.selected.name == "v1.10.0"
    assert model_on_main_tip.changelog_markdown.startswith("## [v1.10.0]")


def test_switch_moves_checkout(model_at_v1_2):
    model_at_v1_2.switch()

    assert exact_release(model_at_v1_2.repo_root) == "v1.10.0"


def test_skip_variable_flag_reflects_environment(model_at_v1_2, monkeypatch):
    persisted = {}

    monkeypatch.setattr(
        source_update_startup, "user_environment_variable", persisted.get
    )
    model_at_v1_2.refresh()

    assert model_at_v1_2.skip_variable_set is False

    monkeypatch.setenv(SKIP_GIT_UPDATE_ENV_VAR, "1")
    model_at_v1_2.refresh()

    assert model_at_v1_2.skip_variable_set is True

    monkeypatch.delenv(SKIP_GIT_UPDATE_ENV_VAR)
    persisted[SKIP_GIT_UPDATE_ENV_VAR] = "1"
    model_at_v1_2.refresh()

    assert model_at_v1_2.skip_variable_set is True


def test_set_and_clear_skip_variable_write_the_user_environment(
    model_at_v1_2, monkeypatch
):
    writes = []

    monkeypatch.setattr(
        model_module,
        "set_user_environment_variable",
        lambda name, value: writes.append(("set", name, value)),
    )
    monkeypatch.setattr(
        model_module,
        "unset_user_environment_variable",
        lambda name: writes.append(("unset", name)),
    )

    model_at_v1_2.set_skip_variable()
    model_at_v1_2.clear_skip_variable()

    assert writes == [
        ("set", SKIP_GIT_UPDATE_ENV_VAR, "1"),
        ("unset", SKIP_GIT_UPDATE_ENV_VAR),
    ]
    # Left to refresh(), which the controller runs on the GUI thread.
    assert model_at_v1_2.skip_variable_set is False


def test_default_repo_root_is_the_source_checkout():
    assert UpdatesModel().repo_root == str(PROJECT_ROOT)


def test_preferences_path_matches_startup_constant():
    assert AUTO_UPDATE_PREFERENCE_PATH == f"{PREFERENCES_PATH}.auto_update"
    assert LAST_ANNOUNCED_PREFERENCE_PATH == (
        f"{PREFERENCES_PATH}.last_announced_version"
    )
    helper = AppUpdatesPreferences(preferences=Preferences())

    assert helper.preferences_path == PREFERENCES_PATH
