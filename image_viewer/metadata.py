# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Image metadata for the image viewer: the file's own facts (dimensions,
pixel format, size, modified time) and every text chunk a capture
carries, rendered as rich text for the sidebar's Metadata section and its
pop-out window.

Generic on purpose — the viewer shows whatever chunks a file holds and
knows no plugin's key. OpenCV drops text chunks when decoding, so they
are read separately through ``QImageReader``, which parses only the
header (no pixel decode) until ``read()``.
"""

# Standard library imports.
import html
import json
import re
from datetime import datetime
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtGui import QImage, QImageReader

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: What the Metadata section shows for an image without text chunks.
NO_METADATA_TEXT = "No metadata"

#: Paragraph margins (QTextDocument honours them on ``<p>``): a small gap
#: under each field, a larger one above each chunk's heading. Fields are
#: blocks, not table rows, because a rich-text table never wraps below
#: its widest row and would pin the sidebar's minimum width.
METADATA_FIELD_STYLE = "margin: 0 0 4px 0"
METADATA_HEADING_STYLE = "margin: 10px 0 4px 0"

#: A JSON chunk's top-level ``version`` is, by generic schema convention,
#: the version of its metadata schema — not of the app or firmware. It is
#: moved out of the field list into a small grey right-aligned "v1.0.0"
#: footnote closing its fields. The neutral grey reads on both light and
#: dark themes.
METADATA_VERSION_KEY = "version"
METADATA_VERSION_STYLE = "margin: 10px 0 0 0; color: #888888; font-size: small"

#: A JSON chunk's top-level ``field_descriptions`` is, by the same
#: convention, an object of field key -> one-line description that the
#: writer ships with its data, so the viewer can explain fields it knows
#: nothing about. It is never shown as a field; each description becomes
#: its field's tooltip, and a field without one gets its stored key.
METADATA_DESCRIPTIONS_KEY = "field_descriptions"

#: Heading of the section of facts read from the file itself, shown
#: before the embedded metadata.
FILE_INFO_HEADING = "File Details"

#: Tooltips of the File Details labels (``read_file_info``'s keys).
FILE_INFO_DESCRIPTIONS = {
    "Dimensions": "Width × height of the image, in pixels.",
    "Pixel Format": "Bits per pixel and colour layout of the stored image.",
    "File Size": "Size of the image file on disk.",
    "Modified": "When the file was last modified (local time).",
}

#: Heading of a run of plain-text chunks (a JSON chunk is headed by its
#: own key instead).
TEXT_CHUNKS_HEADING = "Text"

#: What follows the file section for an image without text chunks.
NO_EMBEDDED_METADATA_TEXT = "No embedded metadata"

#: A lower-case letter followed by an upper-case one: the word boundary
#: inside a CamelCase name.
CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")

#: Words of a field name shown upper-case: generic technical acronyms
#: only — never a plugin's key, which the viewer must not know.
FIELD_NAME_ACRONYMS = frozenset(
    {"id", "uid", "uuid", "utc", "led", "rgb", "rgba", "png", "json", "url", "usb"}
)

#: Pixel formats ``QImageReader`` reports, as the total bits per pixel
#: and colour model (Windows' "Bit depth" convention). PNG's 8-bit RGB
#: reads as ``Format_RGB32`` and its palette images as
#: ``Format_Grayscale8`` or ``Format_Indexed8``. Any other format shows
#: its Qt name.
PIXEL_FORMAT_TEXTS = {
    QImage.Format.Format_Mono: "1-bit monochrome",
    QImage.Format.Format_Grayscale8: "8-bit grayscale",
    QImage.Format.Format_Grayscale16: "16-bit grayscale",
    QImage.Format.Format_Indexed8: "8-bit indexed",
    QImage.Format.Format_RGB32: "24-bit RGB",
    QImage.Format.Format_RGB888: "24-bit RGB",
    QImage.Format.Format_ARGB32: "32-bit RGBA",
    QImage.Format.Format_RGBX64: "48-bit RGB",
    QImage.Format.Format_RGBA64: "64-bit RGBA",
}

#: File size units, Windows-style: 1024-based steps labelled KB/MB/GB.
FILE_SIZE_UNITS = ("KB", "MB", "GB", "TB")
FILE_SIZE_STEP = 1024

#: Local-time format of the file's modified time.
MODIFIED_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def read_png_text(path) -> dict[str, str]:
    """Every text chunk of the image at ``path``, in file order: ``{}`` for
    a file without any (most non-PNG formats) or a missing/unreadable
    file."""
    if not Path(path).is_file():
        return {}

    reader = QImageReader(str(path))

    if not reader.canRead():
        logger.warning(
            f"Cannot read image metadata from {path}: {reader.errorString()}"
        )
        return {}

    return {key: reader.text(key) for key in reader.textKeys()}


def read_file_info(path) -> dict[str, str]:
    """The facts of the image at ``path`` read from the file itself, as
    display label to display text in order: dimensions and pixel format
    from the header (no pixel decode), size and local modified time from
    the file system. ``{}`` for a missing or unreadable file; a fact the
    format does not report is left out."""
    path = Path(path)

    if not path.is_file():
        return {}

    reader = QImageReader(str(path))

    if not reader.canRead():
        logger.warning(f"Cannot read image info from {path}: {reader.errorString()}")
        return {}

    info = {}
    size = reader.size()

    if size.isValid():
        info["Dimensions"] = f"{size.width()} × {size.height()} px"

    pixel_format = reader.imageFormat()

    if pixel_format != QImage.Format.Format_Invalid:
        info["Pixel Format"] = PIXEL_FORMAT_TEXTS.get(
            pixel_format, pixel_format.name.removeprefix("Format_")
        )

    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime)

    info["File Size"] = _file_size_text(stat.st_size)
    info["Modified"] = modified.strftime(MODIFIED_TIME_FORMAT)

    return info


def format_metadata_html(file_info: dict[str, str], texts: dict[str, str]) -> str:
    """The Metadata section's rich text: a "File Details" section of
    ``file_info`` first, each label's tooltip from
    :data:`FILE_INFO_DESCRIPTIONS`, then the embedded ``texts`` as
    :func:`format_png_html` renders them, or a short note when there are
    none. Without file info this is :func:`format_png_html` alone."""
    if not file_info:
        return format_png_html(texts)

    paragraphs = [_heading_paragraph(FILE_INFO_HEADING)]

    for label, text in file_info.items():
        description = FILE_INFO_DESCRIPTIONS.get(label, label)
        paragraphs.append(_metadata_paragraph(label, text, description))

    if texts:
        paragraphs.append(format_png_html(texts))
    else:
        paragraphs.append(
            f'<p style="{METADATA_HEADING_STYLE}">{NO_EMBEDDED_METADATA_TEXT}</p>'
        )

    return "".join(paragraphs)


def format_png_html(texts: dict[str, str]) -> str:
    """The embedded metadata's rich text for ``texts``: one paragraph per
    field, its bold name then its value. A JSON-object chunk gets a bold,
    underlined heading of its key, then one paragraph per field in file
    order (strings bare, anything else — nested objects included — as
    compact one-line JSON); a run of other chunks gets one "Text" heading,
    then a paragraph per chunk of its key and verbatim text. A JSON
    chunk's top-level ``version`` closes its fields as a right-aligned
    ``v<version>`` footnote instead of a field, and its top-level
    ``field_descriptions`` object (field key -> description) is not shown
    but gives each field its tooltip. Names show presentably (see
    :func:`presentable_name`); a field without a description, and every
    plain-text chunk, has its stored key as tooltip. Headings have none.
    Every key and value is HTML-escaped."""
    if not texts:
        return NO_METADATA_TEXT

    paragraphs = []
    in_text_run = False

    for key, value in texts.items():
        try:
            fields = json.loads(value)
        except ValueError:
            # Plain text: shown verbatim below.
            fields = None

        if not isinstance(fields, dict):
            if not in_text_run:
                paragraphs.append(_heading_paragraph(TEXT_CHUNKS_HEADING))
                in_text_run = True

            paragraphs.append(_metadata_paragraph(key, value, key))
            continue

        in_text_run = False
        paragraphs.append(_heading_paragraph(key))

        version = fields.pop(METADATA_VERSION_KEY, None)
        descriptions = fields.pop(METADATA_DESCRIPTIONS_KEY, {})

        # Written by whatever made the file: a malformed value must not
        # break the panel, so it just leaves the fields undescribed.
        if not isinstance(descriptions, dict):
            descriptions = {}

        for field, field_value in fields.items():
            description = _field_text(descriptions.get(field, field))
            paragraphs.append(
                _metadata_paragraph(field, _field_text(field_value), description)
            )

        if version is not None:
            paragraphs.append(
                f'<p align="right" style="{METADATA_VERSION_STYLE}">'
                f"v{html.escape(_field_text(version))}</p>"
            )

    return "".join(paragraphs)


def presentable_name(key):
    """``key`` as a display name: underscores and CamelCase boundaries
    become spaces and each word gets a capital first letter, the rest kept
    as stored — ``camera_lead_time`` reads "Camera Lead Time" and
    ``CaptureDetails`` "Capture Details". Words in
    :data:`FIELD_NAME_ACRONYMS` show upper-case (``timestamp_utc`` reads
    "Timestamp UTC"). A key with no words keeps its stored form."""
    words = []

    for word in CAMEL_CASE_BOUNDARY.sub(" ", key.replace("_", " ")).split():
        if word.lower() in FIELD_NAME_ACRONYMS:
            words.append(word.upper())
        else:
            words.append(word[:1].upper() + word[1:])

    return " ".join(words) or key


def _file_size_text(size):
    """``size`` bytes, human-readable in 1024-based units to one decimal
    (``4.1 MB``); under a kilobyte, whole bytes."""
    if size < FILE_SIZE_STEP:
        return f"{size} bytes"

    for unit in FILE_SIZE_UNITS:
        size /= FILE_SIZE_STEP

        if size < FILE_SIZE_STEP or unit == FILE_SIZE_UNITS[-1]:
            return f"{size:.1f} {unit}"


def _field_text(value):
    """``value`` as shown: a string bare, anything else as compact one-line
    JSON."""
    if isinstance(value, str):
        return value

    return json.dumps(value, ensure_ascii=False)


def _heading_paragraph(name):
    """A section's heading paragraph: ``name`` bold, underlined and
    presentable, without a tooltip — it would only repeat the heading."""
    name_html = html.escape(presentable_name(name))

    return f'<p style="{METADATA_HEADING_STYLE}"><b><u>{name_html}</u></b></p>'


def _metadata_paragraph(name, value, description):
    """One field's paragraph: the bold, presentable ``name`` with
    ``description`` as its tooltip (Qt's rich text maps ``title`` to the
    fragment's tooltip), then the escaped ``value`` (its line breaks
    kept)."""
    name_html = (
        f'<span title="{html.escape(description)}">'
        f"{html.escape(presentable_name(name))}</span>"
    )
    value_html = html.escape(value).replace("\n", "<br>")

    return f'<p style="{METADATA_FIELD_STYLE}"><b>{name_html}</b>: {value_html}</p>'
