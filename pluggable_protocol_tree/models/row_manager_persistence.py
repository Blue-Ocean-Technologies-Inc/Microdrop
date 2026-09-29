# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""JSON persistence for ``RowManager`` (issue #641 step 3): save/load the
tree + per-protocol metadata.

``RowManagerPersistenceMixin`` is mixed into ``RowManager`` by plain
multiple inheritance, not composed as a collaborator: ``to_json`` /
``from_json`` / ``set_state_from_json`` are RowManager's own public API
(same signatures, same ``self``/``cls`` semantics as before the move), so a
mixin keeps every external call site (``manager.to_json()``,
``RowManager.from_json(...)``) unchanged. A collaborator object would need
either a delegating wrapper method on RowManager for each of the three, or
callers reaching through an extra attribute — more moving parts for no
behavioral benefit here, unlike the dropbot_controller mixin SERVICES
(composed via Envisage service offers, swappable at runtime), which this
is not.
"""

# Microdrop package imports.
from pluggable_protocol_tree.services.protocol_validator import (
    log_report,
    validate_protocol,
)


class RowManagerPersistenceMixin:
    """``to_json`` / ``from_json`` / ``set_state_from_json``, mixed into
    ``RowManager``. Depends only on the host's public+protected API
    (``root``, ``columns``, ``protocol_metadata``, ``step_type``,
    ``group_type``, ``selection``, ``rows_changed``) — no state of its own.
    """

    def to_json(self) -> dict:
        """Serialize the tree + per-protocol metadata to a JSON-ready dict."""
        from pluggable_protocol_tree.services.persistence import serialize_tree

        return serialize_tree(
            self.root,
            list(self.columns),
            protocol_metadata=dict(self.protocol_metadata),
        )

    @classmethod
    def from_json(
        cls,
        data: dict,
        columns: list,
        device_electrode_to_channel=None,
        report_findings: bool = True,
    ) -> "RowManager":  # noqa: F821 (forward ref to the host class)
        """Reconstruct a RowManager from a serialized payload.

        When ``report_findings`` is True (headless default) the payload is
        validated against ``columns`` + ``device_electrode_to_channel`` and any
        findings are printed via the module logger before loading. The load
        proceeds regardless - headless cannot prompt."""
        from pluggable_protocol_tree.services.persistence import deserialize_tree

        if report_findings:
            report = validate_protocol(data, columns, device_electrode_to_channel)

            if not report.is_empty:
                log_report(report)

        manager = cls(columns=list(columns))
        root, metadata = deserialize_tree(
            data,
            columns,
            step_type=manager.step_type,
            group_type=manager.group_type,
        )
        manager.root = root
        manager.protocol_metadata = metadata

        return manager

    def set_state_from_json(
        self,
        data: dict,
        columns: list,
        device_electrode_to_channel=None,
        report_findings: bool = True,
    ) -> None:
        """Reconstruct tree state in-place from a serialized payload dynamically.

        When ``report_findings`` is True (headless default) findings are
        validated and printed via the module logger before applying state. The
        GUI load path passes ``report_findings=False`` because it has already
        shown them in a dialog."""
        from pluggable_protocol_tree.services.persistence import deserialize_tree

        if report_findings:
            report = validate_protocol(data, columns, device_electrode_to_channel)

            if not report.is_empty:
                log_report(report)

        # 1. Update columns. This triggers _on_columns_change via Traits,
        #    which automatically rebuilds self.step_type and self.group_type.
        self.columns = list(columns)

        # 2. Deserialize the payload into a new root and metadata dict
        root, metadata = deserialize_tree(
            data,
            self.columns,
            step_type=self.step_type,
            group_type=self.group_type,
        )

        # 3. Apply the new state
        self.root = root
        self.protocol_metadata = metadata

        # 4. Clear any dangling selection paths, as the old tree structure is gone
        self.selection = []

        # 5. Notify the UI/observers that the structure has completely changed
        self.rows_changed = True
