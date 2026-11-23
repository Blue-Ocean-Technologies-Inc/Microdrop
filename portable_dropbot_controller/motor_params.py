# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The per-motor mechanical param blob (``_mt_*_dp``) in the operator's
units, on top of the driver's own codec (``dropbot_portable.param_layout``),
as its Motor Params tab uses it:

- every firmware generation the board can serve (56 / 64 / 68 / 72 B)
  decodes, the missing tail shown as the firmware's defaults;
- bspd / rspd are shown and edited in REAL µm/s whatever the board stores
  (motor layout 2.0 stores real µm/s, older firmware numbers the axis runs
  at ``MOTOR_LEGACY_SPEED_FACTOR`` of);
- a write is read-modify-write of the whole blob, sent back at exactly the
  length the board served (layout-2.0 firmware refuses any other), and a
  speed the operator left unchanged goes back as the board's own number,
  with no rounding drift.

No Qt, no transport: unit-testable without hardware.
"""

# Third-party imports.
from dropbot_portable.param_layout import (
    MOTOR_FIELDS,
    MOTOR_SPEED_FIELDS,
    decode_motor_blob,
    encode_motor_blob,
    motor_blob_problem,
    speed_real_to_wire,
    speed_wire_to_real,
)


def served_motor_fields(blob):
    """The field names a blob of this length actually carries (the
    wire-order prefix of MOTOR_FIELDS)."""
    return [name for name, _ in MOTOR_FIELDS[: len(blob) // 4]]


def decode_motor_params(blob, speed_factor):
    """A served blob -> {field: value} for every field, speeds in real µm/s.

    ``speed_factor`` is the board's real µm/s per stored number. Raises
    ValueError for a length no firmware has ever served.
    """
    fields = decode_motor_blob(blob)

    for name in MOTOR_SPEED_FIELDS:
        fields[name] = speed_wire_to_real(fields[name], speed_factor)

    return fields


def encode_motor_params(board_blob, edits, speed_factor):
    """The bytes a RAM write sends: the board's current blob with ``edits``
    ({field: value}, speeds in real µm/s) in place, at the board's length.

    Raises ValueError for an unknown field, a field the board's firmware
    does not serve, or a value the firmware would refuse.
    """
    board = decode_motor_blob(board_blob)
    served = served_motor_fields(board_blob)
    formats = dict(MOTOR_FIELDS)
    fields = dict(board)

    for name, value in edits.items():
        if name not in formats:
            raise ValueError(f"unknown motor param {name!r}")

        if name not in served:
            raise ValueError(
                f"{name} is not served by this motor firmware "
                f"({len(board_blob)} B blob)"
            )

        if name in MOTOR_SPEED_FIELDS:
            unchanged = round(value) == speed_wire_to_real(board[name], speed_factor)
            fields[name] = (
                board[name] if unchanged else speed_real_to_wire(value, speed_factor)
            )
            continue

        fields[name] = float(value) if formats[name] == "f" else int(value)

    problem = motor_blob_problem(fields)

    if problem:
        raise ValueError(problem)

    return encode_motor_blob(fields)[: len(board_blob)]
