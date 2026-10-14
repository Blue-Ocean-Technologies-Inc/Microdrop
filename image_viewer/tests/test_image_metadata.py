# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for reading and formatting a capture's PNG text-chunk metadata."""

# Standard library imports.
import json

# Enthought library imports.
from pyface.qt.QtGui import QImage

# Microdrop package imports.
from image_viewer.metadata import NO_METADATA_TEXT, format_png_text, read_png_text

CAPTURE_SETTINGS = {
    "exposure_us": 50000,
    "gain": 12.5,
    "filter": "FAM",
    "led_intensities": {"blue": 40, "green": 0},
}


def _write_png(path, texts):
    image = QImage(8, 6, QImage.Format_Grayscale16)
    image.fill(1234)

    for key, value in texts.items():
        image.setText(key, value)

    assert image.save(str(path))

    return path


def test_read_png_text_returns_every_chunk(tmp_path):
    texts = {"MicrodropCapture": json.dumps(CAPTURE_SETTINGS), "Note": "spot 3"}
    path = _write_png(tmp_path / "capture.png", texts)

    assert read_png_text(path) == texts


def test_png_without_chunks_has_no_metadata(tmp_path):
    path = _write_png(tmp_path / "plain.png", {})

    assert read_png_text(path) == {}
    assert format_png_text(read_png_text(path)) == NO_METADATA_TEXT


def test_missing_file_reads_empty():
    assert read_png_text("does/not/exist.png") == {}


def test_lone_json_chunk_renders_fields_in_order_without_heading():
    text = format_png_text({"MicrodropCapture": json.dumps(CAPTURE_SETTINGS)})

    assert text.splitlines() == [
        "exposure_us: 50000",
        "gain: 12.5",
        "filter: FAM",
        'led_intensities: {"blue": 40, "green": 0}',
    ]


def test_several_chunks_get_headings_and_plain_text_shows_verbatim():
    texts = {"MicrodropCapture": json.dumps({"gain": 2}), "Note": "spot 3"}

    assert format_png_text(texts).splitlines() == [
        "[MicrodropCapture]",
        "gain: 2",
        "Note: spot 3",
    ]
