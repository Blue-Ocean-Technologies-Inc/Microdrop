# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hand the lens of a Raspberry Pi CSI camera to MicroDrop.

While libcamera streams, its Raspberry Pi IPA's auto-focus algorithm
(``rpi.af``) rewrites the lens position every frame, undoing any manual
focus written to the lens sub-device. Qt's GStreamer backend exposes no
libcamera focus control either, so nothing is lost by pointing libcamera at
a copy of the sensor's tuning file without ``rpi.af``.
"""

# Standard library imports.
import glob
import json
import os
from pathlib import Path

# Enthought library imports.
from traits.etsconfig.api import ETSConfig

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Read by libcamera's Raspberry Pi pipeline when it opens a camera.
LIBCAMERA_TUNING_FILE_ENV = "LIBCAMERA_RPI_TUNING_FILE"

#: libcamera's tuning files, one directory per Raspberry Pi ISP: ``pisp``
#: (Pi 5) and ``vc4`` (Pi 4 and older).
LIBCAMERA_TUNING_DIR = Path("/usr/share/libcamera/ipa/rpi")

#: sysfs names of the V4L2 sub-devices: the CSI sensor, its lens, and on a
#: Pi 5 the ISP front end.
V4L2_SUBDEVICE_NAME_GLOB = "/sys/class/video4linux/v4l-subdev*/name"

#: The Pi 5 ISP front end's sub-device name.
PISP_FRONT_END_NAME = "pisp-fe"

#: The IPA algorithm that drives the lens.
LIBCAMERA_AF_ALGORITHM = "rpi.af"

#: Where the AF-less tuning copies go, under ETSConfig.application_home.
LIBCAMERA_TUNING_CACHE_DIRNAME = ".libcamera_tuning"


def _v4l2_subdevice_names():
    """Each V4L2 sub-device's name without its bus address
    (``"dw9807 11-000c"`` is ``"dw9807"``)."""
    names = []

    for name_file in sorted(glob.glob(V4L2_SUBDEVICE_NAME_GLOB)):
        try:
            words = Path(name_file).read_text().split()
        except OSError as error:
            logger.debug(f"Cannot read {name_file}: {error}")
            continue

        if words:
            names.append(words[0])

    return names


def strip_autofocus_algorithm(tuning):
    """``tuning`` (a parsed libcamera tuning file) without its ``rpi.af``
    algorithm, or None when it has none. ``algorithms`` holds one
    single-key dict per algorithm."""
    algorithms = tuning.get("algorithms", [])
    kept = [
        algorithm for algorithm in algorithms if LIBCAMERA_AF_ALGORITHM not in algorithm
    ]

    if len(kept) == len(algorithms):
        return None

    return {**tuning, "algorithms": kept}


def disable_libcamera_autofocus(cache_dir=None):
    """Point libcamera at an AF-less copy of the CSI sensor's tuning file.

    Sets LIBCAMERA_TUNING_FILE_ENV, so it must run before any camera is
    opened (before QMediaDevices or QCamera is used). Does nothing when the
    variable is already set (a user override), when there is not exactly
    one CSI sensor (the variable applies to every libcamera camera), or
    when the sensor's tuning has no ``rpi.af``.

    Parameters
    ----------
    cache_dir
        Where the copy is written; defaults to
        LIBCAMERA_TUNING_CACHE_DIRNAME under ETSConfig.application_home.

    Returns
    -------
    The tuning file libcamera now uses, or None when nothing was changed.
    """

    if os.environ.get(LIBCAMERA_TUNING_FILE_ENV):
        logger.info(
            f"{LIBCAMERA_TUNING_FILE_ENV} is already set "
            f"({os.environ[LIBCAMERA_TUNING_FILE_ENV]}); libcamera auto focus "
            f"left as configured"
        )

        return None

    subdevice_names = _v4l2_subdevice_names()
    pipeline = "pisp" if PISP_FRONT_END_NAME in subdevice_names else "vc4"
    tuning_dir = LIBCAMERA_TUNING_DIR / pipeline
    sensors = [
        name for name in subdevice_names if (tuning_dir / f"{name}.json").is_file()
    ]

    if len(sensors) != 1:
        logger.info(
            f"Expected one CSI camera sensor with a {pipeline} tuning file, found "
            f"{sensors or 'none'}; libcamera auto focus left on"
        )

        return None

    sensor = sensors[0]
    source = tuning_dir / f"{sensor}.json"

    try:
        tuning = strip_autofocus_algorithm(json.loads(source.read_text()))
    except (OSError, ValueError, AttributeError) as error:
        logger.error(f"Cannot read libcamera tuning file {source}: {error}")

        return None

    if tuning is None:
        logger.info(f"{source} has no {LIBCAMERA_AF_ALGORITHM}; nothing to disable")

        return None

    if cache_dir is None:
        cache_dir = Path(ETSConfig.application_home) / LIBCAMERA_TUNING_CACHE_DIRNAME

    target = Path(cache_dir) / f"{sensor}_noaf.json"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(tuning, indent=4))
    except OSError as error:
        logger.error(f"Cannot write libcamera tuning file {target}: {error}")

        return None

    os.environ[LIBCAMERA_TUNING_FILE_ENV] = str(target)
    logger.info(
        f"libcamera auto focus disabled for {sensor}: "
        f"{LIBCAMERA_TUNING_FILE_ENV}={target}"
    )

    return target
