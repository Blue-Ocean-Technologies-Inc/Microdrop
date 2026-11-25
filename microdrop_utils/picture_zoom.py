# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A zoomable picture's zoom maths, Qt-free.

A zoom is device pixels per picture pixel: 1.0 shows the picture's actual
pixels, ``fit`` shows it whole in its window. The zoom never goes below fit
and never above MAX_ZOOM (or fit, if fit is larger)."""

#: Zoom factor per wheel notch or key press.
ZOOM_STEP = 1.25

#: The most magnification: this many device pixels per picture pixel.
MAX_ZOOM = 8.0

#: Above this zoom a picture is drawn nearest-neighbour, its pixels crisp
#: squares; at or below it, smoothly scaled.
CRISP_PIXELS_ABOVE = 2.0

#: Two zooms this close (relative) are the same zoom.
_TOLERANCE = 1e-3


def fit_zoom(picture_width, picture_height, view_width, view_height):
    """The zoom that shows the whole picture in the view, all in device
    pixels."""
    return min(
        view_width / max(picture_width, 1),
        view_height / max(picture_height, 1),
    )


def clamped_zoom(zoom, fit):
    """``zoom`` within fit and MAX_ZOOM."""
    return min(max(zoom, fit), max(MAX_ZOOM, fit))


def is_same_zoom(first, second):
    return abs(first - second) <= _TOLERANCE * max(first, second)


def stepped_zoom(zoom, steps, fit, step=ZOOM_STEP):
    """``zoom`` moved ``steps`` steps (negative out, fractional for a smooth
    wheel), landing on actual size or fit when it would pass over either."""
    target = zoom * step**steps

    for stop in (1.0, fit):
        if min(zoom, target) < stop < max(zoom, target):
            target = stop

    return clamped_zoom(target, fit)


def double_click_zoom(zoom, fit):
    """Fit when zoomed in; from fit, actual size, or twice fit when actual
    size is no bigger than fit."""

    if not is_same_zoom(zoom, fit):
        return fit

    if 1.0 > fit and not is_same_zoom(1.0, fit):
        return 1.0

    return clamped_zoom(2 * fit, fit)


def is_crisp(zoom):
    """Whether a picture at ``zoom`` is drawn nearest-neighbour."""
    return zoom > CRISP_PIXELS_ABOVE


def zoom_percent(zoom):
    """``zoom`` as the readout shows it, e.g. ``"150 %"``."""
    return f"{round(zoom * 100)} %"
