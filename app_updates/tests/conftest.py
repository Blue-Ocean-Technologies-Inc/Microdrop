# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fixtures for the app_updates tests: updates models on throwaway git
repositories, with preferences in a temporary file and the user's real
environment variables out of reach.

The git repository fixtures are imported for pytest to register; the model
fixtures request them by those same names, which ruff reads as
redefinitions (F811)."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences

# Microdrop utils imports.
from microdrop_utils import source_update_startup
from microdrop_utils.source_update_startup import SKIP_GIT_UPDATE_ENV_VAR
from microdrop_utils.tests.git_repo_fixtures import (  # noqa: F401
    clone,
    clone_at_v1_2,
    run_git,
    source_repo,
)

# Local imports.
from .. import model as model_module
from .model_factory import make_model


@pytest.fixture(autouse=True)
def no_user_environment(monkeypatch):
    """Keep this machine's skip variable — in the process or saved for the
    user — out of every test, and refuse any write to the real registry or
    profile unless a test replaces the writers itself."""

    def refuse(*args):
        raise AssertionError("a test wrote the user's real environment")

    monkeypatch.delenv(SKIP_GIT_UPDATE_ENV_VAR, raising=False)
    monkeypatch.setattr(
        source_update_startup, "user_environment_variable", lambda name: None
    )
    monkeypatch.setattr(model_module, "set_user_environment_variable", refuse)
    monkeypatch.setattr(model_module, "unset_user_environment_variable", refuse)


@pytest.fixture
def preferences(tmp_path):
    """Preferences backed by a temporary file, so a flush can be read back."""
    return Preferences(filename=str(tmp_path / "preferences.ini"))


@pytest.fixture
def model_at_v1_2(clone_at_v1_2, preferences):  # noqa: F811
    """A model on a checkout detached at ``v1.2.0``, an older panel release."""
    return make_model(clone_at_v1_2, preferences)


@pytest.fixture
def model_on_main_tip(clone, preferences):  # noqa: F811
    """A model on ``main``, one unreleased commit past ``v1.10.0``."""
    return make_model(clone, preferences)


@pytest.fixture
def model_on_feature_branch(clone, preferences):  # noqa: F811
    """A model on a development checkout: branch ``feat/x`` at ``v1.2.0``."""
    run_git(clone, "checkout", "-b", "feat/x", "v1.2.0")

    return make_model(clone, preferences)
