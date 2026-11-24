# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Per-plugin load records: which plugins started, which failed, and why.

Qt-free. The launch-time plugin manager (``isolating_plugin_manager``) and
the runtime plugin-group manager both write here; the status-bar indicator
and its panel (``plugin_management``) only read. It lives in
``microdrop_utils`` because both writers and the reader sit in different
plugin packages, which may not import each other.
"""

# Standard library imports.
import time
import traceback
from contextlib import contextmanager

# Enthought library imports.
from traits.api import (
    Bool,
    Enum,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
)

#: A plugin's load states, in the order a start moves through them.
LOAD_PENDING = "pending"
LOAD_LOADING = "loading"
LOAD_LOADED = "loaded"
LOAD_FAILED = "failed"

LOAD_STATES = (LOAD_PENDING, LOAD_LOADING, LOAD_LOADED, LOAD_FAILED)


def summarize_exception(error):
    """Return a one-line ``Type: message`` summary of ``error``."""
    message = str(error).strip().splitlines()
    first_line = message[0] if message else ""

    if not first_line:
        return type(error).__name__

    return f"{type(error).__name__}: {first_line}"


class PluginLoadRecord(HasTraits):
    """How one plugin's start went."""

    #: The plugin's Envisage id, or its ``module:Class`` spec when the class
    #: could not even be imported.
    plugin_id = Str()

    #: The plugin's user-visible name.
    name = Str()

    #: Where the plugin is in its start.
    state = Enum(*LOAD_STATES)

    #: One-line reason the start failed; empty unless failed.
    error = Str()

    #: Full traceback of the failure; empty unless failed.
    traceback = Str()

    #: Seconds the start took; 0 until it finished.
    duration = Float()

    #: True for a plugin the application cannot run without.
    essential = Bool(False)


class PluginLoadStatus(HasTraits):
    """The load records of every plugin, in load order, and their totals."""

    #: One record per plugin, in the order the plugins were started.
    records = List(Instance(PluginLoadRecord))

    #: Plugins waiting for, or in, their start.
    loading_count = Property(Int, observe="records.items.state")

    #: Plugins that started.
    loaded_count = Property(Int, observe="records.items.state")

    #: Plugins whose start failed.
    failed_count = Property(Int, observe="records.items.state")

    #: The aggregate state: loading while any plugin is pending or loading,
    #: else failed when any plugin failed, else loaded.
    state = Property(
        Enum(LOAD_LOADING, LOAD_LOADED, LOAD_FAILED), observe="records.items.state"
    )

    #: One-line totals, e.g. "31 plugins loaded, 1 failed".
    summary = Property(Str, observe="records.items.state")

    def _get_loading_count(self):
        return sum(
            record.state in (LOAD_PENDING, LOAD_LOADING) for record in self.records
        )

    def _get_loaded_count(self):
        return sum(record.state == LOAD_LOADED for record in self.records)

    def _get_failed_count(self):
        return sum(record.state == LOAD_FAILED for record in self.records)

    def _get_state(self):
        if self.loading_count:
            return LOAD_LOADING

        if self.failed_count:
            return LOAD_FAILED

        return LOAD_LOADED

    def _get_summary(self):
        parts = [f"{self.loaded_count} plugins loaded"]

        if self.loading_count:
            parts.append(f"{self.loading_count} loading")

        if self.failed_count:
            parts.append(f"{self.failed_count} failed")

        return ", ".join(parts)

    def get_record(self, plugin_id):
        """Return the record for ``plugin_id``, or None."""
        for record in self.records:
            if record.plugin_id == plugin_id:
                return record

        return None

    def mark_pending(self, plugin_id, name="", essential=False):
        """Reset ``plugin_id``'s record to pending, adding it if new.

        Returns
        -------
        PluginLoadRecord
            The plugin's record.
        """
        record = self.get_record(plugin_id)

        if record is None:
            record = PluginLoadRecord(plugin_id=plugin_id)
            self.records.append(record)

        record.trait_set(
            name=name or plugin_id,
            state=LOAD_PENDING,
            error="",
            traceback="",
            duration=0.0,
            essential=essential,
        )

        return record

    def mark_failed(self, plugin_id, error, traceback_text, duration=0.0, name=""):
        """Record that ``plugin_id`` failed, adding its record if new."""
        record = self.get_record(plugin_id) or self.mark_pending(plugin_id, name)

        record.trait_set(
            state=LOAD_FAILED,
            error=error,
            traceback=traceback_text,
            duration=duration,
        )

    def discard(self, plugin_id):
        """Drop ``plugin_id``'s record, e.g. once its plugin is unloaded."""
        record = self.get_record(plugin_id)

        if record is not None:
            self.records.remove(record)

    @contextmanager
    def recording(self, plugin, essential=False):
        """Record the start ``plugin`` runs inside this block.

        The record moves to loading on entry, and to loaded with the elapsed
        time on a clean exit. An exception marks it failed with the summary
        and traceback, and propagates.
        """
        record = self.get_record(plugin.id)

        if record is None or record.state != LOAD_PENDING:
            record = self.mark_pending(plugin.id, plugin.name, essential)

        record.state = LOAD_LOADING
        started_at = time.perf_counter()

        try:
            yield record

        except Exception as error:
            self.mark_failed(
                plugin.id,
                summarize_exception(error),
                traceback.format_exc(),
                time.perf_counter() - started_at,
            )

            raise

        record.trait_set(state=LOAD_LOADED, duration=time.perf_counter() - started_at)
