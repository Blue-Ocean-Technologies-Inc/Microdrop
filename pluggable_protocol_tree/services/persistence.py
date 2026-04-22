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


def serialize_tree(root: GroupRow, columns: list) -> dict:
    """Build the full JSON dict for `root` using the given column set."""
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
