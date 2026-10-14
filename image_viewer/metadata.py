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

#: Breathing room between a name and its value, and above a chunk's
#: heading row (QTextDocument honours padding on table cells).
METADATA_KEY_STYLE = "padding-right: 12px"
METADATA_HEADING_STYLE = "padding-top: 8px"


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
    """The Metadata section's rich text for ``texts``: one two-column table,
    bold names beside their values. A JSON-object chunk gives one row per
    field in file order (strings bare, anything else — nested objects
    included — as compact one-line JSON); any other chunk is one row of
    its key and verbatim text. With several chunks each JSON one gets a
    heading row with its key; a lone chunk needs none. Every key and value
    is HTML-escaped."""
    if not texts:
        return NO_METADATA_TEXT

    rows = []

    for key, value in texts.items():
        try:
            fields = json.loads(value)
        except ValueError:
            # Plain text: shown verbatim below.
            fields = None

        if not isinstance(fields, dict):
            rows.append(_metadata_row(key, value))
            continue

        if len(texts) > 1:
            rows.append(
                f'<tr><th colspan="2" align="left" style="{METADATA_HEADING_STYLE}">'
                f"{html.escape(key)}</th></tr>"
            )

        for field, field_value in fields.items():
            if not isinstance(field_value, str):
                field_value = json.dumps(field_value, ensure_ascii=False)

            rows.append(_metadata_row(field, field_value))

    return f'<table cellspacing="0" cellpadding="2">{"".join(rows)}</table>'


def _metadata_row(name, value):
    """One table row: the bold, escaped ``name`` beside the escaped
    ``value`` (its line breaks kept)."""
    value_html = html.escape(value).replace("\n", "<br>")

    return (
        f'<tr><td valign="top" style="{METADATA_KEY_STYLE}">'
        f"<b>{html.escape(name)}</b></td>"
        f'<td valign="top">{value_html}</td></tr>'
    )
