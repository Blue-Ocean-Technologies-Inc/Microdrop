"""Pure-python protocol model for the flowchart demo.

Mirrors the real app's concepts without traits:

  * A Row is a step or a group (a group owns children, like GroupRow in
    ``pluggable_protocol_tree``). Execution walks the leaf steps in tree
    order. Rows carry their canvas position so the drawing persists.
  * A DecisionSpec is what a column provider contributes alongside its
    IColumn trio: a question, a set of outcomes, and default routes so
    the protocol runs even if the user never customizes anything.
  * A DecisionNode is a *placed shape* on the canvas binding one step to
    one contributed decision — added from the step's ＋ palette. It holds
    the user's routing (outcome -> target) and prompt policy
    (prompt / auto / auto-after-N). With no shape placed, the provider
    defaults apply and the prompt still shows.
  * An OpNode is a logic shape (AND): its inputs are outcome endpoints of
    decision shapes belonging to ONE step; when every input outcome was
    chosen in that step's resolution round, the op's own route wins over
    the individual outcome routes.

Route targets are either one of the sentinels below or a row id (a group
id means "jump to the group's first step").
"""

import uuid as _uuid
from dataclasses import dataclass
from typing import Optional

# ---- route target sentinels ------------------------------------------------

NEXT = "__next__"     # fall through to the next leaf step in tree order
SELF = "__self__"     # re-run the current step (retry)
END = "__end__"       # finish the protocol (this repetition) cleanly
ABORT = "__abort__"   # abort the whole run

SENTINEL_LABELS = {
    NEXT: "next step",
    SELF: "retry this step",
    END: "finish protocol",
    ABORT: "abort protocol",
}


def _new_id():
    return _uuid.uuid4().hex[:8]


@dataclass(frozen=True)
class Outcome:
    """One answer a decision can resolve to (one button / one port)."""
    id: str
    label: str
    # Drives port/edge/button colors: "positive" | "negative" | "danger" | "neutral"
    kind: str = "neutral"


@dataclass(frozen=True)
class DecisionSpec:
    """Contributed by a column provider: a question the running protocol
    may pose, its possible outcomes, and provider defaults for where each
    outcome routes. ``default_outcome`` is the answer picked when the
    prompt is suppressed (auto mode / auto-after-N)."""
    id: str
    title: str
    question: str
    outcomes: tuple
    default_routes: dict          # outcome_id -> target (sentinel or row id)
    default_outcome: str
    provider_col_id: str = ""

    def outcome_by_id(self, outcome_id: str) -> Outcome:
        for o in self.outcomes:
            if o.id == outcome_id:
                return o
        raise KeyError(outcome_id)


class Row:
    """One protocol row: a step (leaf) or a group (owns children)."""

    def __init__(self, name, values=None, row_id=None, is_group=False):
        self.id = row_id or _new_id()
        self.name = name
        self.is_group = is_group
        self.children = [] if is_group else None
        self.values = dict(values or {})
        # Completion route (steps only): where execution goes when the
        # step finishes and no decision redirected it. NEXT = tree order.
        self.next_target = NEXT
        # Groups: how many passes a FORMAL group entry schedules (the
        # analogue of GroupRow.repetitions in the real app).
        self.repetitions = 1
        # Groups: collapsed to a single chip on the canvas (view state,
        # persisted so a saved protocol reopens the same way).
        self.collapsed = False
        # Canvas position, persisted with the protocol.
        self.pos = (0.0, 0.0)

    def to_dict(self):
        d = {"id": self.id, "name": self.name, "values": dict(self.values),
             "next_target": self.next_target, "pos": list(self.pos),
             "repetitions": self.repetitions}
        if self.is_group:
            d["children"] = [c.to_dict() for c in self.children]
            d["collapsed"] = self.collapsed
        return d

    @classmethod
    def from_dict(cls, d):
        row = cls(d["name"], d.get("values"), row_id=d["id"],
                  is_group="children" in d)
        row.next_target = d.get("next_target", NEXT)
        row.repetitions = int(d.get("repetitions", 1) or 1)
        row.pos = tuple(d.get("pos", (0.0, 0.0)))
        if row.is_group:
            row.children = [cls.from_dict(c) for c in d["children"]]
            row.collapsed = bool(d.get("collapsed", False))
        return row


class DecisionNode:
    """A placed decision shape: binds (step, contributed decision) and
    holds the user's routing + prompt policy for it."""

    def __init__(self, step_id, decision_id, pos=(0.0, 0.0), node_id=None):
        self.id = node_id or _new_id()
        self.step_id = step_id
        self.decision_id = decision_id
        self.pos = tuple(pos)
        self.routes = {}              # outcome_id -> target
        # Optional user overrides for the outcome button/edge labels
        # (outcome_id -> text); missing keys use the provider's label.
        self.labels = {}
        # Prompt policy:
        #   "prompt"      — always ask (auto_after=N: ask the first N
        #                   times, then answer automatically)
        #   "auto_first"  — answer automatically the first N times
        #                   (auto_after=N), THEN start asking — the
        #                   "auto-retry before escalating to the user"
        #                   behaviour
        #   "auto"        — never ask
        self.mode = "prompt"
        self.auto_after: Optional[int] = None
        self.auto_outcome: Optional[str] = None   # None -> spec default

    def label_for(self, outcome) -> str:
        return self.labels.get(outcome.id, outcome.label)

    def to_dict(self):
        return {"id": self.id, "step_id": self.step_id,
                "decision_id": self.decision_id, "pos": list(self.pos),
                "routes": dict(self.routes), "mode": self.mode,
                "auto_after": self.auto_after,
                "auto_outcome": self.auto_outcome,
                "labels": dict(self.labels)}

    @classmethod
    def from_dict(cls, d):
        n = cls(d["step_id"], d["decision_id"], d.get("pos", (0, 0)),
                node_id=d["id"])
        n.routes = dict(d.get("routes", {}))
        n.mode = d.get("mode", "prompt")
        n.auto_after = d.get("auto_after")
        n.auto_outcome = d.get("auto_outcome")
        n.labels = dict(d.get("labels", {}))
        return n


class OpNode:
    """A logic shape. kind "and": fires when every input outcome was
    chosen in the owning step's resolution round; its route then wins."""

    def __init__(self, kind="and", pos=(0.0, 0.0), node_id=None):
        self.id = node_id or _new_id()
        self.kind = kind
        self.pos = tuple(pos)
        self.inputs = []              # [(decision_node_id, outcome_id)]
        self.target = None            # sentinel or row id; None = unwired

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "pos": list(self.pos),
                "inputs": [list(i) for i in self.inputs],
                "target": self.target}

    @classmethod
    def from_dict(cls, d):
        n = cls(d.get("kind", "and"), d.get("pos", (0, 0)), node_id=d["id"])
        n.inputs = [tuple(i) for i in d.get("inputs", [])]
        n.target = d.get("target")
        return n


class Protocol:
    """A tree of rows + the placed decision/op shapes + the column set."""

    def __init__(self, columns):
        self.columns = list(columns)   # list[Column] from columns.py
        self.rows = []                 # top-level rows (tree)
        self.decision_nodes = []       # list[DecisionNode]
        self.op_nodes = []             # list[OpNode]
        # Canvas positions of the ⏹ Stop / ▦ Finish terminal nodes
        # ({kind: [x, y]}); None until the user moves them.
        self.terminal_pos = {}

    # -- tree walking ---------------------------------------------------

    def iter_rows(self):
        """(row, depth) in tree order."""
        def walk(rows, depth):
            for row in rows:
                yield row, depth
                if row.is_group:
                    yield from walk(row.children, depth + 1)
        yield from walk(self.rows, 0)

    def leaves(self):
        return [r for r, _ in self.iter_rows() if not r.is_group]

    def row_by_id(self, row_id) -> Optional[Row]:
        for row, _ in self.iter_rows():
            if row.id == row_id:
                return row
        return None

    def parent_list_of(self, row_id):
        """(container_list, index) holding the row, or (None, None)."""
        def search(rows):
            for i, row in enumerate(rows):
                if row.id == row_id:
                    return rows, i
                if row.is_group:
                    found = search(row.children)
                    if found[0] is not None:
                        return found
            return None, None
        return search(self.rows)

    def group_chain_of(self, row_id):
        """Groups containing the row, outermost first."""
        chain = []

        def walk(rows, stack):
            for r in rows:
                if r.id == row_id:
                    chain.extend(stack)
                    return True
                if r.is_group and walk(r.children, stack + [r]):
                    return True
            return False

        walk(self.rows, [])
        return chain

    def leaf_index(self, row_id) -> Optional[int]:
        """Execution index for a route target: a step's own index, or a
        group's first leaf. None for unknown/empty targets."""
        row = self.row_by_id(row_id)
        if row is None:
            return None
        if row.is_group:
            for leaf in _subtree_leaves(row):
                row = leaf
                break
            else:
                return None
        for i, leaf in enumerate(self.leaves()):
            if leaf.id == row.id:
                return i
        return None

    # -- row management -------------------------------------------------

    def add_step(self, name, values=None, after_id=None) -> Row:
        seeded = {c.model.col_id: c.model.default_value
                  for c in self.columns}
        seeded.update(values or {})
        step = Row(name, seeded)
        container, index = (self.parent_list_of(after_id)
                            if after_id else (None, None))
        if container is None:
            self.rows.append(step)
        else:
            container.insert(index + 1, step)
        return step

    def remove_rows(self, row_ids) -> None:
        removed_steps = set()
        for rid in row_ids:
            container, index = self.parent_list_of(rid)
            if container is None:
                continue
            row = container.pop(index)
            removed_steps.update(
                r.id for r in ([row] if not row.is_group
                               else _subtree_rows(row)))
        self._scrub_targets(removed_steps)

    def _scrub_targets(self, removed_ids):
        removed_dn = {dn.id for dn in self.decision_nodes
                      if dn.step_id in removed_ids}
        self.decision_nodes = [dn for dn in self.decision_nodes
                               if dn.step_id not in removed_ids]
        for op in self.op_nodes:
            op.inputs = [i for i in op.inputs if i[0] not in removed_dn]
            if op.target in removed_ids:
                op.target = None
        self.op_nodes = [op for op in self.op_nodes if op.inputs
                         or op.target]
        for row, _ in self.iter_rows():
            if row.next_target in removed_ids:
                row.next_target = NEXT
        for dn in self.decision_nodes:
            for oid, target in list(dn.routes.items()):
                if target in removed_ids:
                    del dn.routes[oid]

    # -- grouping -------------------------------------------------------

    def can_group(self, row_ids) -> bool:
        """Selected rows must be a contiguous run of siblings."""
        if not row_ids:
            return False
        containers = []
        indices = []
        for rid in row_ids:
            container, index = self.parent_list_of(rid)
            if container is None:
                return False
            containers.append(id(container))
            indices.append(index)
        if len(set(containers)) != 1:
            return False
        indices.sort()
        return indices == list(range(indices[0], indices[0] + len(indices)))

    def group_rows(self, row_ids, name="Group") -> Optional[Row]:
        if not self.can_group(row_ids):
            return None
        container, _ = self.parent_list_of(row_ids[0])
        indices = sorted(container.index(self.row_by_id(rid))
                         for rid in row_ids)
        members = [container[i] for i in indices]
        group = Row(name, is_group=True)
        group.children = members
        group.pos = members[0].pos
        container[indices[0]:indices[-1] + 1] = [group]
        return group

    def ungroup(self, group_id) -> bool:
        row = self.row_by_id(group_id)
        if row is None or not row.is_group:
            return False
        container, index = self.parent_list_of(group_id)
        container[index:index + 1] = row.children
        self._scrub_targets({group_id})
        return True

    # -- shapes ---------------------------------------------------------

    def decision_node_for(self, step_id, decision_id):
        for dn in self.decision_nodes:
            if dn.step_id == step_id and dn.decision_id == decision_id:
                return dn
        return None

    def decision_node_by_id(self, node_id):
        for dn in self.decision_nodes:
            if dn.id == node_id:
                return dn
        return None

    def add_decision_node(self, step_id, decision_id, pos) -> DecisionNode:
        dn = DecisionNode(step_id, decision_id, pos)
        self.decision_nodes.append(dn)
        return dn

    def remove_decision_node(self, node_id) -> None:
        self.decision_nodes = [dn for dn in self.decision_nodes
                               if dn.id != node_id]
        for op in self.op_nodes:
            op.inputs = [i for i in op.inputs if i[0] != node_id]
        # Chain routes pointing at the removed shape fall back to defaults.
        for dn in self.decision_nodes:
            for oid, target in list(dn.routes.items()):
                if target == node_id:
                    del dn.routes[oid]

    def add_op_node(self, pos, kind="and") -> OpNode:
        op = OpNode(kind, pos)
        self.op_nodes.append(op)
        return op

    def op_node_by_id(self, node_id):
        for op in self.op_nodes:
            if op.id == node_id:
                return op
        return None

    def remove_op_node(self, node_id) -> None:
        self.op_nodes = [op for op in self.op_nodes if op.id != node_id]

    def ops_for_step(self, step_id):
        """Op nodes all of whose inputs come from this step's decision
        shapes (an op with no inputs belongs to no step)."""
        out = []
        for op in self.op_nodes:
            if not op.inputs:
                continue
            owners = {dn.step_id
                      for i in op.inputs
                      for dn in [self.decision_node_by_id(i[0])]
                      if dn is not None}
            if owners == {step_id}:
                out.append(op)
        return out

    # -- decision specs available (from the column set) -----------------

    def spec_by_id(self, decision_id) -> Optional[DecisionSpec]:
        for col in self.columns:
            for spec in col.handler.decision_specs():
                if spec.id == decision_id:
                    return spec
        return None

    def all_specs(self):
        specs = []
        for col in sorted(self.columns, key=lambda c: (c.handler.priority,
                                                       c.model.col_id)):
            specs.extend(col.handler.decision_specs())
        return specs

    def describe_target(self, target) -> str:
        if target is None:
            return "not wired"
        if target in SENTINEL_LABELS:
            return SENTINEL_LABELS[target]
        row = self.row_by_id(target)
        if row is not None:
            return (f"group {row.name!r}" if row.is_group
                    else f"step {row.name!r}")
        dn = self.decision_node_by_id(target)
        if dn is not None:
            spec = self.spec_by_id(dn.decision_id)
            title = spec.title if spec else dn.decision_id
            return f"then resolve {title!r}"
        return "next step (missing target)"

    # -- persistence ----------------------------------------------------

    def to_dict(self):
        return {
            "rows": [r.to_dict() for r in self.rows],
            "decision_nodes": [d.to_dict() for d in self.decision_nodes],
            "op_nodes": [o.to_dict() for o in self.op_nodes],
            "terminal_pos": {k: list(v)
                             for k, v in self.terminal_pos.items()},
        }

    def load_dict(self, d) -> None:
        self.rows = [Row.from_dict(rd) for rd in d.get("rows", [])]
        self.decision_nodes = [DecisionNode.from_dict(x)
                               for x in d.get("decision_nodes", [])]
        self.op_nodes = [OpNode.from_dict(x) for x in d.get("op_nodes", [])]
        self.terminal_pos = {k: tuple(v) for k, v in
                             d.get("terminal_pos", {}).items()}
        # Seed any column values missing from the file (new columns since
        # save).
        for row, _ in self.iter_rows():
            if not row.is_group:
                for c in self.columns:
                    row.values.setdefault(c.model.col_id,
                                          c.model.default_value)


def _subtree_rows(row):
    yield row
    if row.is_group:
        for child in row.children:
            yield from _subtree_rows(child)


def _subtree_leaves(row):
    for r in _subtree_rows(row):
        if not r.is_group:
            yield r
