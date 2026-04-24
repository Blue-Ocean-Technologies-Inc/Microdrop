"""Save and load the protocol tree as compact JSON.

Format:
  {
    "schema_version": 1,
    "columns": [{"id": ..., "cls": "module.ClassName"}, ...],
    "fields":  ["depth", "uuid", "type", "name", ...col_ids],
    "rows":    [[depth, uuid, type, name, *values], ...]
  }

Depth encodes tree nesting: each row becomes a child of the most recent
open row at depth-1 during reconstruction. Group membership is derived
from sequence + depth — no separate shape structure is stored.
"""

from typing import Iterator, List

from pluggable_protocol_tree.consts import PERSISTENCE_SCHEMA_VERSION
from pluggable_protocol_tree.models.row import BaseRow, GroupRow


def serialize_tree(root: GroupRow, columns: list, protocol_metadata=None) -> dict:
    """Build the full JSON dict for `root` using the given column set.

    `protocol_metadata` is a dict of namespaced settings (PPT-3:
    'electrode_to_channel'). Optional for backward compat with
    PPT-1/PPT-2 callers that don't pass it.
    """
    col_specs = [
        {
            "id": c.model.col_id,
            "cls": f"{type(c.model).__module__}.{type(c.model).__name__}",
        }
        for c in columns
    ]
    fields = ["depth", "uuid", "type", "name"] + [c["id"] for c in col_specs]

    rows_out = list(_walk_with_depth(root, columns, depth=0, skip_root=True))

    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "protocol_metadata": dict(protocol_metadata or {}),
        "columns": col_specs,
        "fields": fields,
        "rows": rows_out,
    }


def _walk_with_depth(node, columns: list, depth: int, skip_root: bool) -> Iterator[list]:
    if not skip_root:
        vals = [depth, node.uuid, node.row_type, node.name]
        for col in columns:
            raw = col.model.get_value(node)
            vals.append(col.model.serialize(raw))
        yield vals
    if isinstance(node, GroupRow):
        for child in node.children:
            yield from _walk_with_depth(child, columns, depth + (0 if skip_root else 1),
                                         skip_root=False)


import importlib
import logging

logger = logging.getLogger(__name__)


def deserialize_tree(data: dict, columns: list, step_type, group_type):
    """Reconstruct a tree from a saved-JSON dict.

    Args:
        data: output of serialize_tree (possibly from another session).
        columns: live IColumn list to load values into.
        step_type: dynamic step subclass for this protocol.
        group_type: dynamic group subclass for this protocol.

    Returns (root, protocol_metadata) tuple; protocol_metadata is an
    empty dict if the JSON predates PPT-3.
    """
    live_by_col_id = {c.model.col_id: c for c in columns}
    col_specs: list = data["columns"]
    fields: list = data["fields"]

    # Per-saved-column resolution: (col_id, live_col_or_None)
    resolved: list = []
    for spec in col_specs:
        col_id = spec["id"]
        cls_path = spec["cls"]
        live = live_by_col_id.get(col_id)
        if live is None:
            # Try to import the class to distinguish orphan-present-but-unused
            # from missing-plugin — in PPT-1 we just warn in both cases.
            try:
                importlib.import_module(cls_path.rsplit(".", 1)[0])
                logger.warning(
                    "Column '%s' exists in save but not in live column set — "
                    "its values will be skipped.", col_id,
                )
            except ImportError:
                logger.warning(
                    "Column '%s' class '%s' could not be imported — "
                    "plugin missing? Values will be skipped.",
                    col_id, cls_path,
                )
        resolved.append((col_id, live))

    root = group_type(name="Root")
    stack: list = [root]

    first_value_idx = 4   # fields = depth, uuid, type, name, *col_ids
    for row_tuple in data["rows"]:
        depth = int(row_tuple[0])
        uuid_ = str(row_tuple[1])
        row_type = str(row_tuple[2])
        name = str(row_tuple[3])
        values = row_tuple[first_value_idx:]

        stack = stack[: depth + 1]   # trim to the right ancestor
        parent = stack[-1]

        row_cls = step_type if row_type == "step" else group_type
        row = row_cls(name=name, uuid=uuid_)

        for (col_id, live_col), raw in zip(resolved, values):
            if live_col is None:
                continue
            setattr(row, col_id, live_col.model.deserialize(raw))

        parent.add_row(row)

        if row_type == "group":
            stack.append(row)

    metadata = dict(data.get("protocol_metadata") or {})
    return root, metadata
