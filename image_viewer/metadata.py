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
capture carries and render it for the sidebar's Metadata section.

Generic on purpose — the viewer shows whatever chunks a file holds and
knows no plugin's key. OpenCV drops text chunks when decoding, so they
are read separately through ``QImageReader``, which parses only the
header (no pixel decode) until ``read()``.
"""

# Standard library imports.
import json
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtGui import QImageReader

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: What the Metadata section shows for an image without text chunks.
NO_METADATA_TEXT = "No metadata"


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


def format_png_text(texts: dict[str, str]) -> str:
    """The Metadata section's text for ``texts``: a JSON-object chunk as one
    ``field: value`` line per field in file order (strings bare, anything
    else — nested objects included — as compact one-line JSON), any other
    chunk verbatim as ``key: value``. With several chunks each JSON one
    gets a ``[key]`` heading line; a lone chunk needs none."""
    if not texts:
        return NO_METADATA_TEXT

    lines = []

    for key, value in texts.items():
        try:
            fields = json.loads(value)
        except ValueError:
            # Plain text: shown verbatim below.
            fields = None

        if not isinstance(fields, dict):
            lines.append(f"{key}: {value}")
            continue

        if len(texts) > 1:
            lines.append(f"[{key}]")

        for field, field_value in fields.items():
            if not isinstance(field_value, str):
                field_value = json.dumps(field_value, ensure_ascii=False)

            lines.append(f"{field}: {field_value}")

    return "\n".join(lines)
