# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PNG text-chunk metadata for the image viewer: read every text chunk a
capture carries and render it as rich text for the sidebar's Metadata
section and its pop-out window.

Generic on purpose — the viewer shows whatever chunks a file holds and
knows no plugin's key. OpenCV drops text chunks when decoding, so they
are read separately through ``QImageReader``, which parses only the
header (no pixel decode) until ``read()``.
"""

# Standard library imports.
import html
import json
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtGui import QImageReader

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


def format_png_html(texts: dict[str, str]) -> str:
    """The Metadata section's rich text for ``texts``: one paragraph per
    field, its bold name then its value. A JSON-object chunk gives one
    paragraph per field in file order (strings bare, anything else —
    nested objects included — as compact one-line JSON); any other chunk
    is one paragraph of its key and verbatim text. With several chunks
    each JSON one gets a bold heading paragraph; a lone chunk needs none.
    Every key and value is HTML-escaped."""
    if not texts:
        return NO_METADATA_TEXT

    paragraphs = []

    for key, value in texts.items():
        try:
            fields = json.loads(value)
        except ValueError:
            # Plain text: shown verbatim below.
            fields = None

        if not isinstance(fields, dict):
            paragraphs.append(_metadata_paragraph(key, value))
            continue

        if len(texts) > 1:
            paragraphs.append(
                f'<p style="{METADATA_HEADING_STYLE}"><b>{html.escape(key)}</b></p>'
            )

        for field, field_value in fields.items():
            if not isinstance(field_value, str):
                field_value = json.dumps(field_value, ensure_ascii=False)

            paragraphs.append(_metadata_paragraph(field, field_value))

    return "".join(paragraphs)


def _metadata_paragraph(name, value):
    """One field's paragraph: the bold, escaped ``name``, then the escaped
    ``value`` (its line breaks kept)."""
    value_html = html.escape(value).replace("\n", "<br>")

    return (
        f'<p style="{METADATA_FIELD_STYLE}">'
        f"<b>{html.escape(name)}</b>: {value_html}</p>"
    )
