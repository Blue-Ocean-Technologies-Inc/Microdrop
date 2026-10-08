# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pruning of crashed sessions' listener queues from the router (#719)."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import prune_dead_listener_queues
from microdrop_utils.session_heartbeat import listener_queue_from_dramatiq_key

DEAD = "_0b5e1c9a-dead-4c0d-9f2e-000000000001"
LIVE = "_7f3a2b10-live-4c0d-9f2e-000000000002"
BROKER_ID = "3c9d6e2f-1a4b-4c8d-9e0f-123456789abc"


def test_pairs_on_dead_queues_are_removed():
    subscriber_map = {
        "dropbot/signals/#": [["ui_listener", DEAD], ["ui_listener", LIVE]],
        "dropbot/requests/+": [["dropbot_listener", "default"], ["probe", DEAD]],
    }

    pruned = prune_dead_listener_queues(subscriber_map, {DEAD})

    assert pruned == {
        "dropbot/signals/#": [["ui_listener", LIVE]],
        "dropbot/requests/+": [["dropbot_listener", "default"]],
    }


def test_topics_left_without_subscribers_are_dropped():
    subscriber_map = {
        "camera/signals/frame": [["viewer_listener", DEAD]],
        "camera/requests/start": [["camera_listener", LIVE]],
    }

    pruned = prune_dead_listener_queues(subscriber_map, {DEAD})

    assert pruned == {"camera/requests/start": [["camera_listener", LIVE]]}


def test_shared_queues_are_never_pruned():
    subscriber_map = {"logs/#": [["logger_listener", "default"]]}

    pruned = prune_dead_listener_queues(subscriber_map, {"default"})

    assert pruned == subscriber_map


def test_bytes_topics_are_decoded():
    subscriber_map = {
        b"device/signals/loaded": [["viewer_listener", DEAD], ["ui", LIVE]],
    }

    pruned = prune_dead_listener_queues(subscriber_map, {DEAD})

    assert pruned == {"device/signals/loaded": [["ui", LIVE]]}


def test_map_with_nothing_dead_is_unchanged():
    subscriber_map = {
        "dropbot/signals/#": [["ui_listener", LIVE]],
        "dropbot/requests/+": [["dropbot_listener", "default"]],
    }

    pruned = prune_dead_listener_queues(subscriber_map, {DEAD})

    assert pruned == subscriber_map


@pytest.mark.parametrize(
    "key",
    [
        f"dramatiq:{DEAD}",
        f"dramatiq:{DEAD}.msgs",
        f"dramatiq:{DEAD}.DQ",
        f"dramatiq:{DEAD}.DQ.msgs",
        f"dramatiq:{DEAD}.XQ",
        f"dramatiq:{DEAD}.XQ.msgs",
        f"dramatiq:__acks__.{BROKER_ID}.{DEAD}",
        f"dramatiq:__acks__.{BROKER_ID}.{DEAD}.DQ",
        f"dramatiq:{DEAD}".encode(),
    ],
)
def test_listener_queue_is_derived_from_its_dramatiq_keys(key):
    assert listener_queue_from_dramatiq_key(key) == DEAD


@pytest.mark.parametrize(
    "key",
    [
        "dramatiq:default",
        "dramatiq:default.DQ.msgs",
        f"dramatiq:__acks__.{BROKER_ID}.default",
        "dramatiq:__heartbeats__",
        f"other:{DEAD}",
        "microdrop:message_router_data",
    ],
)
def test_non_listener_keys_give_no_queue(key):
    assert listener_queue_from_dramatiq_key(key) is None
