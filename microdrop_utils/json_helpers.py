# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json
import math
import os


def load_python_object_from_json(json_input):
    # Load JSON string from file or directly from string
    if isinstance(json_input, str):
        if os.path.exists(json_input):  # It's a file path
            with open(json_input, "r") as f:
                data = f.read()
        else:  # It's a raw JSON string
            data = json_input
    elif isinstance(json_input, dict):
        data = json.dumps(json_input)  # If already dict, convert to string
    else:
        raise ValueError(
            "Invalid JSON input: must be a file path, JSON string, or dict"
        )
    # Parse JSON into a Python object
    protocol_dict = json.loads(data)

    return protocol_dict


def restore_nan_from_json_nulls(value):
    """Undo the NaN -> null step of a JSON-safe dump: every null inside a
    numeric list (one with at least one number among its leaves, nested
    lists included) becomes NaN again. Lists without a number keep their
    nulls, since there a null means "no value" rather than a lost NaN."""

    if isinstance(value, dict):
        return {key: restore_nan_from_json_nulls(item) for key, item in value.items()}

    if isinstance(value, list):
        if _is_numeric_list(value):
            return _nan_for_nulls(value)

        return [restore_nan_from_json_nulls(item) for item in value]

    return value


def _is_numeric_list(values):
    """True when every leaf is a number or null and at least one is a number."""
    leaves = list(_leaves(values))

    return all(
        leaf is None or (isinstance(leaf, (int, float)) and not isinstance(leaf, bool))
        for leaf in leaves
    ) and any(leaf is not None for leaf in leaves)


def _leaves(values):
    for item in values:
        if isinstance(item, list):
            yield from _leaves(item)

        else:
            yield item


def _nan_for_nulls(values):
    return [
        _nan_for_nulls(item)
        if isinstance(item, list)
        else (math.nan if item is None else item)
        for item in values
    ]
