# Import Legacy MicroDrop Protocols Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Protocol > Import Legacy Protocol...` menu action that converts a Python 2 MicroDrop protocol pickle, together with its `device.svg`, into the current `pluggable_protocol_tree` protocol and loads it into the tree unsaved.

**Architecture:** A Qt-free, plugin-free service package reads the legacy pickle, parses the device SVG for the electrode→channel map, and emits plain per-step dicts keyed by new column ids plus a conversion report. A thin layer above it reconciles those dicts against the *live* column set by building a `RowManager`, calls `to_json()`, and hands the payload to the existing `validate_protocol` → `confirm_report` → `set_state_from_json` load path. A PySide6 dialog drives device/protocol selection.

**Tech Stack:** Python 3.13, Traits (`HasTraits`), PySide6, pandas (reading legacy DataFrames only), pytest, Envisage/Pyface `DockPaneAction` menus.

**Spec:** `docs/superpowers/specs/2026-07-27-438-import-legacy-protocols-design.md`

## Global Constraints

- Work in the **submodule** checkout `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src`, on branch `feat/438-import-legacy-protocols`. Do not use the standalone `~/PycharmProjects/Microdrop` clone.
- Run Python only through pixi: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && <command>"`. Never invoke `.pixi/envs/default/python.exe` directly — numpy fails to import.
- Voltage (V) and frequency (Hz) are `Int` end-to-end. Never store them as float.
- Use f-strings everywhere, including log messages. No `%s`, `%r`, or `.format()`.
- Logging: `from logger.logger_service import get_logger` then `logger = get_logger(__name__)`. Never `logging.getLogger(__name__)`.
- No bare `except:` and no `print()` for errors. Catch `Exception` only; `logger.debug(...)` for tolerated paths, `logger.warning(..., exc_info=True)` when the stack matters.
- All dialogs go through `microdrop_application.dialogs.pyface_wrapper`. Never raw `QMessageBox` or `pyface.api` directly. Its `confirm(...)` already returns `YES` / `NO` / `CANCEL` — compare against those; do not mint parallel decision constants.
- No cross-plugin imports. The converter must not import `device_viewer`. Importing constants from another plugin's `consts.py` is allowed; importing its classes is not.
- Stateful classes are `HasTraits` with class-level trait declarations and `traits_init` instead of `__init__`. Stateless utility classes (only module functions / staticmethods) stay plain.
- Never import Qt in the service layer. Qt appears only in `views/`.
- Constants live in the subpackage's own `consts.py` in `UPPER_SNAKE_CASE`. Never define a constant mid-file.
- Descriptive names throughout; spell out units (`target_temperature_c`, not `temp`).
- Commit messages follow commitizen: imperative subject ~50 chars including the prefix, body explaining why.
- **Testing scope:** unit tests cover the Qt-free service package only (Tasks 1–6). Do **not** write Qt/GUI tests for Tasks 7–9 — the GUI is tested manually. Do not run the full test suite; run only the test file for the task at hand.

**Sample data.** Tests read real legacy files from these paths, and must **skip** (not fail) when a path is absent:

- `C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/legacy_protocols/August 2022 Quanterix test`
- `C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/legacy_protocols/Duo Fluo v2 28x`
- `C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/legacy_protocols/Zika-4d Mirror`
- `C:/Users/Info/Documents/MicroDrop/devices/DMF-90-pin-array`

---

## File Structure

New package `pluggable_protocol_tree/services/legacy_protocol_import/`:

| File | Responsibility |
|---|---|
| `__init__.py` | Re-export the public entry points |
| `consts.py` | All constants: legacy plugin names, legacy field names, mapping tables, folder names |
| `legacy_pickle_reader.py` | Read a Python 2 pickle into `LegacyProtocol` / `LegacyStep`; detect legacy files |
| `device_svg_channel_map.py` | `device.svg` → `{electrode_id: channel}` |
| `device_folder_scanner.py` | A directory → list of `LegacyDeviceFolder` |
| `conversion_report.py` | `ConversionReport` accumulator + human-readable rendering |
| `protocol_converter.py` | `LegacyProtocol` + channel map → per-step value dicts + report |
| `payload_builder.py` | Per-step dicts + live columns → protocol JSON payload |

New under `pluggable_protocol_tree/views/`:

| File | Responsibility |
|---|---|
| `legacy_import_dialog.py` | `LegacyImportDialogModel` (HasTraits, Qt-free) + `LegacyImportDialog` (PySide6) |

Modified: `pluggable_protocol_tree/menus.py`, `pluggable_protocol_tree/views/protocol_tree_pane.py`, `pluggable_protocol_tree/views/dock_pane.py`.

New tests under `pluggable_protocol_tree/tests/`: `test_legacy_pickle_reader.py`, `test_device_svg_channel_map.py`, `test_device_folder_scanner.py`, `test_protocol_converter.py`, `test_legacy_payload_builder.py`.

---

### Task 1: Legacy pickle reader

**Files:**
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/__init__.py`
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/consts.py`
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/legacy_pickle_reader.py`
- Test: `pluggable_protocol_tree/tests/test_legacy_pickle_reader.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `LEGACY_SAMPLE_DEVICE_FOLDERS: tuple[str, ...]` (consts, test-only convenience)
  - `DEVICE_SVG_FILENAME = "device.svg"`, `PROTOCOLS_DIR_NAME = "protocols"`, `DEVICES_DIR_NAME = "devices"` (consts)
  - `ELECTRODE_CONTROLLER_PLUGIN`, `DROPLET_PLANNING_PLUGIN`, `STEP_LABEL_PLUGIN`, `USER_PROMPT_PLUGIN`, `DROPBOT_PLUGIN`, `DMF_DEVICE_UI_PLUGIN`, `MR_BOX_PLUGIN`, `ZIKA_BOX_PLUGIN`, `PLATEAU_DETECTION_PLUGIN` (consts)
  - `class LegacyStep`: attribute `plugin_data: dict[str, dict]` — nested blobs already unpickled
  - `class LegacyProtocol`: attributes `name: str`, `version: str`, `n_repeats: int`, `steps: list[LegacyStep]`
  - `read_legacy_protocol(path: str) -> LegacyProtocol`
  - `is_legacy_protocol_file(path: str) -> bool`

**Background the implementer needs:**

A legacy protocol file has no extension and is a `pickle` (protocol 2) of `microdrop.protocol.Protocol`. Unpickling needs three accommodations:

1. `encoding="latin1"` — required for Python 2 `str` payloads.
2. The `microdrop.*` classes no longer exist, so `find_class` must return a stub type for them. `Protocol` is pickled with the `OBJ` opcode (calls `cls()`), `Step` with `NEWOBJ` (calls `cls.__new__(cls)`), so the stub must tolerate both.
3. pandas 2.x removed `pandas.core.indexes.numeric.Int64Index`. Without remapping it to `pandas.Index`, 11 sample steps throw `ModuleNotFoundError` while unpickling their `drop_routes` DataFrame — silently losing route data.

`Step.plugin_data` values are themselves pickled blobs (a `str` when they came through as latin1, sometimes `bytes`), so each must be re-unpickled with the same unpickler. This reader does that eagerly so downstream code sees plain dicts.

- [ ] **Step 1: Write the failing test**

Create `pluggable_protocol_tree/tests/test_legacy_pickle_reader.py`:

```python
"""Reading Python 2 MicroDrop protocol pickles."""
import glob
import os

import pytest

from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    ELECTRODE_CONTROLLER_PLUGIN, LEGACY_SAMPLE_DEVICE_FOLDERS,
    PROTOCOLS_DIR_NAME,
)
from pluggable_protocol_tree.services.legacy_protocol_import.legacy_pickle_reader import (
    is_legacy_protocol_file, read_legacy_protocol,
)


def _sample_protocol_paths():
    paths = []
    for folder in LEGACY_SAMPLE_DEVICE_FOLDERS:
        protocols_dir = os.path.join(folder, PROTOCOLS_DIR_NAME)
        if not os.path.isdir(protocols_dir):
            continue
        paths.extend(p for p in sorted(glob.glob(os.path.join(protocols_dir, "*")))
                     if os.path.isfile(p))
    return paths


SAMPLES = _sample_protocol_paths()
requires_samples = pytest.mark.skipif(
    not SAMPLES, reason="legacy sample protocol folders not present on this machine")


@requires_samples
def test_reads_every_sample_protocol_and_all_nested_blobs():
    """Every sample file that is a protocol parses, including every nested
    plugin blob. A nested failure here means route/electrode data is being
    lost silently -- e.g. the pandas Int64Index removal."""
    parsed = 0
    for path in SAMPLES:
        if not is_legacy_protocol_file(path):
            continue
        protocol = read_legacy_protocol(path)
        parsed += 1
        assert protocol.version == "0.2.0"
        assert protocol.steps, f"{path} parsed with no steps"
        for step in protocol.steps:
            for plugin_name, values in step.plugin_data.items():
                assert isinstance(values, dict), (
                    f"{path}: {plugin_name} blob did not unpickle to a dict")
    assert parsed >= 1


@requires_samples
def test_rejects_non_protocol_files():
    """A stray archive sits in one of the real protocols directories; it must
    not be offered as an importable protocol."""
    archives = [p for p in SAMPLES if p.lower().endswith(".7z")]
    if not archives:
        pytest.skip("no non-protocol file present in the samples")
    for path in archives:
        assert is_legacy_protocol_file(path) is False


@requires_samples
def test_electrode_states_are_indexed_by_electrode_id():
    protocol = next(read_legacy_protocol(p) for p in SAMPLES
                    if is_legacy_protocol_file(p))
    states = None
    for step in protocol.steps:
        values = step.plugin_data.get(ELECTRODE_CONTROLLER_PLUGIN, {})
        if "electrode_states" in values:
            states = values["electrode_states"]
            break
    assert states is not None
    assert all(isinstance(electrode_id, str) for electrode_id in states.index)


def test_missing_file_is_not_a_legacy_protocol(tmp_path):
    assert is_legacy_protocol_file(str(tmp_path / "nope")) is False


def test_plain_text_file_is_not_a_legacy_protocol(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("just some text", encoding="utf-8")
    assert is_legacy_protocol_file(str(path)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_legacy_pickle_reader.py -v"`

Expected: FAIL with `ModuleNotFoundError: No module named 'pluggable_protocol_tree.services.legacy_protocol_import'`

- [ ] **Step 3: Create the package consts**

Create `pluggable_protocol_tree/services/legacy_protocol_import/__init__.py` as an empty file.

Create `pluggable_protocol_tree/services/legacy_protocol_import/consts.py`:

```python
"""Constants for importing protocols authored in the Python 2 MicroDrop
(github.com/sci-bots/microdrop)."""

# --- legacy Device Folder layout ---
DEVICE_SVG_FILENAME = "device.svg"
PROTOCOLS_DIR_NAME = "protocols"
DEVICES_DIR_NAME = "devices"

# --- legacy plugin names, as they appear in Step.plugin_data ---
ELECTRODE_CONTROLLER_PLUGIN = "microdrop.electrode_controller_plugin"
DROPLET_PLANNING_PLUGIN = "droplet_planning_plugin"
STEP_LABEL_PLUGIN = "step_label_plugin"
USER_PROMPT_PLUGIN = "user_prompt_plugin"
DROPBOT_PLUGIN = "dropbot_plugin"
DMF_DEVICE_UI_PLUGIN = "dmf_device_ui_plugin"
MR_BOX_PLUGIN = "mr_box_plugin"
ZIKA_BOX_PLUGIN = "zika_box_plugin"
PLATEAU_DETECTION_PLUGIN = "plateau_detection_plugin"

# --- module prefixes that no longer exist and are stubbed while unpickling ---
LEGACY_STUBBED_MODULE_PREFIXES = (
    "microdrop", "microdrop_utility", "flatland", "pygtkhelpers",
)

# --- pandas index classes removed in pandas 2.x, remapped to pandas.Index ---
REMOVED_PANDAS_INDEX_MODULE = "pandas.core.indexes.numeric"
REMOVED_PANDAS_INDEX_CLASSES = frozenset(
    {"Int64Index", "Float64Index", "UInt64Index"})

# --- the legacy protocol format version this importer understands ---
SUPPORTED_LEGACY_PROTOCOL_VERSION = "0.2.0"

# --- sample Device Folders used by the unit tests; absent on most machines ---
LEGACY_SAMPLE_DEVICE_FOLDERS = (
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/August 2022 Quanterix test",
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/Duo Fluo v2 28x",
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/Zika-4d Mirror",
    "C:/Users/Info/Documents/MicroDrop/devices/DMF-90-pin-array",
)
```

- [ ] **Step 4: Write the reader**

Create `pluggable_protocol_tree/services/legacy_protocol_import/legacy_pickle_reader.py`:

```python
"""Read protocols authored in the Python 2 MicroDrop.

A legacy protocol file is an extension-less pickle (protocol 2) of
``microdrop.protocol.Protocol``. Reading one in Python 3 needs three
accommodations, all handled by ``_LegacyUnpickler``:

* ``encoding="latin1"`` so Python 2 ``str`` payloads decode.
* The ``microdrop.*`` classes are long gone, so they resolve to a stub
  type. ``Protocol`` arrives via the OBJ opcode (which calls ``cls()``)
  and ``Step`` via NEWOBJ (``cls.__new__(cls)``), so the stub tolerates
  both construction paths.
* pandas 2.x deleted ``Int64Index`` and friends. Without remapping them
  to ``pandas.Index`` the ``drop_routes`` DataFrames raise
  ``ModuleNotFoundError`` and route data vanishes silently.

``Step.plugin_data`` values are themselves pickled blobs, so this module
unpickles them eagerly -- callers only ever see plain dicts.
"""

import io
import pickle

import pandas as pd

from logger.logger_service import get_logger

from .consts import (
    LEGACY_STUBBED_MODULE_PREFIXES, REMOVED_PANDAS_INDEX_CLASSES,
    REMOVED_PANDAS_INDEX_MODULE,
)

logger = get_logger(__name__)


class _LegacyObjectStub:
    """Stand-in for any long-gone MicroDrop class met while unpickling.

    Accepts both construction paths pickle uses and copies the instance
    state straight onto ``__dict__`` so attributes read naturally."""

    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)
        else:
            self.__dict__["state"] = state


class _LegacyUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module.startswith(LEGACY_STUBBED_MODULE_PREFIXES):
            return type(name, (_LegacyObjectStub,), {"__module__": module})
        if (module == REMOVED_PANDAS_INDEX_MODULE
                and name in REMOVED_PANDAS_INDEX_CLASSES):
            return pd.Index
        return super().find_class(module, name)


def _loads(blob) -> object:
    """Unpickle a nested per-plugin blob. Latin-1 round-trips the bytes that
    came in as a Python 2 ``str``."""
    raw = blob.encode("latin1") if isinstance(blob, str) else blob
    return _LegacyUnpickler(io.BytesIO(raw), encoding="latin1").load()


class LegacyStep:
    """One step of a legacy protocol: legacy plugin name -> its value dict."""

    def __init__(self, plugin_data: dict):
        self.plugin_data = plugin_data


class LegacyProtocol:
    """A legacy protocol: a flat list of steps (the format has no groups)."""

    def __init__(self, name: str, version: str, n_repeats: int,
                 steps: list):
        self.name = name
        self.version = version
        self.n_repeats = n_repeats
        self.steps = steps


def _read_raw_protocol(path: str):
    with open(path, "rb") as handle:
        return _LegacyUnpickler(handle, encoding="latin1").load()


def read_legacy_protocol(path: str) -> LegacyProtocol:
    """Read ``path`` into a ``LegacyProtocol`` with every nested plugin blob
    already unpickled. Raises if the file is not a legacy protocol."""
    raw = _read_raw_protocol(path)
    steps = []
    for index, raw_step in enumerate(getattr(raw, "steps", [])):
        plugin_data = {}
        for plugin_name, blob in getattr(raw_step, "plugin_data", {}).items():
            try:
                values = _loads(blob)
            except Exception as e:
                logger.warning(
                    f"step {index} of {path!r}: could not unpickle "
                    f"{plugin_name!r} data: {e}", exc_info=True)
                continue
            if isinstance(values, dict):
                plugin_data[plugin_name] = values
            else:
                logger.debug(
                    f"step {index} of {path!r}: {plugin_name!r} data is "
                    f"{type(values).__name__}, not a dict; ignored")
        steps.append(LegacyStep(plugin_data))
    return LegacyProtocol(
        name=str(getattr(raw, "name", "") or ""),
        version=str(getattr(raw, "version", "") or ""),
        n_repeats=int(getattr(raw, "n_repeats", 1) or 1),
        steps=steps,
    )


def is_legacy_protocol_file(path: str) -> bool:
    """True when ``path`` unpickles into something that looks like a legacy
    protocol. Used to filter directory listings, which in practice contain
    unrelated files (a 7-Zip archive sits in one real protocols folder)."""
    try:
        raw = _read_raw_protocol(path)
    except Exception as e:
        logger.debug(f"{path!r} is not a legacy protocol: {e}")
        return False
    return isinstance(getattr(raw, "steps", None), list)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_legacy_pickle_reader.py -v"`

Expected: PASS (5 tests, or skips if the sample folders are absent)

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/services/legacy_protocol_import/ pluggable_protocol_tree/tests/test_legacy_pickle_reader.py
git commit -m "feat: read Python 2 MicroDrop protocol pickles"
```

---

### Task 2: Device SVG channel map

**Files:**
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/device_svg_channel_map.py`
- Test: `pluggable_protocol_tree/tests/test_device_svg_channel_map.py`

**Interfaces:**
- Consumes: `consts.DEVICE_SVG_FILENAME`
- Produces: `read_device_svg_channel_map(svg_path: str) -> dict[str, int]` mapping electrode id to channel number.

**Background the implementer needs:**

Both legacy and current device SVGs annotate each electrode `<path>` with `id="electrode053"` (or `id="path609"` on Inkscape-authored devices) and `data-channels="53"`. Only those two attributes are needed.

Do **not** import `device_viewer`'s `SVGProcessor` for this — that would be a cross-plugin import, and the converter needs no geometry. Use `xml.etree.ElementTree`, which handles the SVG namespace via a wildcard tag match.

Expected counts for the sample devices: Duo Fluo 126, DMF-90-pin-array 92, Zika-4d Mirror 87, Quanterix 71.

- [ ] **Step 1: Write the failing test**

Create `pluggable_protocol_tree/tests/test_device_svg_channel_map.py`:

```python
"""Extracting the electrode-id -> channel map from a device SVG."""
import os

import pytest

from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    DEVICE_SVG_FILENAME, LEGACY_SAMPLE_DEVICE_FOLDERS,
)
from pluggable_protocol_tree.services.legacy_protocol_import.device_svg_channel_map import (
    read_device_svg_channel_map,
)

EXPECTED_ELECTRODE_COUNTS = {
    "August 2022 Quanterix test": 71,
    "Duo Fluo v2 28x": 126,
    "Zika-4d Mirror": 87,
    "DMF-90-pin-array": 92,
}


@pytest.mark.parametrize("folder", LEGACY_SAMPLE_DEVICE_FOLDERS)
def test_sample_device_electrode_counts(folder):
    svg_path = os.path.join(folder, DEVICE_SVG_FILENAME)
    if not os.path.isfile(svg_path):
        pytest.skip(f"{svg_path} not present on this machine")
    channel_map = read_device_svg_channel_map(svg_path)
    expected = EXPECTED_ELECTRODE_COUNTS[os.path.basename(folder)]
    assert len(channel_map) == expected
    assert all(isinstance(channel, int) for channel in channel_map.values())
    assert all(isinstance(electrode_id, str) for electrode_id in channel_map)


def test_parses_ids_and_channels(tmp_path):
    svg = tmp_path / "device.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<g><path id="electrode000" data-channels="119" d="M 0,0 H 1 V 1 Z"/>'
        '<path id="electrode001" data-channels="7" d="M 0,0 H 1 V 1 Z"/></g>'
        '</svg>', encoding="utf-8")
    assert read_device_svg_channel_map(str(svg)) == {
        "electrode000": 119, "electrode001": 7}


def test_paths_without_a_channel_are_skipped(tmp_path):
    """Decorative paths carry no data-channels and are not electrodes."""
    svg = tmp_path / "device.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path id="electrode000" data-channels="3" d="M 0,0 Z"/>'
        '<path id="border" d="M 0,0 Z"/></svg>', encoding="utf-8")
    assert read_device_svg_channel_map(str(svg)) == {"electrode000": 3}


def test_non_integer_channel_is_skipped(tmp_path):
    svg = tmp_path / "device.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<path id="a" data-channels="3" d="M 0,0 Z"/>'
        '<path id="b" data-channels="" d="M 0,0 Z"/>'
        '<path id="c" data-channels="1,2" d="M 0,0 Z"/></svg>',
        encoding="utf-8")
    assert read_device_svg_channel_map(str(svg)) == {"a": 3}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_device_svg_channel_map.py -v"`

Expected: FAIL with `ModuleNotFoundError: No module named '...device_svg_channel_map'`

- [ ] **Step 3: Write the implementation**

Create `pluggable_protocol_tree/services/legacy_protocol_import/device_svg_channel_map.py`:

```python
"""Electrode-id -> channel map read straight from a device SVG.

Deliberately a local XML scan rather than a call into ``device_viewer``'s
SVG processor: reaching into another plugin is forbidden, and conversion
needs only the ``id`` and ``data-channels`` attributes -- no geometry.
"""

from xml.etree import ElementTree

from logger.logger_service import get_logger

logger = get_logger(__name__)

# SVG puts elements in a namespace; match any namespace on the local name.
_PATH_ELEMENT_TAG = "{*}path"
_CHANNEL_ATTRIBUTE = "data-channels"


def read_device_svg_channel_map(svg_path: str) -> dict:
    """Map every electrode id in ``svg_path`` to its channel number.

    Paths without an ``id``, without ``data-channels``, or whose channel is
    not a single integer are skipped -- decorative shapes and multi-channel
    annotations are not importable electrodes."""
    root = ElementTree.parse(svg_path).getroot()
    channel_map = {}
    for element in root.iter(_PATH_ELEMENT_TAG):
        electrode_id = element.attrib.get("id")
        raw_channel = element.attrib.get(_CHANNEL_ATTRIBUTE)
        if not electrode_id or not raw_channel:
            continue
        try:
            channel_map[electrode_id] = int(raw_channel)
        except ValueError:
            logger.debug(
                f"{svg_path!r}: electrode {electrode_id!r} has non-integer "
                f"{_CHANNEL_ATTRIBUTE}={raw_channel!r}; skipped")
    return channel_map
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_device_svg_channel_map.py -v"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/legacy_protocol_import/device_svg_channel_map.py pluggable_protocol_tree/tests/test_device_svg_channel_map.py
git commit -m "feat: map device SVG electrodes to channels"
```

---

### Task 3: Device folder scanner

**Files:**
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/device_folder_scanner.py`
- Test: `pluggable_protocol_tree/tests/test_device_folder_scanner.py`

**Interfaces:**
- Consumes: `consts.DEVICE_SVG_FILENAME`, `consts.PROTOCOLS_DIR_NAME`, `consts.DEVICES_DIR_NAME`, `legacy_pickle_reader.is_legacy_protocol_file`
- Produces:
  - `class LegacyDeviceFolder(HasTraits)`: traits `name: Str`, `device_svg_path: Str`, `protocol_paths: List(Str)`
  - `scan_for_device_folders(root_path: str) -> list[LegacyDeviceFolder]`

**Background the implementer needs:**

The user should not have to know which level of an old MicroDrop tree to point at. Three shapes must all work:

| Shape | Detected by | Devices returned |
|---|---|---|
| MicroDrop root | contains a `devices/` subdirectory | subdirectories of `devices/` that have a `device.svg` |
| A single device folder | contains `device.svg` and `protocols/` | itself |
| A parent of device folders | its subdirectories contain `device.svg` | those subdirectories |

`protocol_paths` lists only files that pass `is_legacy_protocol_file`, which is what keeps the stray `Sci-Bots-Quanterix-Device.7z` out of the dropdown. Results are sorted by name so the dropdown order is stable.

- [ ] **Step 1: Write the failing test**

Create `pluggable_protocol_tree/tests/test_device_folder_scanner.py`:

```python
"""Resolving whatever directory the user picked into legacy device folders."""
import os
import pickle

import pytest

from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    LEGACY_SAMPLE_DEVICE_FOLDERS,
)
from pluggable_protocol_tree.services.legacy_protocol_import.device_folder_scanner import (
    scan_for_device_folders,
)

_SVG = ('<svg xmlns="http://www.w3.org/2000/svg">'
        '<path id="electrode000" data-channels="1" d="M 0,0 Z"/></svg>')


class _FakeProtocol:
    """Pickles to something read back as a protocol-shaped object."""

    def __init__(self):
        self.steps = []
        self.name = "fake"
        self.version = "0.2.0"
        self.n_repeats = 1


def _make_device_folder(base, name, protocol_names=("proto-a", "proto-b")):
    device_dir = base / name
    (device_dir / "protocols").mkdir(parents=True)
    (device_dir / "device.svg").write_text(_SVG, encoding="utf-8")
    for protocol_name in protocol_names:
        with open(device_dir / "protocols" / protocol_name, "wb") as handle:
            pickle.dump(_FakeProtocol(), handle, protocol=2)
    return device_dir


def test_scans_a_single_device_folder(tmp_path):
    _make_device_folder(tmp_path, "DeviceOne")
    found = scan_for_device_folders(str(tmp_path / "DeviceOne"))
    assert [device.name for device in found] == ["DeviceOne"]
    assert len(found[0].protocol_paths) == 2


def test_scans_a_microdrop_root_with_a_devices_dir(tmp_path):
    devices_dir = tmp_path / "devices"
    devices_dir.mkdir()
    _make_device_folder(devices_dir, "DeviceB")
    _make_device_folder(devices_dir, "DeviceA")
    found = scan_for_device_folders(str(tmp_path))
    assert [device.name for device in found] == ["DeviceA", "DeviceB"]


def test_scans_a_parent_of_device_folders(tmp_path):
    _make_device_folder(tmp_path, "DeviceB")
    _make_device_folder(tmp_path, "DeviceA")
    found = scan_for_device_folders(str(tmp_path))
    assert [device.name for device in found] == ["DeviceA", "DeviceB"]


def test_non_protocol_files_are_excluded(tmp_path):
    device_dir = _make_device_folder(tmp_path, "DeviceOne")
    (device_dir / "protocols" / "notes.7z").write_bytes(b"7z\xbc\xaf\x27\x1c")
    found = scan_for_device_folders(str(tmp_path / "DeviceOne"))
    assert all(not path.endswith(".7z") for path in found[0].protocol_paths)
    assert len(found[0].protocol_paths) == 2


def test_directory_without_devices_yields_nothing(tmp_path):
    (tmp_path / "empty").mkdir()
    assert scan_for_device_folders(str(tmp_path / "empty")) == []


def test_missing_directory_yields_nothing(tmp_path):
    assert scan_for_device_folders(str(tmp_path / "nope")) == []


def test_device_folder_without_protocols_dir_is_still_found(tmp_path):
    device_dir = tmp_path / "DeviceOne"
    device_dir.mkdir()
    (device_dir / "device.svg").write_text(_SVG, encoding="utf-8")
    found = scan_for_device_folders(str(device_dir))
    assert [device.name for device in found] == ["DeviceOne"]
    assert found[0].protocol_paths == []


@pytest.mark.parametrize("folder", LEGACY_SAMPLE_DEVICE_FOLDERS)
def test_real_sample_folders_scan(folder):
    if not os.path.isdir(folder):
        pytest.skip(f"{folder} not present on this machine")
    found = scan_for_device_folders(folder)
    assert len(found) == 1
    assert found[0].name == os.path.basename(folder)
    assert found[0].protocol_paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_device_folder_scanner.py -v"`

Expected: FAIL with `ModuleNotFoundError: No module named '...device_folder_scanner'`

- [ ] **Step 3: Write the implementation**

Create `pluggable_protocol_tree/services/legacy_protocol_import/device_folder_scanner.py`:

```python
"""Turn whatever directory the user picked into legacy Device Folders.

Three shapes are accepted so the user never has to know which level of an
old MicroDrop tree to point at: a MicroDrop root (has ``devices/``), a
single Device Folder (has ``device.svg``), or a plain parent of Device
Folders.
"""

import os

from traits.api import HasTraits, List, Str

from logger.logger_service import get_logger

from .consts import (
    DEVICE_SVG_FILENAME, DEVICES_DIR_NAME, PROTOCOLS_DIR_NAME,
)
from .legacy_pickle_reader import is_legacy_protocol_file

logger = get_logger(__name__)


class LegacyDeviceFolder(HasTraits):
    """One old-MicroDrop Device Folder: its SVG and its importable protocols."""

    name = Str()
    device_svg_path = Str()
    protocol_paths = List(Str())


def _is_device_folder(path: str) -> bool:
    return os.path.isfile(os.path.join(path, DEVICE_SVG_FILENAME))


def _protocol_paths_in(device_dir: str) -> list:
    """Every file under ``protocols/`` that actually reads as a legacy
    protocol. Directory listings really do contain unrelated files."""
    protocols_dir = os.path.join(device_dir, PROTOCOLS_DIR_NAME)
    if not os.path.isdir(protocols_dir):
        return []
    candidates = sorted(os.path.join(protocols_dir, entry)
                        for entry in os.listdir(protocols_dir))
    return [path for path in candidates
            if os.path.isfile(path) and is_legacy_protocol_file(path)]


def _as_device_folder(device_dir: str) -> LegacyDeviceFolder:
    return LegacyDeviceFolder(
        name=os.path.basename(os.path.normpath(device_dir)),
        device_svg_path=os.path.join(device_dir, DEVICE_SVG_FILENAME),
        protocol_paths=_protocol_paths_in(device_dir),
    )


def _child_device_folders(parent_dir: str) -> list:
    children = sorted(os.path.join(parent_dir, entry)
                      for entry in os.listdir(parent_dir))
    return [_as_device_folder(child) for child in children
            if os.path.isdir(child) and _is_device_folder(child)]


def scan_for_device_folders(root_path: str) -> list:
    """Device Folders reachable from ``root_path``, sorted by name.

    Returns an empty list rather than raising when the path is missing or
    holds nothing importable -- the dialog simply shows no devices."""
    if not root_path or not os.path.isdir(root_path):
        logger.debug(f"{root_path!r} is not a directory; no devices found")
        return []
    devices_dir = os.path.join(root_path, DEVICES_DIR_NAME)
    if os.path.isdir(devices_dir):
        return _child_device_folders(devices_dir)
    if _is_device_folder(root_path):
        return [_as_device_folder(root_path)]
    return _child_device_folders(root_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_device_folder_scanner.py -v"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/legacy_protocol_import/device_folder_scanner.py pluggable_protocol_tree/tests/test_device_folder_scanner.py
git commit -m "feat: scan legacy MicroDrop device folders"
```

---

### Task 4: Conversion report

**Files:**
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/conversion_report.py`
- Test: folded into Task 5's `test_protocol_converter.py` (the report is only meaningful once something populates it)

**Interfaces:**
- Consumes: nothing.
- Produces: `class ConversionReport(HasTraits)` with
  - traits `step_count: Int`, `mapped_columns: List(Str)`, `dropped_fields: Dict(Str, Int)`, `unresolved_electrode_ids: Dict(Str, Int)`, `failed_steps: List(Str)`
  - methods `record_mapped(column_id: str)`, `record_dropped(legacy_field: str)`, `record_unresolved_electrode(electrode_id: str)`, `record_step_failure(description: str)`, `render() -> str`

Add no other methods. In particular do not add an `is_clean` convenience property — nothing consumes one.

**Background the implementer needs:**

`dropped_fields` and `unresolved_electrode_ids` are counters keyed by name, so the summary can say *how many* steps lost a field rather than just naming it. `render()` produces the body of the summary dialog shown after import.

- [ ] **Step 1: Write the implementation**

Create `pluggable_protocol_tree/services/legacy_protocol_import/conversion_report.py`:

```python
"""What a legacy protocol conversion mapped, dropped, and could not resolve.

Counts are per-step so the summary can say how much data a dropped field
actually represented, rather than just naming it.
"""

from traits.api import Dict, HasTraits, Int, List, Str


class ConversionReport(HasTraits):
    """Accumulated outcome of converting one legacy protocol."""

    step_count = Int(0)
    mapped_columns = List(Str())
    dropped_fields = Dict(Str(), Int())
    unresolved_electrode_ids = Dict(Str(), Int())
    failed_steps = List(Str())

    def record_mapped(self, column_id: str) -> None:
        if column_id not in self.mapped_columns:
            self.mapped_columns.append(column_id)

    def record_dropped(self, legacy_field: str) -> None:
        self.dropped_fields[legacy_field] = (
            self.dropped_fields.get(legacy_field, 0) + 1)

    def record_unresolved_electrode(self, electrode_id: str) -> None:
        self.unresolved_electrode_ids[electrode_id] = (
            self.unresolved_electrode_ids.get(electrode_id, 0) + 1)

    def record_step_failure(self, description: str) -> None:
        self.failed_steps.append(description)

    def render(self) -> str:
        """Human-readable summary for the post-import dialog."""
        lines = [f"Converted {self.step_count} steps."]
        if self.mapped_columns:
            lines.append("")
            lines.append("Mapped: " + ", ".join(sorted(self.mapped_columns)))
        if self.dropped_fields:
            lines.append("")
            lines.append("Dropped (no equivalent in this build):")
            for field, count in sorted(self.dropped_fields.items()):
                lines.append(f"    {field}  ({count} steps)")
        if self.unresolved_electrode_ids:
            lines.append("")
            lines.append("Electrodes not present in the selected device:")
            for electrode_id, count in sorted(
                    self.unresolved_electrode_ids.items()):
                lines.append(f"    {electrode_id}  ({count} steps)")
        if self.failed_steps:
            lines.append("")
            lines.append("Steps imported with defaults after an error:")
            for description in self.failed_steps:
                lines.append(f"    {description}")
        return "\n".join(lines)
```

- [ ] **Step 2: Verify it imports**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.services.legacy_protocol_import.conversion_report import ConversionReport; r = ConversionReport(step_count=3); r.record_dropped(\"mr_box_plugin.Pump\"); r.record_dropped(\"mr_box_plugin.Pump\"); print(r.render())'"`

Expected: prints `Converted 3 steps.` followed by a `Dropped` section showing `mr_box_plugin.Pump  (2 steps)`

- [ ] **Step 3: Commit**

```bash
git add pluggable_protocol_tree/services/legacy_protocol_import/conversion_report.py
git commit -m "feat: add legacy conversion report model"
```

---

### Task 5: Protocol converter

**Files:**
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/protocol_converter.py`
- Modify: `pluggable_protocol_tree/services/legacy_protocol_import/consts.py` (add the mapping tables)
- Test: `pluggable_protocol_tree/tests/test_protocol_converter.py`

**Interfaces:**
- Consumes: `LegacyProtocol`, `LegacyStep`, `ConversionReport`, plus the legacy plugin-name constants from Task 1.
- Produces:
  - `class ConvertedProtocol(HasTraits)`: traits `step_values: List(Dict)`, `protocol_repeats: Int`, `electrode_to_channel: Dict(Str, Int)`, `report: Instance(ConversionReport)`
  - `convert_legacy_protocol(protocol: LegacyProtocol, electrode_to_channel: dict) -> ConvertedProtocol`

Each entry of `step_values` is a plain dict keyed by new column id / compound field id, e.g.
`{"name": "A1", "voltage": 120, "frequency": 10000, "duration_s": 1.0, "electrodes": ["path609"], "routes": [], "route_repetitions": 1, "repeat_duration": 0.0, "trail_length": 1, "message_prompt": "", "volume_threshold": 0, "video": False, "set_magnet": True, "magnet_on": False}`.

`repeat_duration_controls` is carried in the same dict as a boolean; Task 6 lifts it out into a row flag rather than a column value.

**Background the implementer needs:**

The full mapping is section 2 of the spec. Points that are easy to get wrong:

- Voltage and frequency are floats in the legacy format and `Int` in the new one. Round them.
- `volume_threshold` changes units: legacy is a 0–1 fraction, the new column is a 0–100 integer percent. Multiply by 100, round, clamp to 0–100.
- `electrode_states` is a `pandas.Series` of booleans indexed by electrode id. Keep the ids whose value is truthy, and drop (while recording) any id absent from `electrode_to_channel` — the Quanterix device really does lack `path1651` and `path1752`.
- `drop_routes` is a DataFrame with `route_i`, `electrode_i`, `transition_i`. Group by `route_i`, sort each group by `transition_i`, take `electrode_i`. Apply the same unresolved-id filtering. Skip a route entirely if filtering empties it.
- `step_label_plugin.label` is usually blank; fall back to `Step {index + 1}`.
- Magnet comes from either `mr_box_plugin` or `zika_box_plugin`. When both are present, `zika_box_plugin` wins and the shadowed one is recorded as dropped.
- `set_magnet` / `set_temperature` are the compound gates. Legacy always commanded the peripheral, so set the gate True whenever the source plugin is present on the step.
- Everything in `DROPPED_LEGACY_FIELDS` is recorded per step and not mapped.

- [ ] **Step 1: Add the mapping tables to consts.py**

Append to `pluggable_protocol_tree/services/legacy_protocol_import/consts.py`:

```python
# --- new-format column / compound-field ids written by the converter ---
NAME_COLUMN_ID = "name"
VOLTAGE_COLUMN_ID = "voltage"
FREQUENCY_COLUMN_ID = "frequency"
DURATION_COLUMN_ID = "duration_s"
ELECTRODES_COLUMN_ID = "electrodes"
ROUTES_COLUMN_ID = "routes"
ROUTE_REPETITIONS_COLUMN_ID = "route_repetitions"
REPEAT_DURATION_COLUMN_ID = "repeat_duration"
REPEAT_DURATION_CONTROLS_FLAG = "repeat_duration_controls"
TRAIL_LENGTH_COLUMN_ID = "trail_length"
MESSAGE_PROMPT_COLUMN_ID = "message_prompt"
VOLUME_THRESHOLD_COLUMN_ID = "volume_threshold"
VIDEO_COLUMN_ID = "video"
REPETITIONS_COLUMN_ID = "repetitions"
SET_MAGNET_FIELD_ID = "set_magnet"
MAGNET_ON_FIELD_ID = "magnet_on"
SET_TEMPERATURE_FIELD_ID = "set_temperature"
TARGET_TEMPERATURE_FIELD_ID = "target_temperature_c"

# --- legacy field names, as they appear inside each plugin's value dict ---
LEGACY_VOLTAGE_FIELD = "Voltage (V)"
LEGACY_FREQUENCY_FIELD = "Frequency (Hz)"
LEGACY_DURATION_FIELD = "Duration (s)"
LEGACY_ELECTRODE_STATES_FIELD = "electrode_states"
LEGACY_DROP_ROUTES_FIELD = "drop_routes"
LEGACY_ROUTE_REPEATS_FIELD = "route_repeats"
LEGACY_REPEAT_DURATION_FIELD = "repeat_duration_s"
LEGACY_TRAIL_LENGTH_FIELD = "trail_length"
LEGACY_LABEL_FIELD = "label"
LEGACY_MESSAGE_FIELD = "message"
LEGACY_VOLUME_THRESHOLD_FIELD = "volume_threshold"
LEGACY_VIDEO_ENABLED_FIELD = "video_enabled"
LEGACY_MAGNET_FIELD = "Magnet"
LEGACY_HEATER_FIELD = "Heater"
LEGACY_HEATER_TEMPERATURE_FIELD = "Heater_temperature"

# --- drop_routes DataFrame columns ---
LEGACY_ROUTE_INDEX_COLUMN = "route_i"
LEGACY_ROUTE_ELECTRODE_COLUMN = "electrode_i"
LEGACY_ROUTE_TRANSITION_COLUMN = "transition_i"

# --- legacy fields with no equivalent; recorded in the report and dropped ---
DROPPED_LEGACY_FIELDS = {
    MR_BOX_PLUGIN: (
        "Pump", "Pump_frequency_(hz)", "Pump_duration_(s)", "Measure_PMT",
        "Measurement_duration_(s)", "Auto pump electrode",
        "Magnet_height(mm)",
    ),
    USER_PROMPT_PLUGIN: ("schema",),
    PLATEAU_DETECTION_PLUGIN: (
        "Plateau Detection", "Check Split", "Calibrate Threshold",
    ),
}

# --- volume_threshold: legacy 0-1 fraction -> new 0-100 integer percent ---
VOLUME_THRESHOLD_PERCENT_SCALE = 100
VOLUME_THRESHOLD_MIN_PERCENT = 0
VOLUME_THRESHOLD_MAX_PERCENT = 100
```

- [ ] **Step 2: Write the failing test**

Create `pluggable_protocol_tree/tests/test_protocol_converter.py`:

```python
"""Mapping legacy protocol steps onto new-format column values."""
import pandas as pd
import pytest

from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    DMF_DEVICE_UI_PLUGIN, DROPBOT_PLUGIN, DROPLET_PLANNING_PLUGIN,
    ELECTRODE_CONTROLLER_PLUGIN, MR_BOX_PLUGIN, PLATEAU_DETECTION_PLUGIN,
    STEP_LABEL_PLUGIN, USER_PROMPT_PLUGIN, ZIKA_BOX_PLUGIN,
)
from pluggable_protocol_tree.services.legacy_protocol_import.legacy_pickle_reader import (
    LegacyProtocol, LegacyStep,
)
from pluggable_protocol_tree.services.legacy_protocol_import.protocol_converter import (
    convert_legacy_protocol,
)

CHANNEL_MAP = {"e0": 0, "e1": 1, "e2": 2, "e3": 3}


def _protocol(plugin_data, n_repeats=1):
    return LegacyProtocol(name="p", version="0.2.0", n_repeats=n_repeats,
                          steps=[LegacyStep(plugin_data)])


def _convert(plugin_data, n_repeats=1):
    return convert_legacy_protocol(_protocol(plugin_data, n_repeats),
                                   CHANNEL_MAP)


def test_voltage_and_frequency_become_ints():
    converted = _convert({ELECTRODE_CONTROLLER_PLUGIN: {
        "Voltage (V)": 120.0, "Frequency (Hz)": 10000.0, "Duration (s)": 1.5}})
    values = converted.step_values[0]
    assert values["voltage"] == 120
    assert isinstance(values["voltage"], int)
    assert values["frequency"] == 10000
    assert isinstance(values["frequency"], int)
    assert values["duration_s"] == 1.5


def test_electrode_states_become_active_electrode_ids():
    states = pd.Series({"e0": True, "e1": False, "e2": True})
    converted = _convert({ELECTRODE_CONTROLLER_PLUGIN: {
        "electrode_states": states}})
    assert converted.step_values[0]["electrodes"] == ["e0", "e2"]


def test_electrodes_absent_from_the_device_are_dropped_and_reported():
    states = pd.Series({"e0": True, "ghost": True})
    converted = _convert({ELECTRODE_CONTROLLER_PLUGIN: {
        "electrode_states": states}})
    assert converted.step_values[0]["electrodes"] == ["e0"]
    assert converted.report.unresolved_electrode_ids == {"ghost": 1}


def test_drop_routes_become_ordered_electrode_id_lists():
    routes = pd.DataFrame({
        "route_i": [0, 0, 0, 1, 1],
        "electrode_i": ["e0", "e1", "e2", "e3", "e0"],
        "transition_i": [0, 1, 2, 0, 1],
    })
    converted = _convert({DROPLET_PLANNING_PLUGIN: {"drop_routes": routes}})
    assert converted.step_values[0]["routes"] == [
        ["e0", "e1", "e2"], ["e3", "e0"]]


def test_route_electrodes_are_ordered_by_transition_not_row_order():
    routes = pd.DataFrame({
        "route_i": [0, 0, 0],
        "electrode_i": ["e2", "e0", "e1"],
        "transition_i": [2, 0, 1],
    })
    converted = _convert({DROPLET_PLANNING_PLUGIN: {"drop_routes": routes}})
    assert converted.step_values[0]["routes"] == [["e0", "e1", "e2"]]


def test_empty_drop_routes_yield_no_routes():
    routes = pd.DataFrame(
        {"route_i": [], "electrode_i": [], "transition_i": []})
    converted = _convert({DROPLET_PLANNING_PLUGIN: {"drop_routes": routes}})
    assert converted.step_values[0]["routes"] == []


def test_repeat_duration_sets_the_row_flag_only_when_positive():
    on = _convert({DROPLET_PLANNING_PLUGIN: {"repeat_duration_s": 5}})
    off = _convert({DROPLET_PLANNING_PLUGIN: {"repeat_duration_s": 0}})
    assert on.step_values[0]["repeat_duration"] == 5.0
    assert on.step_values[0]["repeat_duration_controls"] is True
    assert off.step_values[0]["repeat_duration_controls"] is False


def test_volume_threshold_scales_from_fraction_to_percent():
    converted = _convert({DROPBOT_PLUGIN: {"volume_threshold": 0.25}})
    assert converted.step_values[0]["volume_threshold"] == 25


def test_volume_threshold_is_clamped():
    high = _convert({DROPBOT_PLUGIN: {"volume_threshold": 2.5}})
    low = _convert({DROPBOT_PLUGIN: {"volume_threshold": -1.0}})
    assert high.step_values[0]["volume_threshold"] == 100
    assert low.step_values[0]["volume_threshold"] == 0


def test_blank_label_falls_back_to_a_numbered_step_name():
    blank = _convert({STEP_LABEL_PLUGIN: {"label": ""}})
    named = _convert({STEP_LABEL_PLUGIN: {"label": "A1"}})
    assert blank.step_values[0]["name"] == "Step 1"
    assert named.step_values[0]["name"] == "A1"


def test_user_prompt_message_becomes_the_message_prompt():
    converted = _convert({USER_PROMPT_PLUGIN: {
        "message": "load sample", "schema": ""}})
    assert converted.step_values[0]["message_prompt"] == "load sample"


def test_video_enabled_maps_to_the_video_column():
    converted = _convert({DMF_DEVICE_UI_PLUGIN: {"video_enabled": True}})
    assert converted.step_values[0]["video"] is True


def test_mr_box_magnet_maps_to_the_magnet_compound():
    converted = _convert({MR_BOX_PLUGIN: {
        "Magnet": True, "Magnet_height(mm)": 0.0, "Pump": False}})
    values = converted.step_values[0]
    assert values["set_magnet"] is True
    assert values["magnet_on"] is True


def test_zika_box_magnet_wins_over_mr_box():
    converted = _convert({
        MR_BOX_PLUGIN: {"Magnet": True},
        ZIKA_BOX_PLUGIN: {"Magnet": False, "Heater": False,
                          "Heater_temperature": 20.0},
    })
    assert converted.step_values[0]["magnet_on"] is False
    assert f"{MR_BOX_PLUGIN}.Magnet" in converted.report.dropped_fields


def test_zika_box_heater_maps_to_the_temperature_compound():
    converted = _convert({ZIKA_BOX_PLUGIN: {
        "Magnet": False, "Heater": True, "Heater_temperature": 41.0}})
    values = converted.step_values[0]
    assert values["set_temperature"] is True
    assert values["target_temperature_c"] == 41.0


def test_unmappable_fields_are_reported_as_dropped():
    converted = _convert({
        MR_BOX_PLUGIN: {"Pump": False, "Measure_PMT": False},
        PLATEAU_DETECTION_PLUGIN: {"Plateau Detection": True},
    })
    dropped = converted.report.dropped_fields
    assert dropped[f"{MR_BOX_PLUGIN}.Pump"] == 1
    assert dropped[f"{PLATEAU_DETECTION_PLUGIN}.Plateau Detection"] == 1


def test_protocol_repeats_are_carried_through():
    converted = _convert({}, n_repeats=120)
    assert converted.protocol_repeats == 120


def test_report_counts_steps_and_channel_map_is_carried():
    converted = _convert({})
    assert converted.report.step_count == 1
    assert converted.electrode_to_channel == CHANNEL_MAP


# --- against the real sample folders -------------------------------------

def _sample_device_folder(folder_name):
    import os

    from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
        DEVICE_SVG_FILENAME, LEGACY_SAMPLE_DEVICE_FOLDERS, PROTOCOLS_DIR_NAME,
    )
    for folder in LEGACY_SAMPLE_DEVICE_FOLDERS:
        if os.path.basename(folder) != folder_name:
            continue
        if not os.path.isfile(os.path.join(folder, DEVICE_SVG_FILENAME)):
            break
        return (os.path.join(folder, DEVICE_SVG_FILENAME),
                os.path.join(folder, PROTOCOLS_DIR_NAME))
    pytest.skip(f"sample device folder {folder_name!r} not present")


def _convert_every_protocol_in(folder_name):
    import glob
    import os

    from pluggable_protocol_tree.services.legacy_protocol_import.device_svg_channel_map import (
        read_device_svg_channel_map,
    )
    from pluggable_protocol_tree.services.legacy_protocol_import.legacy_pickle_reader import (
        is_legacy_protocol_file, read_legacy_protocol,
    )
    svg_path, protocols_dir = _sample_device_folder(folder_name)
    channel_map = read_device_svg_channel_map(svg_path)
    converted_all = []
    for path in sorted(glob.glob(os.path.join(protocols_dir, "*"))):
        if not os.path.isfile(path) or not is_legacy_protocol_file(path):
            continue
        converted_all.append(convert_legacy_protocol(
            read_legacy_protocol(path), channel_map))
    return converted_all


def test_duo_fluo_electrodes_all_resolve():
    """Every electrode these protocols reference exists in their own device."""
    for converted in _convert_every_protocol_in("Duo Fluo v2 28x"):
        assert converted.report.unresolved_electrode_ids == {}


def test_zika_protocols_produce_routes():
    """Routes are common in this folder; a converter that silently drops them
    would otherwise look fine against Duo Fluo alone."""
    steps_with_routes = sum(
        1
        for converted in _convert_every_protocol_in("Zika-4d Mirror")
        for values in converted.step_values
        if values.get("routes"))
    assert steps_with_routes > 0


def test_quanterix_dangling_electrodes_are_reported_not_raised():
    """This device really did lose two electrodes its protocols still name."""
    unresolved = set()
    for converted in _convert_every_protocol_in("August 2022 Quanterix test"):
        unresolved.update(converted.report.unresolved_electrode_ids)
    assert {"path1651", "path1752"} <= unresolved
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_converter.py -v"`

Expected: FAIL with `ModuleNotFoundError: No module named '...protocol_converter'`

- [ ] **Step 4: Write the implementation**

Create `pluggable_protocol_tree/services/legacy_protocol_import/protocol_converter.py`:

```python
"""Map a legacy protocol onto new-format column values.

Emits plain per-step dicts keyed by new column id rather than a finished
JSON payload, so this module stays independent of which plugins happen to
be loaded. Reconciling those dicts against the live column set -- and
reporting values whose target column is absent -- happens in
``payload_builder``.
"""

from traits.api import Dict, HasTraits, Instance, Int, List

from logger.logger_service import get_logger

from .consts import (
    DMF_DEVICE_UI_PLUGIN, DROPBOT_PLUGIN, DROPLET_PLANNING_PLUGIN,
    DROPPED_LEGACY_FIELDS, DURATION_COLUMN_ID, ELECTRODE_CONTROLLER_PLUGIN,
    ELECTRODES_COLUMN_ID, FREQUENCY_COLUMN_ID, LEGACY_DROP_ROUTES_FIELD,
    LEGACY_DURATION_FIELD, LEGACY_ELECTRODE_STATES_FIELD,
    LEGACY_FREQUENCY_FIELD, LEGACY_HEATER_FIELD,
    LEGACY_HEATER_TEMPERATURE_FIELD, LEGACY_LABEL_FIELD, LEGACY_MAGNET_FIELD,
    LEGACY_MESSAGE_FIELD, LEGACY_REPEAT_DURATION_FIELD,
    LEGACY_ROUTE_ELECTRODE_COLUMN, LEGACY_ROUTE_INDEX_COLUMN,
    LEGACY_ROUTE_REPEATS_FIELD, LEGACY_ROUTE_TRANSITION_COLUMN,
    LEGACY_TRAIL_LENGTH_FIELD, LEGACY_VIDEO_ENABLED_FIELD,
    LEGACY_VOLTAGE_FIELD, LEGACY_VOLUME_THRESHOLD_FIELD, MAGNET_ON_FIELD_ID,
    MESSAGE_PROMPT_COLUMN_ID, MR_BOX_PLUGIN, NAME_COLUMN_ID,
    REPEAT_DURATION_COLUMN_ID, REPEAT_DURATION_CONTROLS_FLAG,
    ROUTE_REPETITIONS_COLUMN_ID, ROUTES_COLUMN_ID, SET_MAGNET_FIELD_ID,
    SET_TEMPERATURE_FIELD_ID, STEP_LABEL_PLUGIN,
    TARGET_TEMPERATURE_FIELD_ID, TRAIL_LENGTH_COLUMN_ID, USER_PROMPT_PLUGIN,
    VIDEO_COLUMN_ID, VOLTAGE_COLUMN_ID, VOLUME_THRESHOLD_COLUMN_ID,
    VOLUME_THRESHOLD_MAX_PERCENT, VOLUME_THRESHOLD_MIN_PERCENT,
    VOLUME_THRESHOLD_PERCENT_SCALE, ZIKA_BOX_PLUGIN,
)
from .conversion_report import ConversionReport

logger = get_logger(__name__)


class ConvertedProtocol(HasTraits):
    """Result of converting one legacy protocol, before it meets any columns."""

    step_values = List(Dict())
    protocol_repeats = Int(1)
    electrode_to_channel = Dict()
    report = Instance(ConversionReport)


def _active_electrode_ids(states, electrode_to_channel, report) -> list:
    """Electrode ids the step switches on, minus any the device no longer
    has. Real protocols do reference electrodes deleted from their SVG."""
    active = []
    for electrode_id in states.index:
        if not bool(states[electrode_id]):
            continue
        if electrode_id not in electrode_to_channel:
            report.record_unresolved_electrode(str(electrode_id))
            continue
        active.append(str(electrode_id))
    return active


def _routes_from_drop_routes(frame, electrode_to_channel, report) -> list:
    """Ordered electrode-id lists, one per ``route_i``, ordered within a
    route by ``transition_i``."""
    if frame is None or len(frame) == 0:
        return []
    routes = []
    for _, group in frame.groupby(LEGACY_ROUTE_INDEX_COLUMN, sort=True):
        ordered = group.sort_values(LEGACY_ROUTE_TRANSITION_COLUMN)
        electrode_ids = []
        for electrode_id in ordered[LEGACY_ROUTE_ELECTRODE_COLUMN]:
            if electrode_id not in electrode_to_channel:
                report.record_unresolved_electrode(str(electrode_id))
                continue
            electrode_ids.append(str(electrode_id))
        if electrode_ids:
            routes.append(electrode_ids)
    return routes


def _record_dropped_fields(plugin_data, report) -> None:
    for plugin_name, fields in DROPPED_LEGACY_FIELDS.items():
        present = plugin_data.get(plugin_name)
        if not present:
            continue
        for field in fields:
            if field in present:
                report.record_dropped(f"{plugin_name}.{field}")


def _to_percent(fraction: float) -> int:
    percent = round(float(fraction) * VOLUME_THRESHOLD_PERCENT_SCALE)
    return max(VOLUME_THRESHOLD_MIN_PERCENT,
               min(VOLUME_THRESHOLD_MAX_PERCENT, percent))


def _convert_step(step, index, electrode_to_channel, report) -> dict:
    plugin_data = step.plugin_data
    values = {}

    electrode_controller = plugin_data.get(ELECTRODE_CONTROLLER_PLUGIN, {})
    if LEGACY_VOLTAGE_FIELD in electrode_controller:
        values[VOLTAGE_COLUMN_ID] = round(
            float(electrode_controller[LEGACY_VOLTAGE_FIELD]))
    if LEGACY_FREQUENCY_FIELD in electrode_controller:
        values[FREQUENCY_COLUMN_ID] = round(
            float(electrode_controller[LEGACY_FREQUENCY_FIELD]))
    if LEGACY_DURATION_FIELD in electrode_controller:
        values[DURATION_COLUMN_ID] = float(
            electrode_controller[LEGACY_DURATION_FIELD])
    if LEGACY_ELECTRODE_STATES_FIELD in electrode_controller:
        values[ELECTRODES_COLUMN_ID] = _active_electrode_ids(
            electrode_controller[LEGACY_ELECTRODE_STATES_FIELD],
            electrode_to_channel, report)

    droplet_planning = plugin_data.get(DROPLET_PLANNING_PLUGIN, {})
    if LEGACY_DROP_ROUTES_FIELD in droplet_planning:
        values[ROUTES_COLUMN_ID] = _routes_from_drop_routes(
            droplet_planning[LEGACY_DROP_ROUTES_FIELD],
            electrode_to_channel, report)
    if LEGACY_ROUTE_REPEATS_FIELD in droplet_planning:
        values[ROUTE_REPETITIONS_COLUMN_ID] = int(
            droplet_planning[LEGACY_ROUTE_REPEATS_FIELD])
    if LEGACY_REPEAT_DURATION_FIELD in droplet_planning:
        repeat_duration = float(
            droplet_planning[LEGACY_REPEAT_DURATION_FIELD])
        values[REPEAT_DURATION_COLUMN_ID] = repeat_duration
        values[REPEAT_DURATION_CONTROLS_FLAG] = repeat_duration > 0
    if LEGACY_TRAIL_LENGTH_FIELD in droplet_planning:
        values[TRAIL_LENGTH_COLUMN_ID] = int(
            droplet_planning[LEGACY_TRAIL_LENGTH_FIELD])

    step_label = plugin_data.get(STEP_LABEL_PLUGIN, {})
    label = str(step_label.get(LEGACY_LABEL_FIELD, "") or "").strip()
    values[NAME_COLUMN_ID] = label or f"Step {index + 1}"

    user_prompt = plugin_data.get(USER_PROMPT_PLUGIN, {})
    if LEGACY_MESSAGE_FIELD in user_prompt:
        values[MESSAGE_PROMPT_COLUMN_ID] = str(
            user_prompt[LEGACY_MESSAGE_FIELD] or "")

    dropbot = plugin_data.get(DROPBOT_PLUGIN, {})
    if LEGACY_VOLUME_THRESHOLD_FIELD in dropbot:
        values[VOLUME_THRESHOLD_COLUMN_ID] = _to_percent(
            dropbot[LEGACY_VOLUME_THRESHOLD_FIELD])

    device_ui = plugin_data.get(DMF_DEVICE_UI_PLUGIN, {})
    if LEGACY_VIDEO_ENABLED_FIELD in device_ui:
        values[VIDEO_COLUMN_ID] = bool(
            device_ui[LEGACY_VIDEO_ENABLED_FIELD])

    # Magnet may come from either peripheral box. zika_box is the later,
    # more specific one, so it wins and the shadowed value is reported.
    mr_box = plugin_data.get(MR_BOX_PLUGIN, {})
    zika_box = plugin_data.get(ZIKA_BOX_PLUGIN, {})
    if LEGACY_MAGNET_FIELD in zika_box:
        values[SET_MAGNET_FIELD_ID] = True
        values[MAGNET_ON_FIELD_ID] = bool(zika_box[LEGACY_MAGNET_FIELD])
        if LEGACY_MAGNET_FIELD in mr_box:
            report.record_dropped(f"{MR_BOX_PLUGIN}.{LEGACY_MAGNET_FIELD}")
    elif LEGACY_MAGNET_FIELD in mr_box:
        values[SET_MAGNET_FIELD_ID] = True
        values[MAGNET_ON_FIELD_ID] = bool(mr_box[LEGACY_MAGNET_FIELD])

    if LEGACY_HEATER_FIELD in zika_box:
        values[SET_TEMPERATURE_FIELD_ID] = bool(zika_box[LEGACY_HEATER_FIELD])
        if LEGACY_HEATER_TEMPERATURE_FIELD in zika_box:
            values[TARGET_TEMPERATURE_FIELD_ID] = float(
                zika_box[LEGACY_HEATER_TEMPERATURE_FIELD])

    _record_dropped_fields(plugin_data, report)
    return values


def convert_legacy_protocol(protocol, electrode_to_channel: dict):
    """Convert every step of ``protocol`` into new-format column values.

    A step that fails to convert is emitted empty (so it keeps its position
    in the sequence) and recorded in the report -- one bad step must not
    abort a 177-step protocol."""
    report = ConversionReport(step_count=len(protocol.steps))
    step_values = []
    for index, step in enumerate(protocol.steps):
        try:
            values = _convert_step(step, index, electrode_to_channel, report)
        except Exception as e:
            logger.warning(
                f"step {index + 1} of {protocol.name!r} failed to convert: "
                f"{e}", exc_info=True)
            report.record_step_failure(f"Step {index + 1}: {e}")
            values = {NAME_COLUMN_ID: f"Step {index + 1}"}
        for column_id in values:
            report.record_mapped(column_id)
        step_values.append(values)
    return ConvertedProtocol(
        step_values=step_values,
        protocol_repeats=int(protocol.n_repeats or 1),
        electrode_to_channel=dict(electrode_to_channel),
        report=report,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_converter.py -v"`

Expected: PASS (21 tests; the last three skip when the sample folders are absent)

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/services/legacy_protocol_import/ pluggable_protocol_tree/tests/test_protocol_converter.py
git commit -m "feat: map legacy protocol steps to column values"
```

---

### Task 6: Payload builder

**Files:**
- Create: `pluggable_protocol_tree/services/legacy_protocol_import/payload_builder.py`
- Modify: `pluggable_protocol_tree/services/legacy_protocol_import/__init__.py` (re-export the public entry points)
- Test: `pluggable_protocol_tree/tests/test_legacy_payload_builder.py`

**Interfaces:**
- Consumes: `ConvertedProtocol` from Task 5; `RowManager` from `pluggable_protocol_tree.models.row_manager`; `ELECTRODE_TO_CHANNEL_KEY` from `pluggable_protocol_tree.consts`.
- Produces: `build_protocol_payload(converted, columns: list) -> dict` — a payload identical in shape to `RowManager.to_json()`, ready for `validate_protocol` and `set_state_from_json`. Mutates `converted.report` to record values whose target column is not in `columns`.
- `__init__.py` re-exports: `read_legacy_protocol`, `is_legacy_protocol_file`, `read_device_svg_channel_map`, `scan_for_device_folders`, `LegacyDeviceFolder`, `convert_legacy_protocol`, `build_protocol_payload`, `ConversionReport`.

**Background the implementer needs:**

This is where the converter's plugin-independent dicts meet reality. `RowManager(columns=...)` builds a dynamic row type carrying one Traits attribute per active column (and per compound field). So:

- `RowManager.add_step(values=...)` sets attributes by name. Passing a key the row type does not have raises, so **filter first** using `hasattr` on a probe row, and record every filtered key as dropped. That is exactly how "the heater plugin is not loaded" surfaces to the user.
- `repeat_duration_controls` is a row-level flag, not a column. Pop it from the values dict and set it on the row after creation.
- `protocol_metadata[ELECTRODE_TO_CHANNEL_KEY]` holds the device map.
- `RowManager.add_step` returns the new row's path; `manager.get_row(path)` retrieves the row object. `add_group(name=...)` likewise returns a path, and `add_step(parent_path=...)` nests under it.
- **`n_repeats` must NOT be written to `manager.root`.** The root has no `repetitions` attribute (verified: `hasattr(manager.root, "repetitions")` is `False`), and `serialize_tree` walks with `skip_root=True`, so anything set there is silently discarded. When `n_repeats > 1`, wrap every step in one explicit `add_group(name=...)` and set `repetitions` on *that* group — it serializes as a depth-0 `group` row with the steps at depth 1. When `n_repeats` is 1, add the steps flat, matching the legacy shape.

- [ ] **Step 1: Write the failing test**

Create `pluggable_protocol_tree/tests/test_legacy_payload_builder.py`:

```python
"""Turning converted step values into a loadable protocol payload."""
import pandas as pd

from pluggable_protocol_tree.consts import ELECTRODE_TO_CHANNEL_KEY
from pluggable_protocol_tree.services.legacy_protocol_import.legacy_pickle_reader import (
    LegacyProtocol, LegacyStep,
)
from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    ELECTRODE_CONTROLLER_PLUGIN, STEP_LABEL_PLUGIN, ZIKA_BOX_PLUGIN,
)
from pluggable_protocol_tree.services.legacy_protocol_import.payload_builder import (
    build_protocol_payload,
)
from pluggable_protocol_tree.services.legacy_protocol_import.protocol_converter import (
    convert_legacy_protocol,
)
from pluggable_protocol_tree.services.protocol_validator import validate_protocol

CHANNEL_MAP = {"e0": 0, "e1": 1}


def _builtin_columns():
    """The builtin column set — what is available with no optional plugins
    loaded. Built from the per-column factories the way the existing
    persistence tests do (see tests/test_persistence.py::columns)."""
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


def _converted(plugin_data, n_repeats=1):
    protocol = LegacyProtocol(name="p", version="0.2.0", n_repeats=n_repeats,
                              steps=[LegacyStep(plugin_data)])
    return convert_legacy_protocol(protocol, CHANNEL_MAP)


def test_payload_has_the_persistence_shape():
    payload = build_protocol_payload(
        _converted({STEP_LABEL_PLUGIN: {"label": "A1"}}), _builtin_columns())
    for key in ("schema_version", "protocol_metadata", "row_flags",
                "columns", "fields", "rows"):
        assert key in payload


def test_steps_land_in_the_payload_with_their_names():
    protocol = LegacyProtocol(
        name="p", version="0.2.0", n_repeats=1,
        steps=[LegacyStep({STEP_LABEL_PLUGIN: {"label": "A1"}}),
               LegacyStep({STEP_LABEL_PLUGIN: {"label": "B2"}})])
    payload = build_protocol_payload(
        convert_legacy_protocol(protocol, CHANNEL_MAP), _builtin_columns())
    name_index = payload["fields"].index("name")
    assert [row[name_index] for row in payload["rows"]] == ["A1", "B2"]


def test_electrode_map_is_stored_in_protocol_metadata():
    payload = build_protocol_payload(_converted({}), _builtin_columns())
    assert payload["protocol_metadata"][ELECTRODE_TO_CHANNEL_KEY] == CHANNEL_MAP


def test_electrodes_survive_the_round_trip():
    states = pd.Series({"e0": True, "e1": False})
    payload = build_protocol_payload(
        _converted({ELECTRODE_CONTROLLER_PLUGIN: {"electrode_states": states}}),
        _builtin_columns())
    electrodes_index = payload["fields"].index("electrodes")
    assert payload["rows"][0][electrodes_index] == ["e0"]


def test_repeat_duration_controls_becomes_a_row_flag_not_a_column():
    from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
        DROPLET_PLANNING_PLUGIN,
    )
    payload = build_protocol_payload(
        _converted({DROPLET_PLANNING_PLUGIN: {"repeat_duration_s": 5}}),
        _builtin_columns())
    assert "repeat_duration_controls" not in payload["fields"]
    flags = list(payload["row_flags"].values())
    assert flags and flags[0]["repeat_duration_controls"] is True


def test_values_without_a_live_column_are_reported_as_dropped():
    """The heater column ships with an optional plugin. With only builtin
    columns loaded, its values have nowhere to go and must be reported."""
    converted = _converted({ZIKA_BOX_PLUGIN: {
        "Magnet": False, "Heater": True, "Heater_temperature": 41.0}})
    build_protocol_payload(converted, _builtin_columns())
    assert "set_temperature" in converted.report.dropped_fields


def test_repeated_protocol_gets_a_wrapper_group_carrying_the_repeats():
    """n_repeats cannot live on the root -- the root has no repetitions
    attribute and is skipped during serialization -- so it needs a real
    group row."""
    payload = build_protocol_payload(_converted({}, n_repeats=120),
                                     _builtin_columns())
    type_index = payload["fields"].index("type")
    repetitions_index = payload["fields"].index("repetitions")
    depth_index = payload["fields"].index("depth")
    group_rows = [row for row in payload["rows"]
                  if row[type_index] == "group"]
    assert len(group_rows) == 1
    assert group_rows[0][repetitions_index] == 120
    assert group_rows[0][depth_index] == 0
    step_rows = [row for row in payload["rows"] if row[type_index] == "step"]
    assert all(row[depth_index] == 1 for row in step_rows)


def test_unrepeated_protocol_stays_flat():
    payload = build_protocol_payload(_converted({}, n_repeats=1),
                                     _builtin_columns())
    type_index = payload["fields"].index("type")
    assert all(row[type_index] == "step" for row in payload["rows"])


def test_payload_validates_cleanly_against_the_same_device():
    converted = _converted({STEP_LABEL_PLUGIN: {"label": "A1"}})
    columns = _builtin_columns()
    payload = build_protocol_payload(converted, columns)
    report = validate_protocol(payload, columns, CHANNEL_MAP)
    assert report.is_empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_legacy_payload_builder.py -v"`

Expected: FAIL with `ModuleNotFoundError: No module named '...payload_builder'`

**Note for the implementer:** there is no aggregate "all builtin columns" helper in this codebase — the existing tests assemble column lists from the per-column `make_*_column()` factories (see the `columns` fixture at `pluggable_protocol_tree/tests/test_persistence.py:19`). `_builtin_columns()` above follows that pattern. Do not add a new aggregate helper.

- [ ] **Step 3: Write the implementation**

Create `pluggable_protocol_tree/services/legacy_protocol_import/payload_builder.py`:

```python
"""Reconcile converted legacy values against the live column set.

The converter deliberately knows nothing about which plugins are loaded,
so this is where its plain dicts meet the dynamic row type. A value whose
target column is absent -- a heater setpoint with the heater plugin
unloaded, say -- is recorded as dropped rather than raising.
"""

from pluggable_protocol_tree.consts import ELECTRODE_TO_CHANNEL_KEY
from pluggable_protocol_tree.models.row_manager import RowManager

from logger.logger_service import get_logger

from .consts import (
    IMPORTED_PROTOCOL_GROUP_NAME, REPEAT_DURATION_CONTROLS_FLAG,
    REPETITIONS_COLUMN_ID,
)

logger = get_logger(__name__)


def _settable_attribute_names(manager) -> set:
    """Attribute names the current dynamic step type actually carries.

    A legacy value whose name is missing here has no column in this build --
    e.g. a heater setpoint with the heater plugin unloaded."""
    return set(manager.step_type().trait_names())


def _repeats_group_path(manager, converted):
    """Path the steps should be added under.

    ``n_repeats`` cannot live on the root: the root carries no
    ``repetitions`` attribute and ``serialize_tree`` skips it, so the value
    would vanish. A repeated protocol therefore gets one wrapper group that
    does serialize; an unrepeated one stays flat, matching the legacy shape."""
    if converted.protocol_repeats <= 1:
        return ()
    group_path = manager.add_group(name=IMPORTED_PROTOCOL_GROUP_NAME)
    group_row = manager.get_row(group_path)
    if hasattr(group_row, REPETITIONS_COLUMN_ID):
        setattr(group_row, REPETITIONS_COLUMN_ID, converted.protocol_repeats)
    else:
        converted.report.record_dropped(REPETITIONS_COLUMN_ID)
    return group_path


def build_protocol_payload(converted, columns: list) -> dict:
    """Build a payload in ``RowManager.to_json()`` shape from ``converted``.

    Records every value with no matching column on ``converted.report``, so
    the summary dialog can tell the user what their build could not hold."""
    manager = RowManager(columns=list(columns))
    settable = _settable_attribute_names(manager)
    parent_path = _repeats_group_path(manager, converted)

    for values in converted.step_values:
        values = dict(values)
        repeat_duration_controls = values.pop(
            REPEAT_DURATION_CONTROLS_FLAG, None)
        applicable = {}
        for column_id, value in values.items():
            if column_id in settable:
                applicable[column_id] = value
            else:
                converted.report.record_dropped(column_id)
        path = manager.add_step(parent_path=parent_path, values=applicable)
        if repeat_duration_controls:
            manager.get_row(path).repeat_duration_controls = True

    manager.protocol_metadata[ELECTRODE_TO_CHANNEL_KEY] = dict(
        converted.electrode_to_channel)
    return manager.to_json()
```

Add to `pluggable_protocol_tree/services/legacy_protocol_import/consts.py`:

```python
# --- name of the wrapper group that carries a repeated protocol's n_repeats ---
IMPORTED_PROTOCOL_GROUP_NAME = "Imported protocol"
```

Then replace `pluggable_protocol_tree/services/legacy_protocol_import/__init__.py` with:

```python
"""Import protocols authored in the Python 2 MicroDrop."""

from .conversion_report import ConversionReport
from .device_folder_scanner import LegacyDeviceFolder, scan_for_device_folders
from .device_svg_channel_map import read_device_svg_channel_map
from .legacy_pickle_reader import is_legacy_protocol_file, read_legacy_protocol
from .payload_builder import build_protocol_payload
from .protocol_converter import convert_legacy_protocol

__all__ = [
    "ConversionReport",
    "LegacyDeviceFolder",
    "build_protocol_payload",
    "convert_legacy_protocol",
    "is_legacy_protocol_file",
    "read_device_svg_channel_map",
    "read_legacy_protocol",
    "scan_for_device_folders",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_legacy_payload_builder.py -v"`

Expected: PASS (9 tests)

- [ ] **Step 5: Run every service test together**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_legacy_pickle_reader.py pluggable_protocol_tree/tests/test_device_svg_channel_map.py pluggable_protocol_tree/tests/test_device_folder_scanner.py pluggable_protocol_tree/tests/test_protocol_converter.py pluggable_protocol_tree/tests/test_legacy_payload_builder.py -v"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/services/legacy_protocol_import/ pluggable_protocol_tree/tests/test_legacy_payload_builder.py
git commit -m "feat: build protocol payload from converted steps"
```

---

### Task 7: Import dialog

**Files:**
- Create: `pluggable_protocol_tree/views/legacy_import_dialog.py`
- No tests — the GUI is verified manually (see Global Constraints).

**Interfaces:**
- Consumes: `scan_for_device_folders`, `LegacyDeviceFolder` from Task 3.
- Produces:
  - `class LegacyImportDialogModel(HasTraits)`: traits `root_path: Str`, `device_folders: List(Instance(LegacyDeviceFolder))`, `selected_device_index: Int`, `selected_protocol_index: Int`, `device_svg_path: Str`, `protocol_path: Str`
  - `class LegacyImportDialog(QDialog)`: constructor `LegacyImportDialog(parent=None, initial_root_path="")`; method `selected_paths() -> tuple[str, str]` returning `(device_svg_path, protocol_path)`; standard `QDialog` accept/reject.

**Background the implementer needs:**

Model/view separation as used elsewhere in this codebase: the model is `HasTraits` and Qt-free, holding the selections; the view is PySide6 and observes the model to rebuild its dropdowns. Only the view imports Qt.

Selecting a device repopulates the protocol dropdown and rewrites both path fields. Editing a path field directly overrides the dropdown, so files kept outside a standard Device Folder still import.

Default root path: the user's `Documents/MicroDrop` if it exists, otherwise empty.

Use `QFileDialog.getExistingDirectory` for the Browse button — `protocol_tree_pane.py` already uses `QFileDialog` directly for its file dialogs, so this follows the established pattern. Never call `exec()` on a dialog in this codebase; the dialog is shown by the caller.

- [ ] **Step 1: Write the model**

Create `pluggable_protocol_tree/views/legacy_import_dialog.py` starting with the Qt-free model:

```python
"""Dialog for picking a legacy MicroDrop device and protocol to import.

Model/view split as elsewhere in this package: ``LegacyImportDialogModel``
is Qt-free and holds the selections; ``LegacyImportDialog`` observes it and
rebuilds its dropdowns. Editing a path field directly overrides the
dropdowns, so protocols kept outside a standard Device Folder still import.
"""

import os

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout,
)
from traits.api import HasTraits, Instance, Int, List, Str, observe

from logger.logger_service import get_logger

from pluggable_protocol_tree.services.legacy_protocol_import import (
    LegacyDeviceFolder, scan_for_device_folders,
)

logger = get_logger(__name__)

DEFAULT_MICRODROP_DIR_NAME = "MicroDrop"
DEFAULT_DOCUMENTS_DIR_NAME = "Documents"
NO_SELECTION_INDEX = -1


def default_legacy_root_path() -> str:
    """``~/Documents/MicroDrop`` when it exists, else an empty string."""
    candidate = os.path.join(
        os.path.expanduser("~"), DEFAULT_DOCUMENTS_DIR_NAME,
        DEFAULT_MICRODROP_DIR_NAME)
    return candidate if os.path.isdir(candidate) else ""


class LegacyImportDialogModel(HasTraits):
    """Selection state for the legacy import dialog."""

    root_path = Str()
    device_folders = List(Instance(LegacyDeviceFolder))
    selected_device_index = Int(NO_SELECTION_INDEX)
    selected_protocol_index = Int(NO_SELECTION_INDEX)
    device_svg_path = Str()
    protocol_path = Str()

    @observe("root_path")
    def _rescan_devices(self, event=None):
        self.device_folders = scan_for_device_folders(self.root_path)
        self.selected_device_index = (
            0 if self.device_folders else NO_SELECTION_INDEX)

    @observe("selected_device_index")
    def _apply_device_selection(self, event=None):
        device = self.selected_device()
        self.device_svg_path = device.device_svg_path if device else ""
        self.selected_protocol_index = (
            0 if device and device.protocol_paths else NO_SELECTION_INDEX)

    @observe("selected_protocol_index")
    def _apply_protocol_selection(self, event=None):
        device = self.selected_device()
        if device is None or self.selected_protocol_index < 0:
            self.protocol_path = ""
            return
        if self.selected_protocol_index < len(device.protocol_paths):
            self.protocol_path = device.protocol_paths[
                self.selected_protocol_index]

    def selected_device(self):
        if 0 <= self.selected_device_index < len(self.device_folders):
            return self.device_folders[self.selected_device_index]
        return None

    def protocol_names(self) -> list:
        device = self.selected_device()
        if device is None:
            return []
        return [os.path.basename(path) for path in device.protocol_paths]
```

- [ ] **Step 2: Write the view**

Append to the same file:

```python
class LegacyImportDialog(QDialog):
    """Root directory -> device -> protocol, with editable path overrides."""

    def __init__(self, parent=None, initial_root_path=""):
        super().__init__(parent)
        self.setWindowTitle("Import Legacy Protocol")
        self.model = LegacyImportDialogModel()
        self._build_widgets()
        self._connect_widgets()
        self.model.observe(self._refresh_devices, "device_folders")
        self.model.observe(self._refresh_protocols, "selected_device_index")
        self.model.observe(self._refresh_paths,
                           "device_svg_path,protocol_path")
        self.model.root_path = initial_root_path or default_legacy_root_path()
        self._root_edit.setText(self.model.root_path)

    def _build_widgets(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._root_edit = QLineEdit()
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse)
        root_row = QHBoxLayout()
        root_row.addWidget(self._root_edit)
        root_row.addWidget(browse_button)
        form.addRow("MicroDrop folder:", root_row)

        self._device_combo = QComboBox()
        form.addRow("Device:", self._device_combo)

        self._protocol_combo = QComboBox()
        form.addRow("Protocol:", self._protocol_combo)

        self._device_svg_edit = QLineEdit()
        form.addRow("Device SVG:", self._device_svg_edit)

        self._protocol_path_edit = QLineEdit()
        form.addRow("Protocol file:", self._protocol_path_edit)

        layout.addLayout(form)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        self._buttons.button(QDialogButtonBox.Ok).setText("Import")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _connect_widgets(self):
        self._root_edit.editingFinished.connect(
            lambda: setattr(self.model, "root_path", self._root_edit.text()))
        self._device_combo.currentIndexChanged.connect(
            lambda index: setattr(self.model, "selected_device_index", index))
        self._protocol_combo.currentIndexChanged.connect(
            lambda index: setattr(
                self.model, "selected_protocol_index", index))
        self._device_svg_edit.editingFinished.connect(
            lambda: setattr(self.model, "device_svg_path",
                            self._device_svg_edit.text()))
        self._protocol_path_edit.editingFinished.connect(
            lambda: setattr(self.model, "protocol_path",
                            self._protocol_path_edit.text()))

    def _on_browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Select MicroDrop or device folder", self.model.root_path)
        if chosen:
            self._root_edit.setText(chosen)
            self.model.root_path = chosen

    def _refresh_devices(self, event=None):
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        self._device_combo.addItems(
            [device.name for device in self.model.device_folders])
        self._device_combo.setCurrentIndex(self.model.selected_device_index)
        self._device_combo.blockSignals(False)
        self._refresh_protocols()

    def _refresh_protocols(self, event=None):
        self._protocol_combo.blockSignals(True)
        self._protocol_combo.clear()
        self._protocol_combo.addItems(self.model.protocol_names())
        self._protocol_combo.setCurrentIndex(
            self.model.selected_protocol_index)
        self._protocol_combo.blockSignals(False)

    def _refresh_paths(self, event=None):
        self._device_svg_edit.setText(self.model.device_svg_path)
        self._protocol_path_edit.setText(self.model.protocol_path)

    def selected_paths(self):
        """``(device_svg_path, protocol_path)`` as currently shown, so a
        hand-edited path wins over the dropdown selection."""
        return (self._device_svg_edit.text().strip(),
                self._protocol_path_edit.text().strip())
```

- [ ] **Step 3: Verify it imports and constructs headless**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c 'from PySide6.QtWidgets import QApplication; app = QApplication([]); from pluggable_protocol_tree.views.legacy_import_dialog import LegacyImportDialog; d = LegacyImportDialog(); print(\"constructed\", d.selected_paths())'"`

Expected: prints `constructed ('', '')` (or real paths if a MicroDrop folder exists)

- [ ] **Step 4: Commit**

```bash
git add pluggable_protocol_tree/views/legacy_import_dialog.py
git commit -m "feat: add legacy protocol import dialog"
```

---

### Task 8: Device-load request topic

**Files:**
- Modify: `device_viewer/consts.py` (add the topic, subscribe it)
- Modify: `device_viewer/views/device_view_dock_pane.py` (add the handler)
- No tests — verified through Task 9's manual check.

**Interfaces:**
- Produces: `DEVICE_VIEWER_LOAD_SVG_REQUEST = "ui/device_viewer/load_svg_request"` in `device_viewer/consts.py`, handled by `DeviceViewDockPane._on_load_svg_request_triggered(message)` where `message` is the SVG path.

**Why this task exists:**

The import offers to load the legacy `device.svg` when it does not match the loaded device. There is currently **no decoupled way to ask the Device viewer to load an SVG** — `device_viewer` publishes `DEVICE_VIEWER_GEOMETRY_CHANGED` but subscribes to nothing that loads a device, and reaching into its dock pane from `pluggable_protocol_tree` is forbidden. So the Device viewer must expose a request topic.

`GAMEPAD_CAPTURE_REQUEST` (`device_viewer/consts.py:53`, handled at `device_view_dock_pane.py:247`) is the exact precedent: a `ui/device_viewer/*_request` topic in `ACTOR_TOPIC_DICT`, dispatched by the last topic segment to `_on_<segment>_triggered`. Follow it.

**Important dispatch constraint:** the Dramatiq listener base dispatches on `topic.split("/")[-1]`, so the last segment must be unique across every topic the plugin subscribes to. `load_svg_request` does not collide with anything in the current `ACTOR_TOPIC_DICT` — verify that still holds before committing.

- [ ] **Step 1: Add the topic constant**

In `device_viewer/consts.py`, beside the other `ui/device_viewer/*_request` topics (near `GAMEPAD_CAPTURE_REQUEST` at line 53), add:

```python
# Ask the Device viewer to load an SVG. Lets other plugins (e.g. the legacy
# protocol import) switch devices without reaching into this one.
DEVICE_VIEWER_LOAD_SVG_REQUEST = "ui/device_viewer/load_svg_request"
```

- [ ] **Step 2: Subscribe the topic**

In the same file, add `DEVICE_VIEWER_LOAD_SVG_REQUEST,` to the `listener_name` list inside `ACTOR_TOPIC_DICT`, next to `GAMEPAD_CAPTURE_REQUEST`.

- [ ] **Step 3: Add the handler**

In `device_viewer/views/device_view_dock_pane.py`, beside `_on_gamepad_capture_request_triggered` (around line 247), add:

```python
    def _on_load_svg_request_triggered(self, message):
        """Load the SVG at ``message`` (a file path) into the device view.

        Lets another plugin switch devices over pub/sub instead of reaching
        into this pane."""
        svg_path = str(message or "").strip()
        if not svg_path or not os.path.isfile(svg_path):
            logger.warning(f"load-svg request for missing file: {svg_path!r}")
            return
        try:
            self._set_device_view_from_svg(svg_path)
        except Exception as e:
            logger.warning(
                f"could not load requested device svg {svg_path!r}: {e}",
                exc_info=True)
```

Check that `os` is already imported at the top of the file; add it only if it is not. Confirm the exact name of the SVG-loading method by reading `load_svg_dialog` (around line 1070) — it calls `_set_device_view_from_svg(src_file)`; use whatever that method is actually called in the current file rather than trusting this snippet.

- [ ] **Step 4: Verify the topic dispatches uniquely**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c '
from device_viewer.consts import ACTOR_TOPIC_DICT
segments = [t.split(\"/\")[-1] for topics in ACTOR_TOPIC_DICT.values() for t in topics]
duplicates = {s for s in segments if segments.count(s) > 1}
print(\"duplicate final segments:\", duplicates or \"none\")
assert not duplicates
'"`

Expected: prints `duplicate final segments: none`

- [ ] **Step 5: Commit**

```bash
git add device_viewer/consts.py device_viewer/views/device_view_dock_pane.py
git commit -m "feat: add device SVG load request topic"
```

---

### Task 9: Menu action and import flow

**Files:**
- Modify: `pluggable_protocol_tree/menus.py` (add factory, add to `protocol_menu_factory`)
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py` (add `import_legacy_protocol_dialog`)
- Modify: `pluggable_protocol_tree/views/dock_pane.py:1058` area (add the delegating method)
- No tests — the GUI is verified manually.

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: menu item `Protocol > &Import Legacy Protocol...` bound to `PluggableProtocolDockPane.import_legacy_protocol_dialog`.

**Background the implementer needs:**

Read `pluggable_protocol_tree/views/protocol_tree_pane.py:533-570` (`load_from_dialog`) and `:646-656` (`load_protocol_dialog`) before starting — the import method follows them closely and reuses `validate_protocol`, `confirm_report`, and `set_state_from_json`.

Existing helpers on the pane, all already imported there: `self._confirm_proceed_or_abort()`, `self.manager`, `self.device_viewer_sync`, `self.protocol_state_tracker`, the `@attempt_func_execution_with_error_dialog` decorator, and `confirm` / `error` / `information` / `YES` from the pyface wrapper. Check the existing import block at the top of the file and extend it rather than adding a parallel one.

The import deliberately does **not** write a file and does **not** call `protocol_state_tracker.set_loaded(...)` or `reseed_baseline(...)` — the converted protocol must stay dirty and unsaved so the user reviews it and chooses `Save As`.

Loading the legacy device goes through the `DEVICE_VIEWER_LOAD_SVG_REQUEST` topic added in Task 8, published with `publish_message(topic=..., message=svg_path)`. Importing that topic constant from `device_viewer.consts` is allowed — constants are the pub/sub contract. Importing any `device_viewer` *class* is not.

`dialog.exec()` on a custom `QDialog` is the established pattern in this package (`pluggable_protocol_tree/views/tree_widget.py:561` does exactly `if dialog.exec() != QDialog.Accepted:`). The "never use `exec()`" convention targets the pyface message dialogs, which have their own `show()`-based wrappers.

- [ ] **Step 1: Add the menu action factory**

In `pluggable_protocol_tree/menus.py`, add after `load_dialog_factory`:

```python
def import_legacy_dialog_factory():
    return DockPaneAction(
        id=f"{PKG}.import_legacy_protocol_dialog",
        dock_pane_id=_DOCK_PANE_ID,
        name="&Import Legacy Protocol...",
        method="import_legacy_protocol_dialog",
    )
```

and add `import_legacy_dialog_factory(),` to `protocol_menu_factory()`'s `SMenu(...)` arguments, immediately after `load_dialog_factory(),`.

Update the module docstring's first line to read:

```python
"""DockPaneAction factories for the pluggable protocol tree's
``&Protocol`` file menu (New / Load / Import Legacy / Save / Save As).
```

- [ ] **Step 2: Add the delegating method on the dock pane**

In `pluggable_protocol_tree/views/dock_pane.py`, in the `--- &Protocol menu action delegates ---` block, add after `load_protocol_dialog`:

```python
    def import_legacy_protocol_dialog(self):
        self._pane.import_legacy_protocol_dialog()
```

- [ ] **Step 3: Add the import flow on the pane**

In `pluggable_protocol_tree/views/protocol_tree_pane.py`, add to the `--- file menu actions ---` section, after `load_protocol_dialog`:

```python
    @attempt_func_execution_with_error_dialog
    def import_legacy_protocol_dialog(self):
        """Convert a Python 2 MicroDrop protocol into this tree.

        The result is left unsaved on purpose: the user reviews the
        conversion report, then chooses Save As."""
        if not self._confirm_proceed_or_abort():
            return
        dialog = LegacyImportDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        device_svg_path, protocol_path = dialog.selected_paths()
        if not device_svg_path or not protocol_path:
            error(parent=self, title="Import error",
                  message="Select both a device SVG and a protocol file.")
            return

        try:
            electrode_to_channel = read_device_svg_channel_map(
                device_svg_path)
        except Exception as e:
            error(parent=self, title="Import error",
                  message=f"Could not read {device_svg_path}:\n{e}")
            return
        if not electrode_to_channel:
            error(parent=self, title="Import error",
                  message=f"{device_svg_path} contains no electrodes with "
                          f"channel assignments.")
            return

        if not self._confirm_legacy_device_match(
                electrode_to_channel, device_svg_path):
            return

        try:
            legacy_protocol = read_legacy_protocol(protocol_path)
        except Exception as e:
            error(parent=self, title="Import error",
                  message=f"Could not read {protocol_path}:\n{e}")
            return

        converted = convert_legacy_protocol(
            legacy_protocol, electrode_to_channel)
        columns = list(self.manager.columns)
        payload = build_protocol_payload(converted, columns)

        # The legacy device's own map is authoritative for this protocol, and
        # a device load requested above has not landed yet.
        report = validate_protocol(payload, columns, electrode_to_channel)
        if not report.is_empty:
            if confirm_report(report, parent=self) != YES:
                return
        self.manager.set_state_from_json(
            payload, columns=columns, report_findings=False)

        information(parent=self, title="Legacy protocol imported",
                    message=converted.report.render())

    def _confirm_legacy_device_match(self, electrode_to_channel,
                                     device_svg_path) -> bool:
        """True when the import should proceed.

        A protocol stores electrode *ids*, so a mismatched device makes the
        import meaningless. Offers to switch the Device viewer to the legacy
        device over pub/sub; YES loads it, NO imports anyway (dropping the
        unknown electrodes), CANCEL aborts."""
        if self.device_viewer_sync is None:
            return True
        loaded = set(self.device_viewer_sync.electrode_ids_channels_map)
        if not loaded:
            return True
        unknown = set(electrode_to_channel) - loaded
        if not unknown:
            return True
        choice = confirm(
            self,
            f"The loaded device does not have {len(unknown)} of the legacy "
            f"device's electrodes.\n\n"
            f"Load {os.path.basename(device_svg_path)} into the Device "
            f"viewer first?\n\n"
            f"Choosing No imports anyway and drops the unknown electrodes.",
            title="Device mismatch",
            cancel=True,
        )
        if choice == CANCEL:
            return False
        if choice == YES:
            publish_message(topic=DEVICE_VIEWER_LOAD_SVG_REQUEST,
                            message=device_svg_path)
        return True
```

Call it as `self._confirm_legacy_device_match(electrode_to_channel, device_svg_path)`.

**Why validation uses the legacy map, not the live one:** the device load is asynchronous — `publish_message` returns before the Device viewer has swapped devices, so `device_viewer_sync.electrode_ids_channels_map` would still be the *old* map when `validate_protocol` runs a few lines later, producing spurious unknown-electrode findings. The `import_legacy_protocol_dialog` snippet above therefore passes `electrode_to_channel` (the legacy device's own map, authoritative for this protocol) unconditionally, which is also correct when the devices already match.

- [ ] **Step 4: Add the imports**

At the top of `pluggable_protocol_tree/views/protocol_tree_pane.py`, extend the existing import blocks rather than adding parallel ones. Add `QDialog` to the existing `PySide6.QtWidgets` import; add `CANCEL`, `error` and `information` to the existing `pyface_wrapper` import if absent (`confirm` and `YES` are already there); ensure `os` is imported; and add:

```python
from device_viewer.consts import DEVICE_VIEWER_LOAD_SVG_REQUEST
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from pluggable_protocol_tree.services.legacy_protocol_import import (
    build_protocol_payload, convert_legacy_protocol,
    read_device_svg_channel_map, read_legacy_protocol,
)
from pluggable_protocol_tree.views.legacy_import_dialog import (
    LegacyImportDialog,
)
```

- [ ] **Step 5: Verify the menu builds and the pane imports**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.menus import protocol_menu_factory; menu = protocol_menu_factory(); print([item.name for item in menu.items])' && python -c 'import pluggable_protocol_tree.views.protocol_tree_pane; print(\"pane imports\")'"`

Expected: prints a list containing `&Import Legacy Protocol...`, then `pane imports`

- [ ] **Step 6: Run the existing menu test**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_menus.py -v"`

Expected: PASS. If it asserts an exact list of menu item names, update that assertion to include the new item — that is an intended change, not a regression.

- [ ] **Step 7: Commit**

```bash
git add pluggable_protocol_tree/menus.py pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/views/dock_pane.py pluggable_protocol_tree/tests/test_menus.py
git commit -m "feat: add Import Legacy Protocol menu action"
```

- [ ] **Step 8: Manual verification**

Launch the app and check:

1. `Protocol > Import Legacy Protocol...` appears between `Load` and `Save`.
2. Pointing the dialog at `C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/legacy_protocols` lists three devices.
3. Selecting `Duo Fluo v2 28x` lists 8 protocols and does **not** list `Sci-Bots-Quanterix-Device.7z` under the Quanterix device.
4. Importing `Feb6` yields 11 steps with voltage 120, frequency 10000, and electrodes populated.
5. Importing a Zika protocol such as `NASBA_2 lane_v1_Zika 3x3` yields populated routes.
6. The conversion report names the dropped `mr_box_plugin` and `plateau_detection_plugin` fields.
7. The tree is marked unsaved, and `Save As` writes a JSON that reloads via `Protocol > Load`.
8. With a *different* device loaded, importing warns about the mismatch. Choosing Yes switches the Device viewer to the legacy device (Task 8's topic); choosing No imports anyway and the report lists the dropped electrodes; choosing Cancel aborts with the tree untouched.
9. Importing `droplet movement` (whose `n_repeats` is 120) yields one group named "Imported protocol" with Reps 120 and its steps nested inside.
10. Importing a Zika protocol with the heater plugin *disabled* still succeeds, and the report lists `set_temperature` / `target_temperature_c` as dropped.
