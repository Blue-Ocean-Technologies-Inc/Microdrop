# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The thumbnail loader's pure parts: the decode size covers the box and
never upscales, the crop is the middle, and the cache key follows the
file."""

# Standard library imports.
import os

# Microdrop utils imports.
from microdrop_utils.image_thumbnails import (
    centre_crop,
    cover_scaled_size,
    thumbnail_key,
)


def test_a_large_picture_decodes_just_big_enough_to_cover_the_box():
    # 4:3 into 4:3: exactly the box.
    assert cover_scaled_size((4000, 3000), (144, 108)) == (144, 108)

    # 16:9 into 4:3: as tall as the box, wider than it.
    width, height = cover_scaled_size((1920, 1080), (144, 108))

    assert height == 108
    assert width >= 144


def test_a_small_picture_is_never_scaled_up():
    assert cover_scaled_size((40, 30), (144, 108)) == (40, 30)


def test_the_crop_is_the_middle_of_the_picture():
    assert centre_crop((192, 108), (144, 108)) == (24, 0, 144, 108)


def test_a_side_shorter_than_the_box_is_kept_whole():
    assert centre_crop((40, 200), (144, 108)) == (0, 46, 40, 108)


def test_the_key_follows_the_file_and_the_box(tmp_path):
    photo = tmp_path / "a.png"
    photo.write_bytes(b"one")
    first = thumbnail_key(photo, (144, 108))

    assert first == thumbnail_key(str(photo), (144, 108))
    assert first != thumbnail_key(photo, (72, 54))

    photo.write_bytes(b"three")
    os.utime(photo, ns=(first[1] + 10**9, first[1] + 10**9))

    assert thumbnail_key(photo, (144, 108)) != first


def test_a_missing_file_has_no_key(tmp_path):
    assert thumbnail_key(tmp_path / "gone.png", (144, 108)) is None
