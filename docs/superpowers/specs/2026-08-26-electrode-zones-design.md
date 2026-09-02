# Electrode Zones — Design

Status: draft for review · 2026-08-26 · feature lives in `device_viewer/`

## Idea

Users annotate a device with **zones** (heating, mixing, …). A zone type has a
name and a color; each type owns any number of **regions** drawn on the device
viewer with corner snapping. Zones render as a semi-transparent overlay layer —
its own row in the alpha table — and overlapping regions blend visually.

Visual annotation only for v1, but the model is first-class: any code can ask
`zone_manager.get("mixing")` and receive region objects that know the
electrode ids and channels they cover.

## Model — `models/zones.py` (traits sketch)

```python
class ZoneType(HasTraits):
    id = Str()                          # stable key; == name unless generated
    name = Str()                        # display name: "heating", "mixing", ...
    color = Str()                       # hex, e.g. "#f5e050"


class ZoneRegion(HasTraits):
    zone_id = Str()                     # id of its ZoneType
    electrode_ids = List(Str)           # SOURCE OF TRUTH for the region
    channels = Property(List(Int), observe="electrode_ids")
    # derived from the Electrodes model: electrode_id -> channel


class ZoneLayerManager(HasTraits):
    zone_types = List(Instance(ZoneType))
    regions = List(Instance(ZoneRegion))
    active_zone_id = Str()              # type new regions are created as

    def get(self, zone_id) -> list[ZoneRegion]: ...
    def region_count(self, zone_id) -> int: ...
```

- Zones are tracked by **id**, not display name: `id = name` on creation
  unless that would collide with an existing id, in which case an id is
  generated — so two types may share a display name and still be distinct.
  All references (`ZoneRegion.zone_id`, `active_zone_id`, persistence) use
  the id; the name is display-only.

- `ZoneLayerManager` mounted as an `Instance` trait on `DeviceViewMainModel`,
  like the route layer manager.
- **Electrode set is the source of truth.** The outline polygon is *computed*
  as the union boundary of the member electrodes' shapes (shapely
  `unary_union` over `svg_model.polygons[id]`, scaled by
  `ElectrodeLayer.path_scale`). Corner snapping falls out for free, and the
  picture can never disagree with the membership.

## View

- `views/zone_view/zone_region_item.py` — one `QGraphicsPathItem` per region:
  path = union boundary of its electrodes, brush = type color at the layer
  alpha, cosmetic outline pen in the same color. Z-value between electrode
  fill and the channel text labels; overlaps blend via alpha.
- `ElectrodeLayer` gains `add_zones_to_scene` / `remove` / `redraw_zones`,
  wired into `add_all_items_to_scene`, following the connections pattern.
- **Alpha table**: add `zones_key = "Zones"` to `default_settings.py`
  `alpha_keys` / `default_alphas` / `default_visibility` — the row appears in
  the existing table automatically; add a `redraw_zones` branch to
  `ElectrodeInteractionControllerService._alpha_change`.
- **Sidebar — zone types table**: TraitsUI `TableEditor` (same shape as the
  alpha table) in its own `CollapsibleVStackBox`: columns *name*, *color*
  (color picker), *regions* (read-only count). Selected row = the manager's
  `active_zone_id`. Add / remove type buttons; removing a type asks (pyface
  wrapper dialog) and deletes its regions.
- **Sidebar — regions table**: a second `TableEditor` in a
  `CollapsibleVStackBox`, one row per region: *region id* (read-only,
  generated `{zone_id}-{n}`), *zone* (read-only), and an eye checkbox
  (`VisibleColumn`) toggling `ZoneRegion.visible` — the way to re-show a
  hidden region. Selected row = the manager's `selected_region` (two-way
  with canvas selection); edit / delete / hide buttons below act on it.

## Interaction

- New `zone` value in the `DeviceViewMainModel.mode` Enum. Draw and select
  are entered from the Zones sidebar's Off/Draw/Select radio.
- Zone drawing is a **select-then-commit** flow over a *pending selection*
  (`pending_electrode_ids` on the manager), shown live as a dashed highlight
  in the active zone's color:
  - **left-drag** rubber-bands electrodes; on release every electrode the
    band *touches* (any overlap, not just fully enclosed) is added to the
    pending selection (with live capture preview while dragging);
  - a plain **click** (no drag) toggles one electrode in/out of the pending
    selection — this is how irregular shapes are sculpted;
  - the **Commit zone** button turns the pending selection into one
    `ZoneRegion` of the active type and clears the selection (no-op when
    empty);
  - while a selection exists, a floating **check/delete/dismiss** overlay
    sits by its top-right corner on the device view — check commits in
    place, delete discards the whole selection, dismiss hides both canvas
    strips (`show_canvas_overlays`); the sidebar's *Canvas buttons* checkbox
    brings them back.
- **Select mode** (its own mode, distinct from drawing, since regions may
  overlap): clicking picks the topmost region under the cursor (empty space
  deselects) and sets the manager's `selected_region`. The selected region is
  indicated with a thicker outline, and a floating **edit/delete/hide**
  overlay sits by its top-right corner — mirrored by the same buttons under
  the sidebar regions table:
  - **edit** re-opens the region's electrode set as the pending selection
    (`editing_region` on the manager; the region hides from the committed
    layer while editing) and switches to draw mode — the usual drag/toggle
    sculpting then applies, commit updates the region *in place*, clearing
    the selection cancels the edit unchanged;
  - **delete** removes the region;
  - **hide** sets `ZoneRegion.visible = False`; the region disappears from
    the canvas and comes back via its eye checkbox in the regions table.
- **Right-click** on a region: context menu — *delete region*, *change type*.
- All wiring through `@observe` in `ElectrodeInteractionControllerService`,
  branching on mode in the existing mouse handlers.

## Persistence

- **Regions → the device SVG**, on the existing Save/Save-As path
  (`SvgUtil.save_to_file`): an autogenerated `<g inkscape:label="Zones">`
  layer, one child element per region carrying `data-zone-id` and
  `data-electrode-ids` — the same pattern as the Connections layer, so zones
  travel with the device file. On SVG load, the layer is parsed back into the
  manager; a region referencing a zone id that isn't defined locally gets
  that type auto-created (name = id) with a default color.
- **Zone types (id → name, color) → `DeviceViewerPreferences`** (app-global,
  shared across devices), same mirror-on-change pattern as the alpha values.
- Regions whose electrode ids are missing from the loaded device are dropped
  with a warning dialog; the next save writes the file without them.

## app_globals mirror

Like the active device SVG path (`DEVICE_SVG_PATH_KEY`) and the channel →
area map (`CHANNEL_AREAS_KEY`), the current zoning state is mirrored into the
Redis app-globals hash so any process (backend workers, protocol columns) can
read it without pub/sub:

- New key in `device_viewer/consts.py`, added to `APP_GLOBALS_KEYS`:
  `ZONES_KEY = "microdrop.device.zones"`.
- Value: a JSON-serializable snapshot keyed by zone id:
  `{zone_id: {"name": ..., "color": ..., "regions": [{"electrode_ids": [...],
  "channels": [...]}, ...]}}`.
- `ZoneLayerManager` follows the `Electrodes` pattern: an `@observe` on
  `regions.items` / `zone_types.items` rebuilds the snapshot and writes it via
  `_update_app_globals_on_trait_change_event` (module-level
  `app_globals = get_microdrop_redis_globals_manager()`), so the hash tracks
  every draw/delete/rename/recolor and each device SVG load.

## Overlap & contiguity semantics

- A region is always **one contiguous blob**, judged by the device SVG's own
  electrode neighbour graph (`svg_model.neighbours`): committing a disjoint
  pending selection splits it into one region per connected component, moving
  a region rejects drops that would break it apart, and merging requires the
  union to be contiguous. With no neighbour graph, contiguity checks disable
  (whole selection = one blob) rather than splitting everything.
- Regions may **overlap** freely, within and across zones (fills blend by
  alpha). Resolving a zone to hardware is always the **union**:
  `channels_for(zone_id)` returns the deduplicated union of its regions'
  channels; an electrode may belong to several zones at once, and consumers
  (protocol steps, app_globals snapshot) get the union per zone.
- Region ids (`{zone_id}-{n}`) are **monotonic and never reused** — deleting
  or undoing a region retires its id — so external references (app_globals,
  future protocol steps) can never silently rebind to a different region.

## Non-goals (v1)

- No pub/sub topics, no protocol integration, no per-zone behavior (e.g.
  heater targets). The queryable manager is the hook for all of that later.

## Testing

- Unit-testable without Redis/hardware (goes in `examples/tests/`): rubber-band
  → electrode capture, union-outline computation, SVG zones-layer round-trip,
  channel derivation from electrode ids.
- Convention checks: `py_compile` + `black` on touched files.
