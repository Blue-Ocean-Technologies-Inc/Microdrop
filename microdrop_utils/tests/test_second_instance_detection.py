# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Detection of a second MicroDrop instance sharing the same Redis (#1222)."""

# Microdrop utils imports.
from microdrop_utils.session_heartbeat import sibling_queues_sharing_actors

OWN = "_7f3a2b10-own0-4c0d-9f2e-000000000001"
SIBLING = "_0b5e1c9a-sibl-4c0d-9f2e-000000000002"

FRONTEND_ACTORS = {"device_viewer_listener", "notifications_listener"}
BACKEND_ACTORS = {"dropbot_controller_listener", "electrode_controller_listener"}


def test_second_full_instance_shares_actors():
    subscriber_map = {
        "dropbot/requests/#": [
            ["dropbot_controller_listener", OWN],
            ["dropbot_controller_listener", SIBLING],
        ],
        "ui/notifications/post": [
            ["notifications_listener", OWN],
            ["notifications_listener", SIBLING],
        ],
    }

    shared = sibling_queues_sharing_actors(
        subscriber_map, OWN, FRONTEND_ACTORS | BACKEND_ACTORS
    )

    assert shared == {
        SIBLING: {"dropbot_controller_listener", "notifications_listener"}
    }


def test_split_frontend_and_backend_share_nothing():
    subscriber_map = {
        "dropbot/requests/#": [["dropbot_controller_listener", SIBLING]],
        "ui/notifications/post": [["notifications_listener", OWN]],
    }

    assert sibling_queues_sharing_actors(subscriber_map, OWN, FRONTEND_ACTORS) == {}


def test_shared_default_queue_is_not_a_sibling():
    subscriber_map = {
        "dropbot/requests/#": [["dropbot_controller_listener", "default"]]
    }

    assert sibling_queues_sharing_actors(subscriber_map, OWN, BACKEND_ACTORS) == {}
