# Import legacy MicroDrop protocols (issue #438)

Convert protocols authored in the Python 2 MicroDrop (`github.com/sci-bots/microdrop`)
into `pluggable_protocol_tree` protocols, via a `Protocol > Import Legacy Protocol...`
menu action that lets the user browse an old MicroDrop directory, pick a device, and
pick one of that device's protocols.

## 1. Background: what the legacy data actually is

An old MicroDrop *Device Folder* looks like:

```
<MicroDrop dir>/devices/<Device Name>/
    device.svg
    protocols/
        <protocol name>            # no extension, a Python 2 pickle
        ...
    logs/
```

Each protocol file is a `pickle` (protocol 2) of `microdrop.protocol.Protocol`:

```python
Protocol(
    name: str,
    version: str,          # "0.2.0" in every sample examined
    n_repeats: int,        # whole-protocol repeat count
    plugin_fields: dict,   # plugin name -> list of field names it declares
    plugin_data: dict,     # always {} at protocol level in the samples
    steps: [Step, ...],
)
Step(plugin_data: dict)    # plugin name -> a *nested* pickle blob (bytes/str)
```

`Step.plugin_data` values are themselves pickled dicts, so unpickling is two levels
deep. Steps are a **flat list** — the legacy format has no groups or nesting.

### 1.1 Evidence base

Every claim in this spec was checked against the four device folders available locally
(57 protocol files, ~3,400 steps total):

| Device folder | Protocols | Steps |
|---|---|---|
| `scratches/legacy_protocols/August 2022 Quanterix test` | 31 | ~1,600 |
| `scratches/legacy_protocols/Duo Fluo v2 28x` | 8 | 533 |
| `scratches/legacy_protocols/Zika-4d Mirror` | 17 | ~500 |
| `Documents/MicroDrop/devices/DMF-90-pin-array` | 1 | 3 |

All are `version 0.2.0`. Eight legacy plugins appear across them.

### 1.2 Electrode identity — why the device is required

`electrode_states` is a `pandas.Series` whose **index is the SVG element id** of each
electrode (`path609`, `electrode053`) and whose values are booleans. The id namespace
is device-specific and the two id conventions above both occur in real files, so a
protocol is only meaningful alongside the `device.svg` it was authored against.

This lines up well with the new system: `pluggable_protocol_tree` also keys electrodes
by id string (`electrodes: List[str]`, `routes: List[List[str]]`) and resolves ids to
hardware channels at run time. Both old and new device SVGs annotate each `<path>` with
`data-channels`. Verified: all 119 electrode ids used by the Duo Fluo protocols and all
78 used by the Zika protocols resolve against their own `device.svg` with zero misses.

So conversion is an id-for-id copy, not a lossy re-derivation. The device is needed to
build the `electrode_to_channel` map stored in `protocol_metadata`, and to detect the
case where the user has a different device loaded.

## 2. Field mapping

### 2.1 Mapped

| Legacy plugin + field | Type | New col_id / field_id | Transform |
|---|---|---|---|
| `microdrop.electrode_controller_plugin` `Voltage (V)` | float | `voltage` | `round()` to Int |
| `microdrop.electrode_controller_plugin` `Frequency (Hz)` | float | `frequency` | `round()` to Int |
| `microdrop.electrode_controller_plugin` `Duration (s)` | float | `duration_s` | direct |
| `microdrop.electrode_controller_plugin` `electrode_states` | Series[bool] | `electrodes` | ids whose value is truthy |
| `droplet_planning_plugin` `drop_routes` | DataFrame | `routes` | see 2.2 |
| `droplet_planning_plugin` `route_repeats` | int | `route_repetitions` | direct |
| `droplet_planning_plugin` `repeat_duration_s` | int | `repeat_duration` | direct, as float |
| `droplet_planning_plugin` `repeat_duration_s` > 0 | — | `repeat_duration_controls` row flag | set True |
| `droplet_planning_plugin` `trail_length` | int | `trail_length` | direct |
| `step_label_plugin` `label` | str | `name` | blank falls back to `Step <n>` |
| `user_prompt_plugin` `message` | str | `message_prompt` | direct |
| `dropbot_plugin` `volume_threshold` | float 0–1 | `volume_threshold` | `round(v * 100)`, clamped 0–100 |
| `dmf_device_ui_plugin` `video_enabled` | bool | `video` | direct |
| `mr_box_plugin` `Magnet` / `zika_box_plugin` `Magnet` | bool | `set_magnet` = True, `magnet_on` = value | height left at its "Default" sentinel |
| `zika_box_plugin` `Heater` | bool | `set_temperature` | direct |
| `zika_box_plugin` `Heater_temperature` | float | `target_temperature_c` | direct; `tolerance_c` left at default |
| `Protocol.n_repeats` | int | root group `repetitions` | only written when > 1 |

Voltage and frequency are `Int` end-to-end in the new system while the legacy format
stores them as floats, hence the rounding. `volume_threshold` changes units: legacy is a
0–1 fraction, the new column is a 0–100 integer percent.

When both `mr_box_plugin` and `zika_box_plugin` are present on a step, `zika_box_plugin`
wins for `Magnet` (it is the later, more specific peripheral); this is recorded in the
report rather than resolved silently.

### 2.2 Route conversion

`drop_routes` is a DataFrame with columns `route_i`, `electrode_i`, `transition_i`.
Group rows by `route_i`, sort each group by `transition_i`, and take the `electrode_i`
column — that ordered list of electrode ids is one route. The result is the
`List[List[str]]` the new `routes` column expects.

Routes are not a rare edge case: they are empty throughout Duo Fluo but **85 Zika steps
carry real multi-electrode routes**, so this path needs test coverage.

### 2.3 Dropped, with a report

| Legacy field | Why |
|---|---|
| `mr_box_plugin` `Pump`, `Pump_frequency_(hz)`, `Pump_duration_(s)` | No pump peripheral in the new system. `Pump` is `False` on all 2,470 steps observed. |
| `mr_box_plugin` `Measure_PMT`, `Measurement_duration_(s)` | No PMT support. `Measure_PMT` is `False` on all steps observed. |
| `mr_box_plugin` `Auto pump electrode` | Pump-specific. Constant (`24`) across all steps observed. |
| `mr_box_plugin` `Magnet_height(mm)` | MR-Box z-stage geometry does not correspond to the current magnet peripheral's. Constant (`0.0`) across all steps observed. |
| `user_prompt_plugin` `schema` | No equivalent. Empty string on all steps observed. |
| `plateau_detection_plugin` `Plateau Detection`, `Check Split`, `Calibrate Threshold` | No plateau-detection column exists in this build. This is real data (106 / 26 / 7 steps set True) and must be reported prominently. |

A field is also reported as dropped when its target column exists in principle but its
plugin is not loaded in the current session — e.g. importing a Zika protocol without
`heater-microdrop-plugin-py` active.

## 3. Behaviours the real data forces

Three cases came out of testing against the sample folders. Each is a requirement, not a
defensive nicety.

**A non-protocol file sits in a protocols directory.**
`August 2022 Quanterix test/protocols/Sci-Bots-Quanterix-Device.7z` is a 7-Zip archive.
The protocol dropdown must therefore probe each candidate file and list only those that
actually unpickle into a `Protocol`, rather than trusting the directory listing.

**Protocols reference electrodes their device no longer has.**
The Quanterix protocols reference `path1651` and `path1752`, neither of which exists in
that folder's `device.svg` — the device was edited after those protocols were authored.
The converter drops such ids from the step's `electrodes` / `routes`, counts them, and
reports them. It does not fail the import.

**Protocol-level repeats are used.** `n_repeats` is 120 in one sample and 15 in another,
so it cannot be ignored.

## 4. Architecture

Three pieces. The split exists so the conversion logic is testable without Qt, without
Redis, and without a running Envisage application.

### 4.1 `legacy_protocol_import` service package (Qt-free, plugin-free)

New subpackage under `pluggable_protocol_tree/services/legacy_protocol_import/` with its
own `consts.py`, per the subpackage-owns-its-constants convention.

- `legacy_pickle_reader.py` — reads a legacy protocol file. Uses a `pickle.Unpickler`
  subclass whose `find_class` returns a lightweight stub type for any `microdrop.*`,
  `microdrop_utility.*`, `flatland.*` or `pygtkhelpers.*` class, and defers to the
  default resolution otherwise (so `pandas` / `numpy` objects load normally).
  Loads with `encoding="latin1"`, the standard Python 2 pickle compatibility setting.
  Exposes `is_legacy_protocol_file(path) -> bool` for dropdown filtering and
  `read_legacy_protocol(path) -> LegacyProtocol` for conversion.
- `device_svg_channel_map.py` — parses a `device.svg` into `{electrode_id: channel}` by
  scanning `<path>` elements for `id` and `data-channels`. Deliberately a local XML
  scan rather than an import of `device_viewer`'s `SVGProcessor`: importing another
  plugin's parser here would violate the plugin-decoupling rule, and the converter needs
  only these two attributes.
- `device_folder_scanner.py` — resolves whatever directory the user picked into a list
  of `(device_name, device_svg_path, protocol_paths)`. See 4.2.
- `protocol_converter.py` — the mapping in section 2. Takes a `LegacyProtocol` plus an
  electrode→channel map, returns `(converted_steps, ConversionReport)` where
  `converted_steps` is a list of plain dicts keyed by new col_id / compound field_id.
  Knows nothing about `RowManager`, columns, or which plugins are loaded.
- `conversion_report.py` — `HasTraits` model accumulating dropped fields (with step
  counts), unresolved electrode ids, and mapped column names, plus the rendering used by
  the summary dialog.

Emitting *plain dicts* rather than a finished JSON payload is the key decision: it keeps
the converter independent of which plugins are loaded. Reconciling those dicts against
the live column set happens one layer up, which is also where "target column absent
because its plugin is not loaded" is detected and reported.

### 4.2 Directory shape detection

The user should not have to know which level of the tree to point at. Given a directory,
the scanner accepts three shapes:

| Shape | Detected by | Devices found |
|---|---|---|
| MicroDrop root | contains `devices/` | subdirectories of `devices/` |
| A single device folder | contains `device.svg` and `protocols/` | itself |
| A parent of device folders | subdirectories contain `device.svg` | those subdirectories |

This makes `~/Documents/MicroDrop`, `~/Documents/MicroDrop/devices/DMF-90-pin-array`,
and the `legacy_protocols` scratch directory all work without explanation.

### 4.3 Import dialog and menu action

The dialog is a `HasTraits` model plus a PySide6 view, following the
model/controller/view separation used elsewhere: the model holds the root path, the
device selection, the protocol selection and the resolved paths as traits; the view
observes them and rebuilds the dropdowns.

Widgets: a root-directory field with a Browse button, a device dropdown, a protocol
dropdown, and directly editable `device.svg` and protocol-file path fields. Editing a
path field directly overrides the dropdown selection, so files kept outside a standard
Device Folder are still importable.

The menu action follows the existing `DockPaneAction` pattern in
`pluggable_protocol_tree/menus.py` — a factory added to `protocol_menu_factory()`
alongside `&Load`, dispatching to a method on `PluggableProtocolDockPane` that delegates
to the hosted `ProtocolTreePane`.

All dialogs go through `microdrop_application.dialogs.pyface_wrapper`.

## 5. Import flow

1. User picks root directory, device and protocol; presses Import.
2. Read the legacy protocol and build the electrode→channel map from the chosen
   `device.svg`.
3. **Device check.** Compare the legacy device's electrode ids against the currently
   loaded device's map (available from `ProtocolTreePane.device_viewer_sync`). If they
   disagree, `confirm(...)` offers loading the legacy `device.svg`; the user may proceed
   anyway or cancel. The wrapper's `YES` / `NO` / `CANCEL` results are used directly —
   no new decision constants.
4. **Convert.** `protocol_converter` produces step dicts and a `ConversionReport`.
5. **Reconcile against live columns.** Build a `RowManager` seeded with the live column
   set, `add_step(values=...)` per converted step filtered to attributes the dynamic row
   type actually has, apply `repeat_duration_controls` row flags, set
   `protocol_metadata[ELECTRODE_TO_CHANNEL_KEY]`, and set root `repetitions` from
   `n_repeats`. Values whose attribute is missing are added to the report as dropped.
   Then `to_json()` to get a payload that is spec-conformant by construction.
6. **Hand off to the existing load path.** `validate_protocol(...)` →
   `confirm_report(...)` on findings → `manager.set_state_from_json(..., report_findings=False)`,
   exactly as `ProtocolTreePane.load_from_dialog` does today
   (`pluggable_protocol_tree/views/protocol_tree_pane.py:533`). Orphan-column and
   unknown-electrode checking is inherited rather than reimplemented.
7. **Show the conversion report** listing what was mapped and what was dropped, with
   per-field step counts.
8. Result sits in the tree **unsaved and dirty**. The user reviews it and uses the
   existing `Protocol > Save As`.

Nothing is written to disk by the import itself.

## 6. Error handling

- A file that fails to unpickle is excluded from the dropdown by
  `is_legacy_protocol_file`; if the user types such a path manually, `error(...)` names
  the file and the underlying exception.
- A `device.svg` that is unreadable or yields an empty channel map is an `error(...)`;
  import cannot proceed without electrode identity.
- Per-step conversion failures (a corrupt nested blob) are caught individually: that
  step is imported with defaults for the affected plugin's fields and the failure is
  recorded in the report. One bad step does not abort a 177-step protocol.
- All caught exceptions are logged through `logger.logger_service.get_logger`;
  tolerated paths use `logger.debug`, unexpected ones `logger.warning(..., exc_info=True)`.
  No bare `except:` and no `print`.

## 7. Testing

Unit tests against the sample folders, all Qt-free:

- `legacy_pickle_reader` loads all 57 sample protocols; rejects the `.7z` file.
- `device_svg_channel_map` extracts the expected electrode count for each of the four
  devices: Duo Fluo 126, DMF-90-pin-array 92, Zika-4d Mirror 87, Quanterix 71.
- Electrode resolution: every id used by Duo Fluo and Zika resolves; the two known
  Quanterix ids are reported unresolved rather than raising.
- Route conversion produces the expected ordered id lists for a known Zika step, and
  `[]` for a step with an empty `drop_routes`.
- Unit conversions: voltage/frequency round to Int, `volume_threshold` scales to 0–100,
  `repeat_duration_s` > 0 sets the row flag.
- A full round trip: convert a protocol, build the payload, and assert
  `validate_protocol` returns an empty report against the matching device map.

Sample protocol files are read from the existing scratch paths; tests skip with a clear
message when those directories are absent, so CI without the samples stays green.

## 8. Out of scope

- Batch conversion of a whole device folder in one action. The dropdown converts one
  protocol at a time; batch can follow if it is wanted.
- Importing legacy experiment logs.
- Round-tripping new protocols back to the legacy format.
- Reviving `plateau_detection_plugin` behaviour — the fields are reported and dropped.

## 9. Affected files

New, under `pluggable_protocol_tree/services/legacy_protocol_import/`:
`consts.py`, `legacy_pickle_reader.py`, `device_svg_channel_map.py`,
`device_folder_scanner.py`, `protocol_converter.py`, `conversion_report.py`.

New, under `pluggable_protocol_tree/views/`: the import dialog model and view.

Modified: `pluggable_protocol_tree/menus.py` (action factory),
`pluggable_protocol_tree/views/protocol_tree_pane.py` (import method following
`load_from_dialog`), and the dock pane's delegating method.
