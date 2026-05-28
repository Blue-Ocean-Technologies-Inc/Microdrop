# Persist Device View Rotation — Design

Date: 2026-05-28
Branch: `feat/persist_rotation`

## Goal

Persist the device-view rotation angle across sessions, mirroring how
`camera_perspective` is persisted via `DeviceViewerPreferences`. Zoom is
explicitly **out of scope** for this iteration — its lifecycle is fragile
(auto-fit and resize wipe it) and the feature branch name confirms rotation
as the target.

## Existing pattern (the template we mirror)

`DeviceViewMainModel.load_camera_perspective_from_preferences()`
(`device_viewer/models/main_model.py:104`):
- Reads two values from `self.preferences.preferences.get(...)`.
- Writes them into `self.camera_perspective`.
- A separate `@observe("camera_perspective:transformation")` (line 294)
  writes any change back to the preferences node.

`device_view_dock_pane.py:208` calls the load method once during dock pane
construction, immediately after the model is created.

## Current rotation state (today)

- Cumulative angle lives as a plain attribute `self._device_rotation_deg`
  on the interaction service (`electrode_interaction_service.py:177`,
  updated at line 1389).
- It is the source of truth used by gamepad direction remapping
  (`_get_device_rotation_deg`, line 761; `_map_direction_for_device_rotation`,
  line 765).
- The user-facing entry point is `handle_rotate_device()` (line 1448) which
  calls `_rotate_device_view(90)`. `_rotate_device_view` also calls
  `device_view.rotate(...)`, rotates electrode text by `-angle_step` to keep
  labels readable, and runs `fit_to_scene_rect()`.
- Nothing writes the angle to preferences today.

## Design

### 1. Promote the angle to a model trait

Add to `DeviceViewMainModel` (`device_viewer/models/main_model.py`):

```python
device_rotation_deg = Int(0, desc="Cumulative device-view rotation in degrees (0/90/180/270).")
```

This becomes the **single source of truth** for both the gamepad mapping
and the preference persistence. The interaction service drops its private
`self._device_rotation_deg` and reads/writes the model trait.

### 2. Load + save methods on the model

Mirror the camera helpers verbatim in structure:

```python
def load_device_perspective_from_preferences(self):
    raw = self.preferences.preferences.get("device_view.rotation_deg", "0")
    try:
        self.device_rotation_deg = int(raw) % 360
    except (TypeError, ValueError):
        pass  # corrupt pref -> keep default 0

@observe("device_rotation_deg")
def _device_perspective_changed(self, event=None):
    self.preferences.preferences.set(
        "device_view.rotation_deg", str(self.device_rotation_deg)
    )
```

Preference key: `device_view.rotation_deg` (lives under
`microdrop.device_viewer` like the camera keys).

### 3. Call the loader from the dock pane

In `device_view_dock_pane.py`, add immediately below the camera load
(line 208):

```python
self.model.load_device_perspective_from_preferences()
```

Loading happens before the device view widget exists — that's fine, because
the angle is just stored on the model. The view itself is rotated later by
the interaction service, which is created after the SVG/electrode layer
loads.

### 4. Apply the persisted angle when the interaction service starts

In `ElectrodeInteractionControllerService.traits_init`
(`electrode_interaction_service.py:155`), after the existing setup, apply
the persisted angle exactly the way `_rotate_device_view` would — but
without re-incrementing the trait:

```python
rot = self.model.device_rotation_deg % 360
if rot:
    self.device_view.rotate(rot)
    self.electrode_view_layer.rotate_electrode_views_texts(-rot)
    self.device_view.fit_to_scene_rect()
```

By this point both `device_view` and `electrode_view_layer` are bound on
the service (they're constructor args at `device_view_dock_pane.py:616`).

### 5. Switch the cumulative tracker over to the model trait

In `electrode_interaction_service.py`:

- Delete `self._device_rotation_deg = 0` from `traits_init` (line 177).
- Replace `_get_device_rotation_deg` (line 761) to read from
  `self.model.device_rotation_deg`.
- In `_rotate_device_view` (line 1389), replace the cumulative update
  with:

  ```python
  self.model.device_rotation_deg = (self.model.device_rotation_deg + int(angle_step)) % 360
  ```

  The observer on the model now writes through to preferences
  automatically — no extra save call here.

## Files touched

- `device_viewer/models/main_model.py` — add trait, load method, observer.
- `device_viewer/views/device_view_dock_pane.py` — one-line call to the
  new load method.
- `device_viewer/services/electrode_interaction_service.py` — drop the
  private attribute, route reads/writes through the model trait, and
  apply persisted rotation in `traits_init`.

## What we are NOT doing

- **Zoom persistence.** Auto-fit and window resize zero zoom out today,
  so persistence would be a half-feature. Revisit separately if needed.
- **Reset semantics.** "Reset view" (`_reset_view_event_triggered`,
  line 1971) continues to only `fit_to_scene_rect()` — it does not zero
  the rotation. Out of scope.
- **Per-device-file persistence.** The angle is stored globally, not
  keyed by SVG file. Matches the camera-perspective pattern.

## Risks / open questions

- **`fitInView` resetting the transform.** Existing rotate code calls
  `fit_to_scene_rect()` right after `rotate()`. The fact that rotation is
  visibly preserved today means either Qt's `fitInView` preserves the
  rotation portion of the transform in this build, or rotation is being
  re-applied implicitly. We replicate the *same* sequence in the load
  path, so behaviour matches the live rotate path exactly — no new risk.
- **Observer firing during load.** Setting the trait inside the loader
  will trigger `_device_perspective_changed`, which writes the freshly
  loaded value back to prefs. Harmless redundant write; matches the
  camera pattern, which does not guard against this either.
