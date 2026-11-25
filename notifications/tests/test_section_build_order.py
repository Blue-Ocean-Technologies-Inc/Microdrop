# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Which queued section the drawer builds next: News first in the drawer
the app opened at start-up."""

# Microdrop package imports.
from notifications.consts import NotificationSection
from notifications.models.notifications_pane_model import next_section_to_build


def _queue():
    plugins = NotificationSection(id="plugins", title="Plugins")
    activity = NotificationSection(id="activity", title="Activity")
    news = NotificationSection(id="news", title="News", expanded_at_start=True)

    return [plugins, activity, news]


def test_the_app_opened_drawer_builds_a_section_expanded_at_start_first():
    queued = _queue()

    assert next_section_to_build(queued, opened_by_app=True).id == "news"


def test_a_drawer_the_user_opened_builds_the_oldest_first():
    queued = _queue()

    assert next_section_to_build(queued, opened_by_app=False).id == "plugins"


def test_without_a_section_expanded_at_start_the_oldest_goes_first():
    queued = _queue()[:2]

    assert next_section_to_build(queued, opened_by_app=True).id == "plugins"
