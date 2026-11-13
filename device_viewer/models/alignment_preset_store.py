# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera-alignment presets library: one JSON file under
ETSConfig.application_home holding every saved alignment, the defaults,
and the alignment last used with each camera on each device.

The file is ``{"schema_version": 2, "presets": [...], "defaults": [...]}``.
``presets`` holds the named presets and one automatically kept
``last_used`` record per (camera, device). Each default slot is
``{"scope", "device_key", "camera_id", "camera_label", "preset_id"}``, at
most one per slot: a camera + device slot, a device slot, or a camera
slot, after the preset's scope. Every mutation rereads the file, changes
it and writes it back atomically, keeping records and keys this version
does not understand.

A version-1 file is upgraded on first read (a copy of it is kept beside
it): every record and slot gains an unknown camera id, and every preset
keeps its device scope — none is narrowed to a camera.

Every device with a saved endpoint but no named preset gets one on each
refresh: its endpoint becomes an endpoint-only preset that is its default,
so devices aligned before presets existed (or after an unreadable file was
set aside) are covered. The endpoint cache itself is left alone — it stays
the working endpoint, and presets are a library of snapshots applied onto
it.

A file written by a newer schema is read-only: never rewritten, whatever
its shape. A file that cannot be parsed is kept aside under a fresh
``.unreadable`` name before a new one replaces it."""

# Standard library imports.
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

# Enthought library imports.
from traits.api import Bool, Dict, HasTraits, Instance, List, Str
from traits.etsconfig.api import ETSConfig

# Microdrop utils imports.
from microdrop_utils.file_handler import next_free_numbered_path, write_atomically

# Local imports.
from ..consts import (
    ALIGNMENT_PRESET_DEFAULT_STEM,
    ALIGNMENT_PRESET_KIND_LAST_USED,
    ALIGNMENT_PRESET_KIND_NAMED,
    ALIGNMENT_PRESET_SCOPE_CAMERA,
    ALIGNMENT_PRESET_SCOPE_CAMERA_DEVICE,
    ALIGNMENT_PRESET_SCOPE_DEVICE,
    ALIGNMENT_PRESETS_FILENAME,
    ALIGNMENT_PRESETS_SCHEMA_VERSION,
    CAMERA_ALIGNMENT_DIRNAME,
    MIGRATED_ENDPOINT_PRESET_SUFFIX,
    PRESET_NAME_TAKEN_TEMPLATE,
    PRESET_NEEDS_DEVICE_MESSAGE,
    PRESET_UNKNOWN_MESSAGE,
    PRESETS_NEWER_SCHEMA_MESSAGE,
)
from ..utils.camera_endpoints import CameraEndpointStore
from .alignment_preset import (
    AlignmentPreset,
    alignment_preset_name_error,
    alignment_scope_error,
    utc_now_iso,
)
from .camera_identity import CameraIdentity

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def default_presets_file():
    """Where the presets library lives by default. Resolved at call time,
    after the application has configured ETSConfig."""
    return (
        Path(ETSConfig.application_home)
        / CAMERA_ALIGNMENT_DIRNAME
        / ALIGNMENT_PRESETS_FILENAME
    )


def _empty_data():
    return {
        "schema_version": ALIGNMENT_PRESETS_SCHEMA_VERSION,
        "presets": [],
        "defaults": [],
    }


def _is_newer_schema(data):
    """Whether parsed file data declares a schema newer than this one."""
    version = data.get("schema_version") if isinstance(data, dict) else None

    return (
        isinstance(version, int)
        and not isinstance(version, bool)
        and version > ALIGNMENT_PRESETS_SCHEMA_VERSION
    )


def _has_known_shape(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("schema_version"), int)
        and isinstance(data.get("presets"), list)
        and isinstance(data.get("defaults"), list)
    )


def upgrade_to_current_schema(data):
    """Bring parsed version-1 data up to this schema in place and return it.

    Records and default slots gain an unknown (empty) camera id; a record
    without a scope gets the device scope, the only one version 1 wrote.
    Labels, scopes and every field this version does not know are kept.
    """

    for record in data["presets"]:
        if isinstance(record, dict):
            record.setdefault("scope", ALIGNMENT_PRESET_SCOPE_DEVICE)
            record.setdefault("camera_id", "")

    for slot in data["defaults"]:
        if isinstance(slot, dict):
            slot.setdefault("camera_id", "")
            slot.setdefault("camera_label", "")

    data["schema_version"] = ALIGNMENT_PRESETS_SCHEMA_VERSION

    return data


def _record_camera(record):
    """The camera a raw record or default slot names."""
    return CameraIdentity(
        camera_id=str(record.get("camera_id", "")),
        label=str(record.get("camera_label", "")),
    )


def _slot_for(record):
    """The default slot the raw preset ``record`` fills, after its scope:
    a camera scope keys on the camera, a device scope on the device."""
    scope = record.get("scope", ALIGNMENT_PRESET_SCOPE_DEVICE)
    keyed_on_device = scope != ALIGNMENT_PRESET_SCOPE_CAMERA
    keyed_on_camera = scope != ALIGNMENT_PRESET_SCOPE_DEVICE

    return {
        "scope": scope,
        "device_key": record.get("device_key", "") if keyed_on_device else "",
        "camera_id": record.get("camera_id", "") if keyed_on_camera else "",
        "camera_label": record.get("camera_label", "") if keyed_on_camera else "",
        "preset_id": record.get("id"),
    }


def _same_slot(slot, other):
    """Whether two default slots are the same slot (whatever they name)."""
    scope = slot.get("scope", ALIGNMENT_PRESET_SCOPE_DEVICE)

    if other.get("scope", ALIGNMENT_PRESET_SCOPE_DEVICE) != scope:
        return False

    if scope != ALIGNMENT_PRESET_SCOPE_CAMERA and (
        slot.get("device_key") != other.get("device_key")
    ):
        return False

    if scope != ALIGNMENT_PRESET_SCOPE_DEVICE:
        return _record_camera(slot).matches(_record_camera(other))

    return True


def _slot_covers(slot, scope, device_key, camera):
    """Whether ``slot`` is the ``scope`` slot of ``camera`` on
    ``device_key``."""

    if slot.get("scope", ALIGNMENT_PRESET_SCOPE_DEVICE) != scope:
        return False

    if scope != ALIGNMENT_PRESET_SCOPE_CAMERA and slot.get("device_key") != device_key:
        return False

    if scope != ALIGNMENT_PRESET_SCOPE_DEVICE:
        return _record_camera(slot).matches(camera)

    return True


def _put_default(data, record):
    """Make the raw preset ``record`` the default of its slot, replacing
    whatever that slot named and any other slot naming it."""
    slot = _slot_for(record)
    data["defaults"] = [
        other
        for other in data["defaults"]
        if not (
            isinstance(other, dict)
            and (other.get("preset_id") == record.get("id") or _same_slot(other, slot))
        )
    ]
    data["defaults"].append(slot)


def _drop_defaults_naming(data, preset_id):
    """Remove every default slot naming ``preset_id``; return whether there
    was one."""
    kept = [
        slot
        for slot in data["defaults"]
        if not (isinstance(slot, dict) and slot.get("preset_id") == preset_id)
    ]
    dropped = len(kept) != len(data["defaults"])
    data["defaults"] = kept

    return dropped


def _is_own_last_used_of(record, device_key, camera):
    """Whether ``record`` is the last-used record ``camera`` itself wrote on
    ``device_key``: the same id, or — for a camera without one — an id-less
    record with its label. A label-only record is never taken over by a
    camera with an id: it stays the fallback of every camera of that
    label."""
    return (
        isinstance(record, dict)
        and record.get("kind") == ALIGNMENT_PRESET_KIND_LAST_USED
        and record.get("device_key") == device_key
        and record.get("camera_id", "") == camera.camera_id
        and (bool(camera.camera_id) or record.get("camera_label") == camera.label)
    )


def _is_named_record_of(record, device_key):
    return (
        isinstance(record, dict)
        and record.get("kind", ALIGNMENT_PRESET_KIND_NAMED)
        == ALIGNMENT_PRESET_KIND_NAMED
        and record.get("device_key") == device_key
    )


def _record_with_id(data, preset_id):
    """Return the raw record ``preset_id`` in ``data``, or None."""
    return next(
        (
            record
            for record in data["presets"]
            if isinstance(record, dict) and record.get("id") == preset_id
        ),
        None,
    )


def _name_clash(data, device_key, name, preset_id=""):
    """Return the raw named record of ``device_key`` called ``name``
    (case-insensitively), other than ``preset_id``, or None."""
    folded = name.strip().casefold()

    return next(
        (
            record
            for record in data["presets"]
            if _is_named_record_of(record, device_key)
            and record.get("id") != preset_id
            and str(record.get("name", "")).strip().casefold() == folded
        ),
        None,
    )


class AlignmentPresetStore(HasTraits):
    """The saved camera-alignment presets, their defaults, and the
    alignment last used with each camera on each device."""

    #: The presets file; the default under ETSConfig.application_home is
    #: resolved on first use.
    path = Instance(Path)

    #: The endpoint cache: a device with an endpoint but no preset gets
    #: one from it.
    endpoint_store = Instance(CameraEndpointStore)

    #: SOURCE OF TRUTH for the presets table — every readable record, in
    #: file order.
    presets = List(Instance(AlignmentPreset))

    #: The default slots whose preset is readable.
    defaults = List(Dict)

    #: The store lists but never writes: the file was written by a newer
    #: schema, or (set by the owner) it could not be read or written.
    read_only = Bool(False)

    #: Why ``read_only`` is set, for the user; "" while writable.
    read_only_reason = Str()

    #: Where the latest unreadable file was kept, until the owner has told
    #: the user (it then clears it); "" for none.
    unreadable_copy = Str()

    #: Where the file was copied before an upgrade from an older schema;
    #: "" when it was not upgraded.
    upgraded_copy = Str()

    def _path_default(self):
        return default_presets_file()

    def _endpoint_store_default(self):
        return CameraEndpointStore()

    # ------------------------------------------------------------------ #
    def refresh(self):
        """Reread the file. An unreadable one is first kept aside; a device
        with a saved endpoint but no preset then gets one.

        Raises ``OSError`` when the file cannot be read, set aside or
        written.
        """
        data = self._read_data()

        if data is None:
            self._set_unreadable_file_aside()
            data = _empty_data()

        if _is_newer_schema(data):
            logger.warning(f"{PRESETS_NEWER_SCHEMA_MESSAGE} ({self.path})")
            self.read_only = True
            self.read_only_reason = PRESETS_NEWER_SCHEMA_MESSAGE

        else:
            self.read_only = False
            self.read_only_reason = ""
            self._upgrade(data)
            self._migrate_endpoints(data)

        self._list(data)

    def mark_unavailable(self, reason):
        """Stop writing until the next successful refresh, saying why."""
        self.read_only = True
        self.read_only_reason = reason

    def get(self, preset_id):
        """Return the listed preset ``preset_id``, or None."""
        return next((preset for preset in self.presets if preset.id == preset_id), None)

    def named_for(self, device_key):
        """Return ``device_key``'s named presets, sorted by name."""
        return sorted(
            (
                preset
                for preset in self.presets
                if preset.kind == ALIGNMENT_PRESET_KIND_NAMED
                and preset.device_key == device_key
            ),
            key=lambda preset: preset.name.casefold(),
        )

    def find_named(self, device_key, name):
        """Return ``device_key``'s named preset called ``name``
        (case-insensitively), or None."""
        folded = name.strip().casefold()

        return next(
            (
                preset
                for preset in self.named_for(device_key)
                if preset.name.casefold() == folded
            ),
            None,
        )

    def name_error(self, name, device_key, preset_id=""):
        """Return why preset ``preset_id`` ("" for a new one) of
        ``device_key`` cannot be called ``name``, or ""."""
        error = alignment_preset_name_error(name)

        if error:
            return error

        clash = self.find_named(device_key, name)

        if clash is not None and clash.id != preset_id:
            return PRESET_NAME_TAKEN_TEMPLATE.format(
                device_key=device_key, name=clash.name
            )

        return ""

    def unique_name(self, device_key, name):
        """Return ``name``, or ``name (N)`` for the smallest N ``device_key``
        has not used."""
        number = 2
        candidate = name

        while self.find_named(device_key, candidate):
            candidate = f"{name} ({number})"
            number += 1

        return candidate

    def next_default_name(self, device_key):
        """Return ``<stem>-N`` for the smallest N ``device_key`` has not used."""
        number = 1

        while self.find_named(device_key, f"{ALIGNMENT_PRESET_DEFAULT_STEM}-{number}"):
            number += 1

        return f"{ALIGNMENT_PRESET_DEFAULT_STEM}-{number}"

    def is_default(self, preset_id):
        """Return whether some default slot names ``preset_id``."""
        return any(slot.get("preset_id") == preset_id for slot in self.defaults)

    def resolve_default(self, device_key, camera=None):
        """Return the default preset for ``camera`` (a CameraIdentity; None
        for no camera) on ``device_key``, or None: the camera + device slot,
        else the device slot, else the camera's any-device slot."""
        defaults = self.defaults_for(device_key, camera)

        return defaults[0] if defaults else None

    def defaults_for(self, device_key, camera=None):
        """Return every default preset covering ``camera`` on
        ``device_key``, in the order ``resolve_default`` ranks them."""
        camera = camera if camera is not None else CameraIdentity()
        defaults = []

        for scope in (
            ALIGNMENT_PRESET_SCOPE_CAMERA_DEVICE,
            ALIGNMENT_PRESET_SCOPE_DEVICE,
            ALIGNMENT_PRESET_SCOPE_CAMERA,
        ):
            for slot in self.defaults:
                preset = self.get(slot.get("preset_id"))

                if preset is not None and _slot_covers(slot, scope, device_key, camera):
                    defaults.append(preset)

        return defaults

    def default_in_slot_of(self, scope, device_key, camera):
        """Return the default preset of the ``scope`` slot a preset of
        ``camera`` on ``device_key`` would fill, or None."""
        record = AlignmentPreset(
            scope=scope,
            device_key=device_key,
            camera_id=camera.camera_id,
            camera_label=camera.label,
        ).to_dict()
        slot = _slot_for(record)

        return next(
            (
                self.get(other.get("preset_id"))
                for other in self.defaults
                if _same_slot(other, slot)
            ),
            None,
        )

    def last_used_for(self, camera, device_key):
        """Return the alignment last used with ``camera`` on ``device_key``,
        or None. A record of the camera's own id outranks one matched by
        label."""

        if camera is None or not camera.is_known:
            return None

        records = [
            preset
            for preset in self.presets
            if preset.kind == ALIGNMENT_PRESET_KIND_LAST_USED
            and preset.device_key == device_key
            and preset.camera.matches(camera)
        ]
        records.sort(key=lambda preset: preset.camera_id != camera.camera_id)

        return records[0] if records else None

    # ------------------------------------------------------------------ #
    def save_named(self, name, snapshot, replace=False):
        """Save ``snapshot`` (an AlignmentPreset's geometry, camera and
        scope) as ``name`` for its device and return the saved preset.
        ``replace`` overwrites a same-named preset of that device in place,
        keeping its identity, default (moved to the new scope's slot) and
        any fields this version does not know.

        Raises ``ValueError`` for a bad name or scope, a clash without
        ``replace``, no device, or a read-only file.
        """
        error = alignment_preset_name_error(name) or alignment_scope_error(
            snapshot.scope,
            snapshot.camera_label,
            snapshot.camera_id,
            not snapshot.is_endpoint_only,
        )

        if error:
            raise ValueError(error)

        name = name.strip()
        device_key = snapshot.device_key

        if not device_key:
            raise ValueError(PRESET_NEEDS_DEVICE_MESSAGE)

        record = snapshot.to_dict()
        record.update(
            name=name,
            kind=ALIGNMENT_PRESET_KIND_NAMED,
            saved_at=utc_now_iso(),
        )

        def change(data):
            existing = _name_clash(data, device_key, name)

            if existing is None:
                record["id"] = str(uuid4())
                data["presets"].append(record)

                return

            if not replace:
                raise ValueError(
                    PRESET_NAME_TAKEN_TEMPLATE.format(device_key=device_key, name=name)
                )

            record["id"] = existing.get("id")
            existing.update(record)

            if _drop_defaults_naming(data, existing["id"]):
                _put_default(data, existing)

        self._mutate(change)
        logger.info(f"Saved camera-alignment preset '{name}' for {device_key}")

        return self.get(record["id"])

    def rename(self, preset_id, new_name):
        """Rename preset ``preset_id``; its id and default stay.

        Raises ``ValueError`` for an unknown preset, a bad name, or a name
        its device already uses.
        """
        error = alignment_preset_name_error(new_name)

        if error:
            raise ValueError(error)

        new_name = new_name.strip()

        def change(data):
            record = _record_with_id(data, preset_id)

            if record is None:
                raise ValueError(PRESET_UNKNOWN_MESSAGE)

            device_key = record.get("device_key", "")

            if _name_clash(data, device_key, new_name, preset_id) is not None:
                raise ValueError(
                    PRESET_NAME_TAKEN_TEMPLATE.format(
                        device_key=device_key, name=new_name
                    )
                )

            record["name"] = new_name

        self._mutate(change)
        logger.info(f"Renamed camera-alignment preset to '{new_name}'")

    def delete(self, preset_id):
        """Remove preset ``preset_id`` and any default naming it."""

        def change(data):
            record = _record_with_id(data, preset_id)

            if record is None:
                logger.warning(f"Cannot delete unknown alignment preset {preset_id}")

                return

            data["presets"].remove(record)
            data["defaults"] = [
                slot
                for slot in data["defaults"]
                if not (isinstance(slot, dict) and slot.get("preset_id") == preset_id)
            ]

        self._mutate(change)

    def set_default(self, preset_id):
        """Make preset ``preset_id`` the default of its scope's slot: its
        camera on its device, its device, or its camera.

        Raises ``ValueError`` for an unknown preset.
        """

        def change(data):
            record = _record_with_id(data, preset_id)

            if record is None:
                raise ValueError(PRESET_UNKNOWN_MESSAGE)

            _put_default(data, record)

        self._mutate(change)

    def clear_default(self, preset_id):
        """Leave the slot preset ``preset_id`` is the default of empty."""
        self._mutate(lambda data: _drop_defaults_naming(data, preset_id))

    def set_scope(self, preset_id, scope):
        """Change which setups preset ``preset_id`` applies to; a default
        moves to the new scope's slot.

        Raises ``ValueError`` for an unknown preset or a scope its camera
        and geometry cannot have.
        """

        def change(data):
            record = _record_with_id(data, preset_id)

            if record is None:
                raise ValueError(PRESET_UNKNOWN_MESSAGE)

            error = alignment_scope_error(
                scope,
                record.get("camera_label", ""),
                record.get("camera_id", ""),
                record.get("camera_quad") is not None,
            )

            if error:
                raise ValueError(error)

            record["scope"] = scope

            if _drop_defaults_naming(data, preset_id):
                _put_default(data, record)

        self._mutate(change)

    def remember_last_used(self, snapshot):
        """Keep ``snapshot`` as the alignment last used with its camera on
        its device, in place of the previous one.

        Raises ``ValueError`` without a device or camera, or while
        read-only, and ``OSError`` when the file cannot be written.
        """
        device_key, camera = snapshot.device_key, snapshot.camera

        if not device_key or not camera.is_known:
            raise ValueError("a last-used alignment needs its camera and device")

        record = snapshot.to_dict()
        record.update(
            name="",
            kind=ALIGNMENT_PRESET_KIND_LAST_USED,
            scope=ALIGNMENT_PRESET_SCOPE_CAMERA_DEVICE,
            saved_at=utc_now_iso(),
        )

        def change(data):
            existing = next(
                (
                    other
                    for other in data["presets"]
                    if _is_own_last_used_of(other, device_key, camera)
                ),
                None,
            )

            if existing is None:
                record["id"] = str(uuid4())
                data["presets"].append(record)

                return

            record["id"] = existing.get("id")
            existing.update(record)

        self._mutate(change)

    def forget_last_used(self, camera, device_key):
        """Drop the alignment last used with ``camera`` itself on
        ``device_key`` — not a record it only matches by label."""

        def change(data):
            data["presets"] = [
                record
                for record in data["presets"]
                if not _is_own_last_used_of(record, device_key, camera)
            ]

        if self.last_used_for(camera, device_key) is not None:
            self._mutate(change)

    # ------------------------------------------------------------------ #
    def _mutate(self, change):
        """Refresh, apply ``change`` (which may raise ValueError to refuse)
        to the file's data, write it back atomically and refresh again.

        Raises ``ValueError`` while read-only and ``OSError`` when the file
        cannot be read or written.
        """
        self.refresh()

        if self.read_only:
            raise ValueError(self.read_only_reason)

        data = self._read_data()

        if data is None:
            raise OSError(f"{self.path} could not be read")

        if _is_newer_schema(data):
            raise ValueError(PRESETS_NEWER_SCHEMA_MESSAGE)

        change(data)

        self._write_data(data)
        self.refresh()

    def _list(self, data):
        """Publish the readable records and default slots of ``data``."""
        records = data.get("presets")
        slots = data.get("defaults")
        presets = []

        for record in records if isinstance(records, list) else []:
            try:
                presets.append(AlignmentPreset.from_dict(record))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(f"Skipping a malformed alignment preset: {exc}")

        readable_ids = {preset.id for preset in presets}

        self.presets = presets
        self.defaults = [
            slot
            for slot in (slots if isinstance(slots, list) else [])
            if isinstance(slot, dict) and slot.get("preset_id") in readable_ids
        ]

    def _read_data(self):
        """Return the file's data: an empty library without a file, a newer
        schema's data whatever its shape, or None (logged) when it cannot be
        parsed or is not this schema's shape.

        Raises ``OSError`` when the file exists but cannot be read.
        """

        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _empty_data()

        try:
            data = json.loads(text)
        except ValueError as exc:
            logger.error(f"Camera-alignment presets unreadable ({self.path}): {exc}")

            return None

        # A newer schema may have reshaped the file; it is not ours to judge.
        if _is_newer_schema(data):
            return data

        if not _has_known_shape(data):
            logger.error(f"Camera-alignment presets malformed ({self.path})")

            return None

        return data

    def _upgrade(self, data):
        """Upgrade the file's older-schema ``data`` in place and write it
        back, first copying the file under a name no earlier copy uses."""

        if data["schema_version"] >= ALIGNMENT_PRESETS_SCHEMA_VERSION:
            return

        old_version = data["schema_version"]
        upgrade_to_current_schema(data)

        if self.path.exists():
            copy = next_free_numbered_path(
                self.path.with_name(f"{self.path.name}.v{old_version}")
            )
            shutil.copy2(self.path, copy)
            self.upgraded_copy = str(copy)

        self._write_data(data)
        logger.info(
            f"Upgraded the camera-alignment presets at {self.path} to schema "
            f"{ALIGNMENT_PRESETS_SCHEMA_VERSION} (version {old_version} kept as "
            f"{self.upgraded_copy})"
        )

    def _write_data(self, data):
        data["schema_version"] = ALIGNMENT_PRESETS_SCHEMA_VERSION
        write_atomically(self.path, json.dumps(data, indent=1).encode("utf-8"))

    def _set_unreadable_file_aside(self):
        """Keep the unreadable file under a name no earlier copy uses."""
        aside = next_free_numbered_path(
            self.path.with_name(f"{self.path.name}.unreadable")
        )

        os.replace(self.path, aside)
        self.unreadable_copy = str(aside)
        logger.warning(f"Kept the unreadable alignment presets file as {aside}")

    def _migrate_endpoints(self, data):
        """Give every device with a saved endpoint but no named preset its
        endpoint as a preset, made its default; write only when one was
        added."""
        devices_with_presets = {
            record.get("device_key")
            for record in data["presets"]
            if isinstance(record, dict)
            and record.get("kind", ALIGNMENT_PRESET_KIND_NAMED)
            == ALIGNMENT_PRESET_KIND_NAMED
        }
        migrated = []

        for device_key in self.endpoint_store.device_keys():
            endpoint = self.endpoint_store.load(device_key)

            if device_key in devices_with_presets or endpoint is None:
                continue

            preset = AlignmentPreset(
                name=f"{device_key} {MIGRATED_ENDPOINT_PRESET_SUFFIX}",
                device_key=device_key,
                scene_quad=endpoint,
                endpoint_quad=endpoint,
                saved_at=self.endpoint_store.saved_at(device_key) or utc_now_iso(),
            )
            record = preset.to_dict()
            data["presets"].append(record)
            _put_default(data, record)
            migrated.append(device_key)

        if not migrated:
            return

        self._write_data(data)
        logger.info(
            f"Made the saved camera-alignment endpoints of {', '.join(migrated)} "
            f"into presets at {self.path}"
        )
