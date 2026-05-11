# `id_to_channel` lifecycle in the new pluggable protocol tree

**Date:** 2026-05-11
**Companion to:** [`2026-05-11-issue-414-protocol-tree-device-viewer-sync-design.md`](./2026-05-11-issue-414-protocol-tree-device-viewer-sync-design.md)
**Status:** Reference — pinned design contract for the electrode-to-channel mapping

## Why this doc exists

The legacy `protocol_grid` plugin duplicated the electrode-to-channel mapping on every step's `device_state.id_to_channel`, plus carried a fresh copy in every `DEVICE_VIEWER_STATE_CHANGED` publish payload. That meant N copies for an N-step protocol, plus broker-traffic redundancy, plus N synchronization sites whenever the chip changed.

The new pluggable protocol tree deliberately doesn't reproduce that pattern. This doc pins down what we do instead — one writer, one storage location, three readers, automatic persistence.

## What it is

A `dict[str, int | None]` mapping each electrode SVG ID (e.g. `"e00"`, `"e01"`) to its physical DropBot channel number (e.g. `0`, `1`).

It's the **chip geometry** — fixed for a given chip + SVG file, only changes when the user inserts a different chip or loads a different SVG. Most of a session, it never changes.

## Where it lives — single source of truth

```
RowManager.protocol_metadata["electrode_to_channel"]
```

That's it. One dict, on the protocol-level metadata. **Not** on each step, **not** on the controller, **not** in a separate cache module. The `protocol_metadata` trait already exists on `RowManager` for exactly this purpose — its docstring even names `"electrode_to_channel"` as the canonical key.

The `DeviceViewerSyncController` exposes it as a read-only property:

```python
@property
def id_to_channel(self) -> dict[str, int | None]:
    return self.row_manager.protocol_metadata.get(
        "electrode_to_channel", {}
    )
```

The only auxiliary copy anywhere in the system is the controller's `_channel_to_id_cache` — but that's a *derived inverted view* of the same dict, used purely for fast reverse-lookup (channel → electrode) when handling free-mode toggles. Rebuilt from scratch whenever the source dict changes.

## Top-level dataflow

```
                  ┌─────────────────────────────────┐
                  │  DV's local model.electrodes    │  ← source of truth in DV-land
                  │  .id_to_channel                 │
                  └──────────────┬──────────────────┘
                                 │ publish on geometry change only
                                 ▼
              DEVICE_VIEWER_GEOMETRY_CHANGED  (small payload)
                                 │
                                 ▼
                  ┌─────────────────────────────────┐
                  │  DeviceViewerSyncController     │
                  │  ._on_geometry_qt:              │
                  │     write to protocol_metadata  │
                  │     rebuild _channel_to_id_cache│
                  └──────────────┬──────────────────┘
                                 │
                                 ▼
            ┌───────────────────────────────────────────┐
            │ RowManager.protocol_metadata              │  ← source of truth in protocol-tree-land
            │   ["electrode_to_channel"] = {...}        │     (one dict, persisted with the protocol)
            └────┬─────────────────┬─────────────────┬──┘
                 │                 │                 │
                 ▼                 ▼                 ▼
         executor reads      controller reads    to_json includes
         via scratch         via property +      automatically
         during routes       inverted cache
```

Three readers, one writer, one storage location, automatic persistence. No step-level duplication, no parallel caches, no synchronization code.

## Lifecycle, step by step

### 1. Birth — DV initializes

```
  ┌─────────────────────────────────────────────┐
  │  DV starts, loads SVG file                  │
  │                                             │
  │  ▸ device_viewer.models.electrodes parses   │
  │    SVG, builds electrode geometry           │
  │  ▸ self.model.electrodes.id_to_channel      │
  │    is now populated                         │
  │                                             │
  │  protocol tree knows nothing yet            │
  └─────────────────────────────────────────────┘
```

At this point the mapping exists only inside the DV's model. The protocol tree doesn't know about it yet.

### 2. First publication — `DEVICE_VIEWER_GEOMETRY_CHANGED`

```
  ┌─────────────────────────────────────────────┐
  │  DV._publish_geometry_if_changed()          │
  │                                             │
  │  current = {eid: e.channel for eid, e in    │
  │             model.electrodes.electrodes      │
  │             .items()}                       │
  │  if current == self._last_published_id_     │
  │                  to_channel:                │
  │      return    ◀──── change-gated           │
  │  self._last_published_id_to_channel =       │
  │      dict(current)                          │
  │  publish_message(                           │
  │      topic=DEVICE_VIEWER_GEOMETRY_CHANGED,  │
  │      message=GeometryChangedMessage(        │
  │          id_to_channel=current).serialize() │
  │  )                                          │
  └─────────────────────────────────────────────┘

  Triggers (call sites):
    ▸ chip-insert handler
    ▸ apply_message_model when SVG file path changes
    ▸ first model initialization (one-shot at startup)
```

The publish is **gated** on actual change. A thousand state-change publishes between two chip-insert events trigger zero geometry publishes.

### 3. Reception — controller writes to `protocol_metadata`

```
  DEVICE_VIEWER_GEOMETRY_CHANGED  (broker)
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Worker thread (Dramatiq):                  │
  │    _listener_routine(message, topic):       │
  │       if topic == DEVICE_VIEWER_GEOMETRY_   │
  │                       CHANGED:              │
  │           bridge.geometry_changed.emit(     │
  │               message)                      │
  └─────────────────────────────────────────────┘
       │  Qt.AutoConnection marshals to GUI thread
       ▼
  ┌─────────────────────────────────────────────┐
  │  GUI thread:                                │
  │    _on_geometry_qt(payload):                │
  │       msg = GeometryChangedMessage.         │
  │             deserialize(payload)            │
  │                                             │
  │       # SINGLE WRITE SITE                   │
  │       row_manager.protocol_metadata[        │
  │           "electrode_to_channel"            │
  │       ] = msg.id_to_channel                 │
  │                                             │
  │       # rebuild inverted view               │
  │       self._channel_to_id_cache = {         │
  │           chan: eid                         │
  │           for eid, chan in                  │
  │           msg.id_to_channel.items()         │
  │           if chan is not None               │
  │       }                                     │
  └─────────────────────────────────────────────┘
```

This is the **single write site** for the mapping. After this point, anyone in the protocol-tree world reading `protocol_metadata["electrode_to_channel"]` sees the current mapping.

### 4. Cold-start safety net

What if the controller subscribes *after* the DV has already initialized and the geometry message has been published and missed? Phase 1 keeps `id_to_channel` in `DEVICE_VIEWER_STATE_CHANGED` for legacy compat, so the *first* state message we see still carries the mapping inline:

```
  DEVICE_VIEWER_STATE_CHANGED  (cold-start state msg)
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  _on_dv_state_qt(payload):                  │
  │     dv_msg = DeviceViewerMessageModel.      │
  │              deserialize(payload)           │
  │                                             │
  │     if not row_manager.protocol_metadata    │
  │            .get("electrode_to_channel"):    │
  │         # COLD-START SEED — same write      │
  │         # site logic as step 3              │
  │         row_manager.protocol_metadata[      │
  │             "electrode_to_channel"          │
  │         ] = dv_msg.id_to_channel            │
  │         self._channel_to_id_cache = {       │
  │             chan: eid                       │
  │             for eid, chan in                │
  │             dv_msg.id_to_channel.items()    │
  │             if chan is not None             │
  │         }                                   │
  │                                             │
  │     # ... continue with free-mode capture   │
  │     # using the now-populated mapping       │
  └─────────────────────────────────────────────┘
```

In Phase 2 (deferred to PPT-9), the cold-start path goes away because the DV publishes geometry on its own initialization unconditionally — the explicit topic becomes the only source.

### 5. Use — three readers

#### A. The executor (during routes execution)

```
  ┌─────────────────────────────────────────────┐
  │  routes_column.py: RoutesHandler.on_step    │
  │                                             │
  │  mapping = ctx.protocol.scratch.get(        │
  │      "electrode_to_channel", {}             │
  │  )                                          │
  │  for phase in iter_phases(...):             │
  │      electrodes = sorted(phase)             │
  │      channels = sorted(                     │
  │          mapping[e] for e in electrodes     │
  │          if e in mapping                    │
  │      )                                      │
  │      publish_message(                       │
  │          topic=ELECTRODES_STATE_CHANGE,     │
  │          message=json.dumps({               │
  │              "electrodes": electrodes,      │
  │              "channels": channels,          │
  │          }),                                │
  │      )                                      │
  └─────────────────────────────────────────────┘

  Note: ProtocolContext.scratch is hydrated from
  protocol_metadata at run start. So the executor
  reads from the same dict, just via the scratch
  alias.
```

#### B. The controller (free-mode capture, reverse-lookup)

```
  DEVICE_VIEWER_STATE_CHANGED  (free-mode toggle, no step_id)
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  _on_dv_state_qt(payload):                  │
  │     dv_msg = DeviceViewerMessageModel.      │
  │              deserialize(payload)           │
  │     if dv_msg.step_id:                      │
  │         self._free_mode_stash = None        │
  │         return                              │
  │     if not (dv_msg.channels_activated or    │
  │             dv_msg.routes):                 │
  │         self._free_mode_stash = None        │
  │         return                              │
  │                                             │
  │     # REVERSE LOOKUP via inverted cache     │
  │     electrodes = sorted(                    │
  │         self._channel_to_id_cache[c]        │
  │         for c in dv_msg.channels_activated  │
  │         if c in self._channel_to_id_cache   │
  │     )                                       │
  │     routes = [list(ids)                     │
  │               for ids, _ in dv_msg.routes]  │
  │     self._free_mode_stash = {               │
  │         "electrodes": electrodes,           │
  │         "routes": routes,                   │
  │     }                                       │
  └─────────────────────────────────────────────┘
```

#### C. The DV-side adapter (incoming `PROTOCOL_TREE_DISPLAY_STATE`)

The DV doesn't need the protocol's copy — it owns the geometry locally because it's the source. Our slim outgoing payload doesn't carry `id_to_channel`; the DV resolves electrode IDs → channels using its own model:

```
  PROTOCOL_TREE_DISPLAY_STATE  (slim payload, no id_to_channel)
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  device_view_dock_pane.                     │
  │     _on_protocol_tree_display_state_        │
  │     triggered(message_serial):              │
  │                                             │
  │     msg = ProtocolTreeDisplayMessage.       │
  │            deserialize(message_serial)      │
  │                                             │
  │     # use DV's OWN local mapping            │
  │     id_to_channel = self.model.electrodes   │
  │                       .id_to_channel        │
  │                                             │
  │     channels_activated = {                  │
  │         id_to_channel[eid]                  │
  │         for eid in msg.electrodes           │
  │         if id_to_channel.get(eid)           │
  │            is not None                      │
  │     }                                       │
  │     # ... rest of adapter                   │
  └─────────────────────────────────────────────┘
```

### 6. Persistence — automatic

When the user saves the protocol via `RowManager.to_json()`, `protocol_metadata` is included:

```json
{
  "schema_version": 1,
  "metadata": {
    "electrode_to_channel": {"e00": 0, "e01": 1, "e02": 2, ...}
  },
  "rows": [...]
}
```

When the user loads a saved protocol via `from_json` / `set_state_from_json`, the metadata round-trips. The controller doesn't need to do anything — its property reader will see the loaded mapping immediately. The `_channel_to_id_cache` rebuild happens lazily on first read (or could be eagerly rebuilt in a `protocol_metadata` Trait observer; implementation detail).

If the loaded protocol's mapping differs from the currently-attached chip, the next `DEVICE_VIEWER_GEOMETRY_CHANGED` from the DV (e.g., when the user inserts a chip) overwrites it through the same write site in step 3.

### 7. Insert-as-new-step (free-mode capture flow)

Worth tracing because this is where stale geometry could matter most. The user toggled some electrodes in free mode while a protocol with mapping `{e00: 0}` was loaded, but the current chip has mapping `{e00: 5}`. What happens?

```
  Free-mode toggle in DV
    ▸ DV publishes channels_activated = {5}
       (DV uses its OWN current mapping)

  Controller receives state msg
    ▸ Reverse-lookup via _channel_to_id_cache
       (which mirrors protocol_metadata)
    ▸ If geometry has been updated since chip insert:
         _channel_to_id_cache = {5: "e00"}
         → electrodes = ["e00"]
    ▸ If geometry NOT updated (no chip insert
       since protocol load):
         _channel_to_id_cache = {0: "e00"}
         → electrodes = []  (channel 5 not in cache)
         → empty stash; no false capture

  Protection: the free-mode capture only triggers
  on geometry the controller actually knows about.
  Stale geometry can drop electrodes silently, but
  it won't fabricate wrong ones.
```

The fix for stale geometry is the geometry topic itself: chip insert publishes the new mapping, controller updates `protocol_metadata`, all subsequent reverse-lookups use it. The very first geometry publish after chip insert resolves the divergence.

### 8. Phase-2 evolution (deferred to PPT-9)

Today the DV still puts `id_to_channel` in every `DEVICE_VIEWER_STATE_CHANGED` because legacy `protocol_grid` consumes it from there in 30+ places. Once `protocol_grid` is deleted, Phase 2 makes that field `Optional[dict] = None` and `gui_models_to_message_model` stops populating it.

Our controller doesn't change — it already reads from `protocol_metadata` and only used the inline mapping as a cold-start seed. The cold-start path then has to rely on the explicit geometry topic instead, which is fine because the DV always publishes geometry on its own initialization.

```
  Phase 1 (this spec)         Phase 2 (PPT-9 era)
  ──────────────────────       ──────────────────────
  GEOMETRY_CHANGED      ──┐    GEOMETRY_CHANGED      ──┐
  (small, on change)      │    (small, on change)      │
                          │                            │
  STATE_CHANGED           │    STATE_CHANGED           │
  carries id_to_channel ──┤    no id_to_channel       │
  (legacy consumer needs) │                           │
                          ▼                           ▼
              protocol_metadata             protocol_metadata
              ["electrode_to_channel"]      ["electrode_to_channel"]
                          │                           │
                          ▼                           ▼
              cold-start seed possible     cold-start relies on
              from inline state mapping    GEOMETRY_CHANGED only
                                           (DV always publishes
                                           on init)
```

## Summary table

| Aspect | Legacy (`protocol_grid`) | New (`pluggable_protocol_tree`) |
|---|---|---|
| Storage location | Per-step `device_state.id_to_channel` (N copies for N-step protocol) | `RowManager.protocol_metadata["electrode_to_channel"]` (1 dict) |
| Publish payload | `DEVICE_VIEWER_STATE_CHANGED` carries it on every publish (~1.4 KB / publish on a 90-pin chip) | Phase 1: same payload + new dedicated `DEVICE_VIEWER_GEOMETRY_CHANGED` topic for change-gated publishes. Phase 2 (PPT-9): state topic drops the field. |
| Synchronization | `_apply_id_to_channel_mapping_to_all_steps` walks every step on chip insert | None — single dict, single write site, instant. |
| Persistence | Embedded in each step's serialized state | Single `metadata.electrode_to_channel` key in the protocol JSON |
| Reverse-lookup (channel → electrode) | Recomputed ad hoc from each step's copy | Inverted view in `_channel_to_id_cache`, rebuilt on geometry change. |
| Cold-start (controller subscribes late) | N/A (legacy widget initializes alongside DV) | Phase 1: seed `protocol_metadata` from first `DEVICE_VIEWER_STATE_CHANGED` if metadata empty. Phase 2: rely on `DEVICE_VIEWER_GEOMETRY_CHANGED` published on DV init. |

## Invariants

- The mapping has **exactly one storage location** in protocol-tree-land: `RowManager.protocol_metadata["electrode_to_channel"]`.
- The mapping has **exactly one write site** in the controller: shared between `_on_geometry_qt` (preferred) and `_on_dv_state_qt` cold-start seed (fallback).
- The `_channel_to_id_cache` on the controller is **derivable** from the source dict; never authoritative; rebuilt on any write.
- The DV owns its own local copy on `model.electrodes.id_to_channel` — that's the source. The protocol-tree side is a downstream replica synced via the geometry topic.
- Persistence is **automatic** via `RowManager.to_json` / `from_json` because `protocol_metadata` is already part of the serialization contract.
