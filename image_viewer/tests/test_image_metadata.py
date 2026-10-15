# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for reading and formatting an image's file facts and a capture's
PNG text-chunk metadata."""

# Standard library imports.
import html
import json
import os
from datetime import datetime

# Enthought library imports.
from pyface.qt.QtGui import QImage

# Microdrop package imports.
from image_viewer.metadata import (
    FILE_INFO_DESCRIPTIONS,
    FILE_INFO_HEADING,
    NO_EMBEDDED_METADATA_TEXT,
    NO_METADATA_TEXT,
    TEXT_CHUNKS_HEADING,
    format_metadata_html,
    format_png_html,
    presentable_name,
    read_file_info,
    read_png_text,
)

CAPTURE_SETTINGS = {
    "exposure_us": 50000,
    "gain": 12.5,
    "filter": "FAM",
    "led_intensities": {"blue": 40, "green": 0},
}


def _bold_name(shown, key):
    """A field name as rendered: bold, presentable, its key the tooltip."""
    return f'<b><span title="{key}">{shown}</span></b>'


def _heading(shown):
    """A section heading as rendered: bold, underlined, no tooltip."""
    return f"<b><u>{shown}</u></b>"


def _write_png(path, texts):
    image = QImage(8, 6, QImage.Format_Grayscale16)
    image.fill(1234)

    for key, value in texts.items():
        image.setText(key, value)

    assert image.save(str(path))

    return path


def test_read_png_text_returns_every_chunk(tmp_path):
    texts = {"CaptureDetails": json.dumps(CAPTURE_SETTINGS), "Note": "spot 3"}
    path = _write_png(tmp_path / "capture.png", texts)

    assert read_png_text(path) == texts


def test_png_without_chunks_has_no_metadata(tmp_path):
    path = _write_png(tmp_path / "plain.png", {})

    assert read_png_text(path) == {}
    assert format_png_html(read_png_text(path)) == NO_METADATA_TEXT


def test_missing_file_reads_empty():
    assert read_png_text("does/not/exist.png") == {}


def test_lone_json_chunk_renders_its_heading_then_bold_fields_in_order():
    html_text = format_png_html({"CaptureDetails": json.dumps(CAPTURE_SETTINGS)})
    names = [_bold_name(presentable_name(key), key) for key in CAPTURE_SETTINGS]

    assert "<table" not in html_text
    assert html_text.startswith("<p")
    assert html_text.index(_heading("Capture Details")) < html_text.index(names[0])
    assert [html_text.index(name) for name in names] == sorted(
        html_text.index(name) for name in names
    )
    assert "12.5" in html_text
    assert "{&quot;blue&quot;: 40, &quot;green&quot;: 0}" in html_text


def test_several_chunks_get_underlined_headings_and_plain_text_paragraphs():
    texts = {"MicrodropCapture": json.dumps({"gain": 2}), "Note": "spot 3"}
    html_text = format_png_html(texts)

    heading = _heading("Microdrop Capture")
    gain = _bold_name("Gain", "gain")
    text_heading = _heading(TEXT_CHUNKS_HEADING)

    assert f"{heading}</p>" in html_text
    assert html_text.index(heading) < html_text.index(gain)
    assert html_text.index(gain) < html_text.index(text_heading)
    assert f"{_bold_name('Note', 'Note')}: spot 3" in html_text
    assert "<table" not in html_text


def test_consecutive_plain_text_chunks_share_one_heading():
    html_text = format_png_html({"Software": "Qt", "Note": "spot 3"})

    assert html_text.count(TEXT_CHUNKS_HEADING) == 1


def test_keys_and_values_are_html_escaped():
    texts = {"CaptureDetails": json.dumps({"<field>": "a < b & c"})}
    html_text = format_png_html(texts)

    assert _bold_name("&lt;field&gt;", "&lt;field&gt;") in html_text
    assert "a &lt; b &amp; c" in html_text
    assert "<field>" not in html_text


def test_version_moves_from_fields_to_right_aligned_v_footnote():
    texts = {"CaptureDetails": json.dumps({"version": "1.0.0", "label": "GFP"})}
    html_text = format_png_html(texts)

    assert 'title="version"' not in html_text
    assert '<p align="right"' in html_text
    assert html_text.endswith(">v1.0.0</p>")
    assert html_text.index(">Label<") < html_text.index(">v1.0.0<")


def test_non_string_version_renders_as_compact_json():
    texts = {"CaptureDetails": json.dumps({"version": [1, 2]})}

    assert format_png_html(texts).endswith(">v[1, 2]</p>")


def test_chunk_without_version_has_no_footnote():
    html_text = format_png_html({"CaptureDetails": json.dumps({"gain": 2})})

    assert 'align="right"' not in html_text


def test_non_json_chunk_keeps_its_version_text():
    html_text = format_png_html({"version": "1"})

    assert f"{_bold_name('Version', 'version')}: 1" in html_text
    assert 'align="right"' not in html_text


def test_snake_case_names_read_title_case_with_acronyms_upper():
    assert presentable_name("camera_lead_time") == "Camera Lead Time"
    assert presentable_name("timestamp_utc") == "Timestamp UTC"
    assert presentable_name("step_dotted_id") == "Step Dotted ID"
    assert presentable_name("led_index") == "LED Index"


def test_camel_case_names_split_into_capitalised_words():
    assert presentable_name("CaptureDetails") == "Capture Details"
    assert presentable_name("sensorTemperature") == "Sensor Temperature"
    assert presentable_name("imageID") == "Image ID"


def test_other_names_keep_their_letters_and_capitalise_each_word():
    assert presentable_name("Exposure") == "Exposure"
    assert presentable_name("Creation Time") == "Creation Time"
    assert presentable_name("raw_ADC_count") == "Raw ADC Count"
    assert presentable_name("__") == "__"


def test_field_name_tooltip_is_the_stored_key():
    html_text = format_png_html({"Capture": json.dumps({"camera_lead_time": 250})})

    assert f"{_bold_name('Camera Lead Time', 'camera_lead_time')}: 250" in html_text


def test_field_descriptions_become_tooltips_and_undescribed_fields_keep_their_key():
    fields = {
        "camera_lead_time": 250,
        "gain": 2,
        "field_descriptions": {"camera_lead_time": "Wait <before> the grab."},
    }
    html_text = format_png_html({"Capture": json.dumps(fields)})

    lead_time = _bold_name("Camera Lead Time", "Wait &lt;before&gt; the grab.")

    assert f"{lead_time}: 250" in html_text
    assert f"{_bold_name('Gain', 'gain')}: 2" in html_text


def test_field_descriptions_are_not_shown_as_a_field():
    fields = {"gain": 2, "field_descriptions": {"gain": "Camera gain."}}
    html_text = format_png_html({"Capture": json.dumps(fields)})

    assert "Field Descriptions" not in html_text
    assert 'title="field_descriptions"' not in html_text


def test_malformed_field_descriptions_leave_fields_undescribed():
    fields = {"gain": 2, "field_descriptions": "not an object"}
    html_text = format_png_html({"Capture": json.dumps(fields)})

    assert f"{_bold_name('Gain', 'gain')}: 2" in html_text
    assert "not an object" not in html_text


def test_headings_have_no_tooltip():
    texts = {"CaptureDetails": json.dumps({"gain": 2}), "Note": "spot 3"}
    html_text = format_metadata_html({"Dimensions": "8 × 6 px"}, texts)

    assert f'title="{FILE_INFO_HEADING}"' not in html_text
    assert 'title="CaptureDetails"' not in html_text
    assert f'title="{TEXT_CHUNKS_HEADING}"' not in html_text


def test_read_file_info_reports_header_and_file_system_facts(tmp_path):
    path = _write_png(tmp_path / "capture.png", {})
    os.utime(path, (0, datetime(2026, 10, 15, 14, 3, 27).timestamp()))

    assert read_file_info(path) == {
        "Dimensions": "8 × 6 px",
        "Pixel Format": "16-bit grayscale",
        "File Size": f"{path.stat().st_size} bytes",
        "Modified": "2026-10-15 14:03:27",
    }


def test_large_file_size_reads_in_1024_based_units(tmp_path):
    path = _write_png(tmp_path / "capture.png", {})

    with open(path, "ab") as file:
        file.truncate(int(4.1 * 1024 * 1024))

    assert read_file_info(path)["File Size"] == "4.1 MB"


def test_read_file_info_of_missing_or_unreadable_file_is_empty(tmp_path):
    not_an_image = tmp_path / "notes.png"
    not_an_image.write_text("not an image")

    assert read_file_info("does/not/exist.png") == {}
    assert read_file_info(not_an_image) == {}


def test_file_details_section_comes_first_then_the_embedded_chunks():
    file_info = {"Dimensions": "8 × 6 px"}
    texts = {"CaptureDetails": json.dumps({"gain": 2})}
    html_text = format_metadata_html(file_info, texts)

    file_heading = _heading(FILE_INFO_HEADING)

    assert html_text.index(file_heading) == html_text.index("<b>")
    assert html_text.index("8 × 6 px") < html_text.index("Capture Details")
    assert html_text.endswith(format_png_html(texts))


def test_file_details_labels_are_described_by_the_viewer(tmp_path):
    path = _write_png(tmp_path / "capture.png", {})
    file_info = read_file_info(path)
    html_text = format_metadata_html(file_info, {})

    assert set(file_info) == set(FILE_INFO_DESCRIPTIONS)

    for label, description in FILE_INFO_DESCRIPTIONS.items():
        assert _bold_name(label, html.escape(description)) in html_text


def test_file_without_chunks_notes_no_embedded_metadata():
    html_text = format_metadata_html({"Dimensions": "8 × 6 px"}, {})

    assert html_text.endswith(f"{NO_EMBEDDED_METADATA_TEXT}</p>")


def test_without_file_info_only_the_chunks_show():
    texts = {"Note": "spot 3"}

    assert format_metadata_html({}, texts) == format_png_html(texts)
    assert format_metadata_html({}, {}) == NO_METADATA_TEXT
