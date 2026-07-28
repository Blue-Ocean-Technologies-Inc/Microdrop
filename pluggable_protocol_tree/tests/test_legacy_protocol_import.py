"""End-to-end checks for legacy protocol import, against the real samples."""
import glob
import os

import pytest

from pluggable_protocol_tree.consts import ELECTRODE_TO_CHANNEL_KEY
from pluggable_protocol_tree.services.legacy_protocol_import import (
    build_protocol_payload, convert_legacy_protocol, is_legacy_protocol_file,
    read_device_svg_channel_map, read_legacy_protocol, scan_for_device_folders,
)
from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    DEVICE_SVG_FILENAME, PROTOCOLS_DIR_NAME,
)
from pluggable_protocol_tree.services.protocol_validator import validate_protocol

# Sample Device Folders used by these tests; absent on most machines, in
# which case the tests that depend on them skip (see `_device` below).
# Developer-machine paths -- deliberately not in the package's consts.py,
# which ships as part of the runtime package.
LEGACY_SAMPLE_DEVICE_FOLDERS = (
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/August 2022 Quanterix test",
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/Duo Fluo v2 28x",
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/Zika-4d Mirror",
    "C:/Users/Info/Documents/MicroDrop/devices/DMF-90-pin-array",
)


def _device(folder_name):
    for folder in LEGACY_SAMPLE_DEVICE_FOLDERS:
        if os.path.basename(folder) == folder_name and os.path.isdir(folder):
            return folder
    pytest.skip(f"sample folder {folder_name!r} not present")


def _columns():
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.message_prompt_column import (
        make_message_prompt_column,
    )
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.repeat_duration_column import (
        make_repeat_duration_column,
    )
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column
    from pluggable_protocol_tree.builtins.trail_length_column import (
        make_trail_length_column,
    )
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    return [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column(), make_electrodes_column(),
            make_routes_column(), make_repetitions_column(),
            make_route_repetitions_column(), make_repeat_duration_column(),
            make_trail_length_column(), make_message_prompt_column()]


def _convert_all_in(folder_name):
    folder = _device(folder_name)
    channel_map = read_device_svg_channel_map(
        os.path.join(folder, DEVICE_SVG_FILENAME))
    converted_all = []
    for path in sorted(glob.glob(
            os.path.join(folder, PROTOCOLS_DIR_NAME, "*"))):
        if os.path.isfile(path) and is_legacy_protocol_file(path):
            converted_all.append(convert_legacy_protocol(
                read_legacy_protocol(path), channel_map))
    return converted_all


def test_every_sample_protocol_converts():
    """Nothing in the real corpus raises, and every protocol yields steps
    that actually carry converted data -- not just non-empty *placeholder*
    dicts (e.g. a converter emitting ``[{}, {}, {}]`` would satisfy a bare
    "truthy step_values" check but hold nothing usable)."""
    total = 0
    for folder in LEGACY_SAMPLE_DEVICE_FOLDERS:
        if not os.path.isdir(folder):
            continue
        for converted in _convert_all_in(os.path.basename(folder)):
            assert converted.step_values
            for values in converted.step_values:
                assert values
                assert values.get("name")
            total += 1
    if not total:
        pytest.skip("no sample folders present")


def test_scanner_excludes_non_protocol_files():
    root = os.path.dirname(_device("August 2022 Quanterix test"))
    quanterix = next(device for device in scan_for_device_folders(root)
                     if device.name == "August 2022 Quanterix test")
    assert all(not path.lower().endswith(".7z")
               for path in quanterix.protocol_paths)


def test_scalar_fields_convert_with_the_right_types_and_units():
    folder = _device("Duo Fluo v2 28x")
    converted = convert_legacy_protocol(
        read_legacy_protocol(os.path.join(folder, PROTOCOLS_DIR_NAME, "Feb6")),
        read_device_svg_channel_map(
            os.path.join(folder, DEVICE_SVG_FILENAME)))
    values = converted.step_values[0]
    assert isinstance(values["voltage"], int) and values["voltage"] == 120
    assert isinstance(values["frequency"], int)
    assert values["frequency"] == 10000
    assert 0 <= values["volume_threshold"] <= 100
    assert values["electrodes"]


def test_zika_protocols_produce_routes():
    """Routes are absent from Duo Fluo, so this folder is the one that catches
    a broken route conversion."""
    steps_with_routes = sum(
        1 for converted in _convert_all_in("Zika-4d Mirror")
        for values in converted.step_values if values.get("routes"))
    assert steps_with_routes > 0


def test_dangling_electrodes_are_reported_not_raised():
    """This device really did lose two electrodes its protocols still name."""
    unresolved = set()
    for converted in _convert_all_in("August 2022 Quanterix test"):
        unresolved.update(converted.report.unresolved_electrode_ids)
    assert {"path1651", "path1752"} <= unresolved


def test_payload_round_trips_and_validates():
    folder = _device("Duo Fluo v2 28x")
    channel_map = read_device_svg_channel_map(
        os.path.join(folder, DEVICE_SVG_FILENAME))
    converted = convert_legacy_protocol(
        read_legacy_protocol(os.path.join(folder, PROTOCOLS_DIR_NAME, "Feb6")),
        channel_map)
    columns = _columns()
    payload = build_protocol_payload(converted, columns)
    assert payload["protocol_metadata"][ELECTRODE_TO_CHANNEL_KEY] == channel_map
    assert len(payload["rows"]) == len(converted.step_values)
    assert validate_protocol(payload, columns, channel_map).is_empty
