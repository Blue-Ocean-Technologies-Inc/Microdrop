# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hardware-free tests for ``libcamera_tuning``: the sysfs sub-device names
and libcamera's tuning directory are built under ``tmp_path``."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Microdrop utils imports.
import microdrop_utils.libcamera_tuning as tuning_module

TUNING = {
    "version": 2.0,
    "target": "pisp",
    "algorithms": [
        {"rpi.black_level": {"black_level": 4096}},
        {"rpi.af": {"map": [0.0, 420, 35.0, 920]}},
        {"rpi.hdr": {}},
    ],
}


@pytest.fixture
def pi(tmp_path, monkeypatch):
    """A Pi 5 with an imx708 and its lens; returns the cache directory."""
    sysfs = tmp_path / "sys"

    for index, name in enumerate(
        ["csi2", "pisp-fe", "imx708_wide_noir", "dw9807 11-000c"]
    ):
        subdevice = sysfs / f"v4l-subdev{index}"
        subdevice.mkdir(parents=True)
        (subdevice / "name").write_text(f"{name}\n")

    for pipeline in ("pisp", "vc4"):
        tuning_dir = tmp_path / "ipa" / pipeline
        tuning_dir.mkdir(parents=True)
        (tuning_dir / "imx708_wide_noir.json").write_text(
            json.dumps({**TUNING, "target": pipeline})
        )

    monkeypatch.setattr(
        tuning_module, "V4L2_SUBDEVICE_NAME_GLOB", str(sysfs / "v4l-subdev*" / "name")
    )
    monkeypatch.setattr(tuning_module, "LIBCAMERA_TUNING_DIR", tmp_path / "ipa")
    monkeypatch.delenv(tuning_module.LIBCAMERA_TUNING_FILE_ENV, raising=False)

    return tmp_path / "cache"


def test_strip_autofocus_algorithm_drops_only_rpi_af():
    stripped = tuning_module.strip_autofocus_algorithm(TUNING)

    assert [list(algorithm) for algorithm in stripped["algorithms"]] == [
        ["rpi.black_level"],
        ["rpi.hdr"],
    ]
    assert stripped["target"] == "pisp"
    assert len(TUNING["algorithms"]) == 3


def test_strip_autofocus_algorithm_none_without_rpi_af():
    assert tuning_module.strip_autofocus_algorithm({"algorithms": []}) is None


def test_af_less_copy_of_the_pisp_tuning_is_used(pi):
    target = tuning_module.disable_libcamera_autofocus(cache_dir=pi)

    assert target == pi / "imx708_wide_noir_noaf.json"
    assert tuning_module.os.environ["LIBCAMERA_RPI_TUNING_FILE"] == str(target)

    written = json.loads(target.read_text())

    assert written["target"] == "pisp"
    assert "rpi.af" not in [
        name for algorithm in written["algorithms"] for name in algorithm
    ]


def test_user_tuning_file_is_respected(pi, monkeypatch):
    monkeypatch.setenv("LIBCAMERA_RPI_TUNING_FILE", "/home/user/mine.json")

    assert tuning_module.disable_libcamera_autofocus(cache_dir=pi) is None
    assert (
        tuning_module.os.environ["LIBCAMERA_RPI_TUNING_FILE"] == "/home/user/mine.json"
    )
    assert not pi.exists()


def test_two_sensors_change_nothing(pi, monkeypatch, tmp_path):
    second = tmp_path / "sys" / "v4l-subdev4"
    second.mkdir()
    (second / "name").write_text("imx708_wide_noir 11-001a\n")

    assert tuning_module.disable_libcamera_autofocus(cache_dir=pi) is None
    assert "LIBCAMERA_RPI_TUNING_FILE" not in tuning_module.os.environ


def test_lens_map_pairs_dioptres_with_positions():
    assert tuning_module.lens_map_from_tuning(TUNING) == ((0.0, 420), (35.0, 920))


def test_lens_map_is_sorted_by_dioptres():
    tuning = {"algorithms": [{"rpi.af": {"map": [35.0, 920.0, 0.0, 420.0]}}]}

    assert tuning_module.lens_map_from_tuning(tuning) == ((0.0, 420), (35.0, 920))


def test_no_lens_map_without_rpi_af():
    assert tuning_module.lens_map_from_tuning({"algorithms": []}) == ()


def test_focus_span_is_near_then_far():
    lens_map = ((0.0, 420), (35.0, 920))

    assert tuning_module.lens_focus_span(lens_map) == (920, 420)
    assert tuning_module.lens_focus_span(((0.0, 420),)) is None


def test_lens_dioptres_interpolate_and_hold_at_the_ends():
    lens_map = ((0.0, 420), (35.0, 920))

    assert tuning_module.lens_dioptres(lens_map, 670) == pytest.approx(17.5)
    assert tuning_module.lens_dioptres(lens_map, 100) == 0.0
    assert tuning_module.lens_dioptres(lens_map, 1023) == 35.0


def test_lens_map_is_read_from_the_original_not_the_af_less_copy(pi):
    # Once auto focus is disabled, libcamera reads the copy, which has no map.
    copy = tuning_module.disable_libcamera_autofocus(cache_dir=pi)

    assert tuning_module.os.environ["LIBCAMERA_RPI_TUNING_FILE"] == str(copy)
    assert tuning_module.read_lens_map() == ((0.0, 420), (35.0, 920))


def test_no_lens_map_without_a_single_sensor(pi, tmp_path):
    second = tmp_path / "sys" / "v4l-subdev4"
    second.mkdir()
    (second / "name").write_text("imx708_wide_noir 11-001a\n")

    assert tuning_module.read_lens_map() == ()
