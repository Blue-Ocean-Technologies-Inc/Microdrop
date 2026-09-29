# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Generate a demo experiment for the image viewer's perspective correction.

A chip of 3 x 4 equal round droplets, each brightening at its own rate,
photographed by a tilted camera: the captures show the chip as a keystoned
quad whose droplets are unequal ellipses on a skewed grid. Define the
correction on the chip's four corner markers (drag them to a rectangle),
apply it, and the droplets become equal circles on a straight grid — one
ROI size fits them all, and the rates read out cleanly.

Layout written (the capture chain's): two capture sessions under
``<root>/<name>/captures/``, each with 16-bit raws in ``16bit_raw/`` and
8-bit display copies beside them, so the Image Group dropdown offers
All / None / 16bit_raw.

    pixi run python -m image_viewer.demos.generate_perspective_demo
"""

# Standard library imports.
import argparse
import calendar
import os
import time
from pathlib import Path

# Third-party imports.
import cv2
import numpy as np

#: Capture frame size (width, height) and the chip's rectangle inside the
#: rectified (undistorted) scene.
FRAME_SIZE = (1280, 960)
CHIP_RECT = (190, 180, 1090, 780)

#: Where the chip's corners land in the capture (clockwise from top-left):
#: a camera tilted back and to the side, so the far edge is narrower.
CAMERA_QUAD = [(330, 170), (1010, 230), (1150, 820), (140, 760)]

#: Droplet grid (rows, columns) and the droplet radius, in rectified px.
GRID = (3, 4)
DROPLET_RADIUS = 58

#: 16-bit levels: dark background, chip body, and the brightest droplet.
BACKGROUND_LEVEL = 600
CHIP_LEVEL = 1400
MAX_SIGNAL = 24000
NOISE_SIGMA = 120

#: Frames per session and seconds between frames.
FRAMES_PER_SESSION = 12
FRAME_INTERVAL_S = 30

CAPTURE_TIMESTAMP_FORMAT = "%Y_%m_%d-%H_%M_%S"
RAW_SUBDIR = "16bit_raw"


def droplet_centres():
    """Rectified centres of the droplet grid, row by row."""
    left, top, right, bottom = CHIP_RECT
    rows, columns = GRID
    x_step = (right - left) / columns
    y_step = (bottom - top) / rows

    return [
        (left + (column + 0.5) * x_step, top + (row + 0.5) * y_step)
        for row in range(rows)
        for column in range(columns)
    ]


def droplet_rates(count, rng):
    """Per-droplet brightening time constants (s): some fast, some slow,
    one blank control that never lights."""
    rates = rng.uniform(60, 600, count)
    rates[-1] = np.inf

    return rates


def rectified_frame(elapsed_s, rates, rng):
    """The scene as a camera square-on to the chip would see it."""
    width, height = FRAME_SIZE
    frame = np.full((height, width), BACKGROUND_LEVEL, dtype=np.float64)

    left, top, right, bottom = CHIP_RECT
    frame[top:bottom, left:right] = CHIP_LEVEL

    # Bright corner markers: what the user clicks to define the correction.
    for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)):
        cv2.circle(frame, (int(x), int(y)), 14, MAX_SIGNAL * 0.6, -1)

    cv2.rectangle(frame, (left, top), (right, bottom), MAX_SIGNAL * 0.3, 4)

    for (x, y), rate in zip(droplet_centres(), rates):
        level = 0.0 if np.isinf(rate) else 1.0 - np.exp(-elapsed_s / rate)
        cv2.circle(
            frame,
            (int(x), int(y)),
            DROPLET_RADIUS,
            CHIP_LEVEL + level * (MAX_SIGNAL - CHIP_LEVEL),
            -1,
            lineType=cv2.LINE_AA,
        )

    # Uneven illumination, brighter at the lower left.
    ys, xs = np.mgrid[0:height, 0:width]
    frame *= 0.8 + 0.3 * (1 - xs / width) * (ys / height)

    return frame + rng.normal(0, NOISE_SIGMA, frame.shape)


def camera_view(frame):
    """``frame`` as the tilted camera sees it."""
    left, top, right, bottom = CHIP_RECT
    chip = np.float32([(left, top), (right, top), (right, bottom), (left, bottom)])
    matrix = cv2.getPerspectiveTransform(chip, np.float32(CAMERA_QUAD))

    return cv2.warpPerspective(
        frame,
        matrix,
        FRAME_SIZE,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=BACKGROUND_LEVEL,
    )


def write_session(captures, session_name, start_epoch, start_elapsed, rates, rng):
    """One capture session: raws under ``16bit_raw/``, 8-bit display copies
    beside them, stamped and dated like the capture chain's files."""
    session_stamp = time.strftime(CAPTURE_TIMESTAMP_FORMAT, time.gmtime(start_epoch))
    folder = captures / f"{session_name}_{session_stamp}"
    (folder / RAW_SUBDIR).mkdir(parents=True, exist_ok=True)

    for index in range(FRAMES_PER_SESSION):
        epoch = start_epoch + index * FRAME_INTERVAL_S
        elapsed = start_elapsed + index * FRAME_INTERVAL_S
        stamp = time.strftime(CAPTURE_TIMESTAMP_FORMAT, time.gmtime(epoch))
        label = f"Green_540_nm_{index + 1}_{stamp}"

        raw = np.clip(camera_view(rectified_frame(elapsed, rates, rng)), 0, 65535)
        raw = raw.astype(np.uint16)
        display = cv2.normalize(raw, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        raw_path = folder / RAW_SUBDIR / f"{label}_raw.png"
        display_path = folder / f"{label}.png"
        cv2.imwrite(str(raw_path), raw)
        cv2.imwrite(str(display_path), display)

        for path in (raw_path, display_path):
            os.utime(path, (epoch, epoch))

    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "Documents" / "Sci-Bots" / "Microdrop" / "Experiments",
        help="Experiments folder to write into",
    )
    parser.add_argument("--name", default="perspective_demo")
    args = parser.parse_args()

    rng = np.random.default_rng(7)
    rates = droplet_rates(GRID[0] * GRID[1], rng)
    captures = args.root / args.name / "captures"
    start = calendar.timegm(
        time.strptime("2026_09_29-15_00_00", CAPTURE_TIMESTAMP_FORMAT)
    )
    second_start = start + FRAMES_PER_SESSION * FRAME_INTERVAL_S + 300

    first = write_session(captures, "Incubate_1", start, 0, rates, rng)
    second = write_session(
        captures,
        "Incubate_2",
        second_start,
        second_start - start,
        rates,
        rng,
    )

    print(f"Wrote {FRAMES_PER_SESSION} frames each to:\n  {first}\n  {second}")
    print(f"Chip corner markers in the captures: {CAMERA_QUAD}")


if __name__ == "__main__":
    main()
