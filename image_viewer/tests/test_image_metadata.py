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
from image_viewer.metadata import NO_METADATA_TEXT, format_png_html, read_png_text

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
    assert format_png_html(read_png_text(path)) == NO_METADATA_TEXT


def test_missing_file_reads_empty():
    assert read_png_text("does/not/exist.png") == {}


def test_lone_json_chunk_renders_bold_fields_in_order_without_heading():
    html_text = format_png_html({"MicrodropCapture": json.dumps(CAPTURE_SETTINGS)})
    names = [f"<b>{name}</b>" for name in CAPTURE_SETTINGS]

    assert html_text.startswith("<table")
    assert "MicrodropCapture" not in html_text
    assert [html_text.index(name) for name in names] == sorted(
        html_text.index(name) for name in names
    )
    assert "12.5" in html_text
    assert "{&quot;blue&quot;: 40, &quot;green&quot;: 0}" in html_text


def test_several_chunks_get_headings_and_plain_text_rows():
    texts = {"MicrodropCapture": json.dumps({"gain": 2}), "Note": "spot 3"}
    html_text = format_png_html(texts)

    assert ">MicrodropCapture</th>" in html_text
    assert "<b>gain</b>" in html_text
    assert "<b>Note</b>" in html_text
    assert "spot 3" in html_text


def test_keys_and_values_are_html_escaped():
    texts = {"MicrodropCapture": json.dumps({"<field>": "a < b & c"})}
    html_text = format_png_html(texts)

    assert "<b>&lt;field&gt;</b>" in html_text
    assert "a &lt; b &amp; c" in html_text
    assert "<field>" not in html_text
