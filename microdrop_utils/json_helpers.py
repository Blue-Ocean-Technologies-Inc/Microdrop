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
