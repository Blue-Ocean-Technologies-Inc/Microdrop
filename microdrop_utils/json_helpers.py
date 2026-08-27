# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import json
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
        raise ValueError("Invalid JSON input: must be a file path, JSON string, or dict")
    # Parse JSON into a Python object
    protocol_dict = json.loads(data)
    return protocol_dict
