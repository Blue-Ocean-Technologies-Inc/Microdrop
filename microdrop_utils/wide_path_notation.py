# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A text notation for slug phases on the lattice.

**Frames** — one character per lattice cell over a fixed window, only
actuations::

    .   off
    #   on
    _   no electrode there (a hole or off the device)

**Titles** — ``<head step> <heading>``, e.g. ``3 u``: the head is at route
step 3 and the slug is heading up; ``3.1 u`` is an extra phase on the corner
electrode that already faces the way the route leaves. Headings are the
letters r/l/u/d as seen on screen (u is decreasing SVG y).

**Shorthand** — ``WxT <heading>``, e.g. ``3x2 r``: width across the heading,
trail along it, so the picture follows from the letter and the numbers never
change at a corner.

``render_phases`` draws a ``[(label, ids)]`` phase list over one shared
window so consecutive frames line up; ``parse`` reads a frame back into
lattice cells so tests can assert pictures; ``frame_text`` lays frames side
by side for printing.
"""

OFF, ON, HOLE = ".", "#", "_"

#: Heading vector -> letter, as seen on screen (u is decreasing SVG y).
HEADINGS = {(1, 0): "r", (-1, 0): "l", (0, -1): "u", (0, 1): "d"}
HEADING_VECTORS = {letter: vector for vector, letter in HEADINGS.items()}


def lattice_cells(centroids, pitch):
    """``id -> (column, row)`` lattice coordinates, rounded from centroids.

    Real devices are not perfect grids (reservoir electrodes are large and
    off-pitch); rounding to the nearest pitch places every electrode on a
    cell for drawing, which is all a frame needs.
    """
    x0 = min(x for x, _y in centroids.values())
    y0 = min(y for _x, y in centroids.values())
    return {
        electrode_id: (round((x - x0) / pitch), round((y - y0) / pitch))
        for electrode_id, (x, y) in centroids.items()
    }


def heading_letter(heading):
    """r/l/u/d for a unit heading, ``?`` off-axis."""
    key = (round(heading[0]), round(heading[1]))
    return HEADINGS.get(key, "?")


def render_frame(on, cells, window):
    """One frame: the cells in ``window`` = (min_col, min_row, max_col,
    max_row), ``#`` where an electrode in ``on`` sits, ``_`` where no
    electrode sits at all."""
    by_cell = {cell: electrode_id for electrode_id, cell in cells.items()}
    on = set(on)
    lines = []
    for row in range(window[1], window[3] + 1):
        chars = []
        for col in range(window[0], window[2] + 1):
            electrode_id = by_cell.get((col, row))
            if electrode_id is None:
                chars.append(HOLE)
            elif electrode_id in on:
                chars.append(ON)
            else:
                chars.append(OFF)
        lines.append(" ".join(chars))
    return "\n".join(lines)


def window_around(ids, cells, margin=1):
    """The bounding window of ``ids`` plus ``margin`` cells on every side."""
    cols = [cells[i][0] for i in ids]
    rows = [cells[i][1] for i in ids]
    return (
        min(cols) - margin,
        min(rows) - margin,
        max(cols) + margin,
        max(rows) + margin,
    )


def render_phases(phases, route, centroids, pitch, margin=1):
    """``[(title, frame)]`` for a list of :data:`Phase` records.

    All frames share one window — everything any phase lights up, plus the
    route, plus ``margin`` — so they line up side by side. The title is the
    phase's number, counted from 1, and the direction of travel it carries.
    """
    cells = lattice_cells(centroids, pitch)
    every_id = {i for phase in phases for i in phase.ids} | set(route)

    if not every_id:
        return []

    window = window_around(every_id, cells, margin)

    return [
        (
            f"{number} {heading_letter(phase.heading)}",
            render_frame(phase.ids, cells, window),
        )
        for number, phase in enumerate(phases, 1)
    ]


def parse(frame, window):
    """The cells (column, row) marked on in ``frame``, reading it over
    ``window`` the way ``render_frame`` wrote it."""
    on = set()
    for row_offset, line in enumerate(frame.strip("\n").splitlines()):
        for col_offset, char in enumerate(line.split()):
            if char == ON:
                on.add((window[0] + col_offset, window[1] + row_offset))
    return on


def shorthand(left, right, trail_length, heading, block_heading=None):
    """``WxT heading`` for a slug's parameters.

    Width is across the heading and trail along it. With a rotation-locked
    block the block keeps ``block_heading`` while the route turns, so once
    the two are perpendicular the numbers swap: ``3x2 r`` becomes ``2x3 u``.
    """
    width, trail = left + right + 1, trail_length

    if block_heading is not None:
        dot = heading[0] * block_heading[0] + heading[1] * block_heading[1]

        if abs(dot) < 0.5:
            width, trail = trail, width

    return f"{width}x{trail} {heading_letter(heading)}"


def frame_text(frames):
    """Frames side by side, titles above, for printing."""
    if not frames:
        return ""
    blocks = [[title] + frame.splitlines() for title, frame in frames]
    height = max(len(block) for block in blocks)
    width = max(len(line) for block in blocks for line in block)
    lines = []
    for index in range(height):
        lines.append(
            "   ".join(
                (block[index] if index < len(block) else "").ljust(width)
                for block in blocks
            ).rstrip()
        )
    return "\n".join(lines)
