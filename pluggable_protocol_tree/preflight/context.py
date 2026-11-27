# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Builds the ``PreflightContext`` of one run scope from the row manager,
the device-viewer sync controller, the preferences and the experiment
folder. Qt-free."""

# Standard library imports.
import os
import shutil
from collections import Counter
from itertools import dropwhile
from pathlib import Path

# Third-party imports.
from redis.exceptions import RedisError

# Microdrop package imports.
from device_viewer.consts import user_disabled_channels_mirror
from microdrop_application.helpers import get_current_experiment_directory
from pluggable_protocol_tree.consts import ELECTRODE_TO_CHANNEL_KEY
from pluggable_protocol_tree.execution.executor import has_protocol_level_hooks

# Local imports.
from .consts import BYTES_PER_GB, NON_SETTING_COLUMN_IDS
from .models import PreflightContext

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def build_preflight_context(
    manager, sync, preferences, run_paths, preview_mode, start_path=None
):
    """The snapshot of a run over ``run_paths`` (None: the whole protocol)
    from ``start_path`` (None: its first step) with ``preview_mode``.

    Parameters
    ----------
    manager : RowManager
        The protocol.
    sync : DeviceViewerSyncController
        The loaded device's electrode neighbours.
    preferences : ProtocolPreferences
        ``suppress_unused_column_hooks_information`` hides unused columns;
        ``protocol_tree_ack_times`` gives the used columns' ack waits.
    """
    frames = manager.iter_execution_frames(run_paths)

    if start_path is not None:
        # Play from a step skips the frames before it, as the executor does.
        frames = dropwhile(lambda frame: tuple(frame[0].path) != start_path, frames)

    repeats = Counter(tuple(row.path) for row, _ in frames)
    steps = [_step(manager, row, repeats) for row in manager.iter_run_rows(None)]
    columns = hooked_column_names(manager.columns)

    # The executor judges unused columns over run_paths, whatever the start.
    all_unused = manager.unused_column_ids(run_paths)
    unused = [column_id for column_id in all_unused if column_id in columns]
    ack_times = {
        column_id: seconds
        for column_id, seconds in preferences.protocol_tree_ack_times.items()
        if column_id not in all_unused
    }

    if preferences.suppress_unused_column_hooks_information:
        unused = []

    # The executor's channel map: the live device's, else a loaded file's
    # until the device geometry arrives.
    channels = dict(manager.protocol_metadata.get(ELECTRODE_TO_CHANNEL_KEY) or {})

    return PreflightContext(
        steps=steps,
        # Resolved here, in execution order: an empty list runs nothing.
        run_paths=list(repeats),
        preview_mode=preview_mode,
        columns=columns,
        unused_column_ids=unused,
        ack_times=ack_times,
        ack_column_names={
            column_id: preferences.protocol_tree_column_names.get(column_id, column_id)
            for column_id in ack_times
        },
        device_electrodes=list(channels),
        electrode_channels=channels,
        electrode_neighbours=dict(sync.electrode_neighbours),
        **_disabled_channel_facts(),
        **_folder_facts(),
    )


def hooked_column_names(columns):
    """Display names of the columns with protocol-level hooks, by id, in
    column order: those a run skips the hooks of when no step uses them.

    A column's ``preference_display_name`` wins over its header label
    (``col_name``); a compound's field cells share one id and arrive
    owner-first, so the owner's label names the compound.
    """
    names = {}

    for column in columns:
        if has_protocol_level_hooks(column.handler):
            names.setdefault(
                column.id,
                getattr(column, "preference_display_name", "")
                or column.model.col_name
                or column.id,
            )

    return names


def _step(manager, row, repeats):
    """One step's dict: its cell values by column id, then the facts the
    built-in checks read."""
    path = tuple(row.path)
    step = {
        column.model.col_id: column.model.get_value(row) for column in manager.columns
    }

    step.update(
        path=path,
        electrodes=list(getattr(row, "electrodes", None) or []),
        routes=[list(route) for route in getattr(row, "routes", None) or []],
        duration_s=float(getattr(row, "duration_s", 0.0) or 0.0),
        repeats=repeats.get(path, 0),
        set_columns=_set_column_ids(manager.columns, step),
    )

    return step


def _set_column_ids(columns, values):
    """Ids of the columns a step sets: a value other than the column's
    default (a compound's field cells carry their own; a Bool toggled off
    from a True default counts), the ``NON_SETTING_COLUMN_IDS`` aside."""
    set_ids = []

    for column in columns:
        model = column.model

        if model.col_id in NON_SETTING_COLUMN_IDS:
            continue

        value = values[model.col_id]

        if value != model.default_value:
            set_ids.append(model.col_id)

    return set_ids


def _disabled_channel_facts():
    """The user-disabled channels, or none while Redis cannot be read."""
    try:
        return {"disabled_channels": sorted(user_disabled_channels_mirror.read())}

    except RedisError as error:
        logger.error(f"Pre-flight cannot read the disabled channels: {error}")

        return {}


def _folder_facts():
    """The experiment folder's context fields. Those it cannot read (Redis
    or the file system failing) keep the context's fail-closed defaults."""
    facts = {}

    try:
        folder = get_current_experiment_directory()
        facts["experiment_folder"] = str(folder)
        existing = _nearest_existing(Path(folder))
        facts["folder_writable"] = os.access(existing, os.W_OK)
        facts["free_disk_gb"] = shutil.disk_usage(existing).free / BYTES_PER_GB

    except (OSError, RedisError) as error:
        logger.error(f"Pre-flight cannot read the experiment folder: {error}")

    return facts


def _nearest_existing(path):
    """``path``, or its nearest existing ancestor while the run has yet to
    create it: where its writability and free space are judged."""
    while not path.exists() and path.parent != path:
        path = path.parent

    return path
