# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A press outside the open drawer closes it; it also reaches what was
pressed only on a drawer the app opened and the user has not used yet."""

# Microdrop package imports.
from notifications.models.notifications_pane_model import (
    NotificationsPaneModel,
    outside_press_passes_through,
)


def test_a_press_outside_an_unused_app_opened_drawer_passes_through():
    assert outside_press_passes_through(opened_by_app=True, used_while_open=False)


def test_a_press_outside_a_drawer_the_user_owns_is_used_up():
    assert not outside_press_passes_through(opened_by_app=False, used_while_open=False)
    assert not outside_press_passes_through(opened_by_app=True, used_while_open=True)
    assert not outside_press_passes_through(opened_by_app=False, used_while_open=True)


def test_closing_forgets_who_opened_the_drawer_and_its_use():
    model = NotificationsPaneModel(opened_by_app=True, is_open=True)
    model.used_while_open = True

    model.is_open = False

    assert not model.opened_by_app
    assert not model.used_while_open
