# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""User- and hardware-disabled channels: the electrodes model keeps both
kinds apart, unions them for its readers, and mirrors the user's set to
app_globals (the conftest's dict here) for the backends to filter against."""

# Microdrop package imports.
from device_viewer.consts import (
    USER_DISABLED_CHANNELS_KEY,
    user_disabled_channels_mirror,
)
from device_viewer.models import disabled_channels
from device_viewer.models.disabled_channels import split_disabled_channels
from device_viewer.models.electrodes import Electrodes


def _mirrored():
    return disabled_channels.app_globals[USER_DISABLED_CHANNELS_KEY]


def test_split_keeps_the_enabled_channels_and_reports_the_dropped():
    assert split_disabled_channels([5, 1, 3], {3, 9}) == ([1, 5], [3])


def test_split_of_only_disabled_channels_keeps_nothing():
    assert split_disabled_channels([2], {2}) == ([], [2])


def test_mirror_round_trips_as_a_sorted_list():
    user_disabled_channels_mirror.write({3, 1})

    assert _mirrored() == [1, 3]
    assert user_disabled_channels_mirror.read() == {1, 3}


def test_drop_from_also_drops_the_extra_disabled_channels():
    user_disabled_channels_mirror.write({4})

    kept = user_disabled_channels_mirror.drop_from([1, 2, 4], "test", also_disabled=[2])

    assert kept == [1]


def test_drop_from_with_nothing_mirrored_keeps_every_channel():
    assert user_disabled_channels_mirror.drop_from({2, 1}, "test") == [1, 2]


def test_disabled_channels_is_the_union_of_both_kinds():
    electrodes = Electrodes()

    electrodes.user_disabled_channels.add(1)
    electrodes.hardware_disabled_channels = {1, 2}

    assert electrodes.disabled_channels == {1, 2}

    electrodes.hardware_disabled_channels = set()

    assert electrodes.disabled_channels == {1}


def test_construction_overwrites_a_previous_sessions_mirror():
    disabled_channels.app_globals[USER_DISABLED_CHANNELS_KEY] = [9]

    Electrodes()

    assert _mirrored() == []


def test_only_the_user_set_is_mirrored():
    electrodes = Electrodes()

    electrodes.user_disabled_channels.add(4)
    electrodes.hardware_disabled_channels = {5}

    assert _mirrored() == [4]

    electrodes.user_disabled_channels.clear()

    assert _mirrored() == []
