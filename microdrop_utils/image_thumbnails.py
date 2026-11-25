# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Small cover-cropped pictures of local image files, decoded off the GUI
thread.

A picture is decoded on a worker, a few at a time, by a QImageReader scaled
close to the box it is shown in (a multi-megapixel photo is never decoded
whole), then centre-cropped to the box; only the QPixmap is made on the GUI
thread, at the screen's device pixel ratio. A picture is never scaled up.
Results are kept by (path, modification time, file size, box), the most
recent few, so a picture shown again or a rebuilt view does not decode it
again, while a file rewritten in place is. A file that is missing or not a
readable image gives None.
"""

# Standard library imports.
import math
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# Enthought library imports.
from pyface.api import GUI
from pyface.qt import QtCore, QtGui

#: Pictures decoded at once; the rest wait their turn.
MAX_DECODING = 2

#: Pictures kept, the least recently used dropped first.
CACHE_SIZE = 64


def cover_scaled_size(source, box):
    """The ``(width, height)`` to decode a ``source`` sized picture at so it
    covers ``box`` (width, height) with its aspect kept; never larger than
    the source."""
    source_width, source_height = (max(side, 1) for side in source)
    box_width, box_height = box
    scale = min(max(box_width / source_width, box_height / source_height), 1.0)

    # A hair under the exact product, so a float error does not add a pixel.
    return (
        max(math.ceil(source_width * scale - 1e-6), 1),
        max(math.ceil(source_height * scale - 1e-6), 1),
    )


def centre_crop(size, box):
    """``(x, y, width, height)`` of the ``box`` sized middle of a ``size``
    picture; the whole of a side shorter than the box."""
    width, height = size
    crop_width, crop_height = min(width, box[0]), min(height, box[1])

    return (
        (width - crop_width) // 2,
        (height - crop_height) // 2,
        crop_width,
        crop_height,
    )


def thumbnail_key(path, box):
    """What the picture of ``path`` in ``box`` is kept by: the path, its
    modification time and size, and the box; None when it is missing."""

    try:
        stat = os.stat(path)

    except OSError:
        return None

    return os.fspath(path), stat.st_mtime_ns, stat.st_size, tuple(box)


def decode_thumbnail(path, box):
    """On a worker thread: ``path`` decoded close to ``box`` (device pixels)
    and centre-cropped to it, as a QImage; null if it is no readable image.
    A QImage, never a QPixmap: only the GUI thread may make those."""
    reader = QtGui.QImageReader(os.fspath(path))
    size = reader.size()

    if size.isValid() and not size.isEmpty():
        scaled = cover_scaled_size((size.width(), size.height()), box)
        reader.setScaledSize(QtCore.QSize(*scaled))

    picture = reader.read()

    if picture.isNull():
        return picture

    return picture.copy(*centre_crop((picture.width(), picture.height()), box))


class ThumbnailLoader:
    """Hands each requested picture to its callbacks as a QPixmap, or None."""

    def __init__(self, workers=MAX_DECODING, cache_size=CACHE_SIZE):
        self._pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="thumbnail"
        )
        self._cache_size = cache_size
        self._cache = OrderedDict()
        self._waiting = {}

    def request(self, path, box, ratio, callback):
        """Call ``callback(pixmap or None)`` with the picture at ``path``
        cover-cropped to ``box`` (width, height in px) at device pixel
        ``ratio``: at once when it is kept or missing, else on the GUI thread
        once decoded."""
        device_box = (round(box[0] * ratio), round(box[1] * ratio))
        key = thumbnail_key(path, device_box)

        if key is None:
            callback(None)

            return

        if key in self._cache:
            self._cache.move_to_end(key)
            callback(self._cache[key])

            return

        if key in self._waiting:
            self._waiting[key].append(callback)

            return

        self._waiting[key] = [callback]
        future = self._pool.submit(decode_thumbnail, path, device_box)
        future.add_done_callback(partial(self._deliver_later, key, ratio))

    def _deliver_later(self, key, ratio, future):
        GUI.invoke_later(self._decoded, key, ratio, future.result())

    def _decoded(self, key, ratio, picture):
        """On the GUI thread: the QPixmap of the decoded ``picture``, kept
        and handed to the callbacks waiting for it."""
        pixmap = None

        if not picture.isNull():
            pixmap = QtGui.QPixmap.fromImage(picture)
            pixmap.setDevicePixelRatio(ratio)

        self._cache[key] = pixmap

        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

        for callback in self._waiting.pop(key, []):
            callback(pixmap)


#: The session's loader, made on first use.
_loader = None


def thumbnail_loader():
    """The session's ThumbnailLoader, shared so a picture decodes once."""
    global _loader

    if _loader is None:
        _loader = ThumbnailLoader()

    return _loader
