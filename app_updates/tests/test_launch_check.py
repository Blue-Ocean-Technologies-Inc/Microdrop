# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The background check after startup: what it does for each set of facts."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.source_version import DEVELOPMENT, MANAGED, NO_GIT

# Local imports.
from ..consts import (
    ANNOUNCE,
    LOG_DOWNLOADED,
    NO_ACTION,
    POLICY_LATEST,
    POLICY_STAY,
)
from ..launch_check import launch_check_action, may_check


def _action(**facts):
    """Return the action under POLICY_STAY on release v1.45.0, nothing
    announced yet, with ``facts`` overriding the defaults."""
    defaults = dict(
        policy=POLICY_STAY,
        newest_panel_tag=None,
        current_release="v1.45.0",
        last_announced="",
    )
    defaults.update(facts)

    return launch_check_action(**defaults)


# --- may_check: the gate before any fetch -----------------------------------------


def test_may_check_a_managed_checkout_without_the_skip_variable():
    assert may_check(MANAGED, False)


@pytest.mark.parametrize("state", [DEVELOPMENT, NO_GIT])
def test_may_not_check_an_unmanaged_checkout(state):
    assert not may_check(state, False)


def test_may_not_check_with_the_skip_variable_set():
    assert not may_check(MANAGED, True)


# --- policy "latest" -----------------------------------------------------------


def test_latest_with_a_newer_panel_release_logs_it():
    action = _action(policy=POLICY_LATEST, newest_panel_tag="v1.46.0")

    assert action == (LOG_DOWNLOADED, "v1.46.0")


def test_latest_logs_any_release_to_a_checkout_built_on_none():
    action = _action(
        policy=POLICY_LATEST,
        newest_panel_tag="v1.46.0",
        current_release=None,
    )

    assert action == (LOG_DOWNLOADED, "v1.46.0")


def test_latest_without_a_panel_release_does_nothing():
    assert _action(policy=POLICY_LATEST) == (NO_ACTION, None)


@pytest.mark.parametrize("newest", ["v1.45.0", "v1.44.0"])
def test_latest_with_the_current_or_an_older_release_does_nothing(newest):
    action = _action(policy=POLICY_LATEST, newest_panel_tag=newest)

    assert action == (NO_ACTION, None)


def test_latest_logs_even_an_already_announced_release():
    action = _action(
        policy=POLICY_LATEST,
        newest_panel_tag="v1.46.0",
        last_announced="v1.46.0",
    )

    assert action == (LOG_DOWNLOADED, "v1.46.0")


# --- policy "stay" -------------------------------------------------------------


def test_stay_announces_a_newer_release():
    assert _action(newest_panel_tag="v1.46.0") == (ANNOUNCE, "v1.46.0")


def test_stay_announces_any_release_to_a_checkout_built_on_none():
    action = _action(newest_panel_tag="v1.46.0", current_release=None)

    assert action == (ANNOUNCE, "v1.46.0")


def test_stay_without_a_panel_release_does_nothing():
    assert _action(newest_panel_tag=None) == (NO_ACTION, None)


def test_stay_does_not_announce_a_release_twice():
    action = _action(newest_panel_tag="v1.46.0", last_announced="v1.46.0")

    assert action == (NO_ACTION, None)


def test_stay_announces_a_release_newer_than_the_last_announced():
    action = _action(newest_panel_tag="v1.47.0", last_announced="v1.46.0")

    assert action == (ANNOUNCE, "v1.47.0")


@pytest.mark.parametrize("newest", ["v1.45.0", "v1.44.0"])
def test_stay_does_not_announce_the_current_or_an_older_release(newest):
    assert _action(newest_panel_tag=newest) == (NO_ACTION, None)
