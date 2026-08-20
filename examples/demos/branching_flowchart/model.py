"""Pure-python protocol model for the flowchart demo.

Mirrors the real app's concepts without traits:

  * A Step is what a BaseRow is in ``pluggable_protocol_tree`` — a bag of
    per-column values keyed by col_id, plus (new here) its routing state.
  * A DecisionSpec is what a column provider would contribute alongside its
    IColumn trio: a question, a set of outcomes, and default routes so the
    protocol runs even if the user never customizes anything.
  * A RouteConfig is the user's per-(step, decision) customization, edited
    graphically on the canvas: where each outcome goes, and whether the
    prompt is shown or auto-answered (optionally only after N occurrences).

Route targets are either one of the sentinels below or a concrete step id.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

# ---- route target sentinels ------------------------------------------------

NEXT = "__next__"     # fall through to the next step in table order
SELF = "__self__"     # re-run the current step (retry)
END = "__end__"       # finish the protocol (this repetition) cleanly
ABORT = "__abort__"   # abort the whole run

SENTINEL_LABELS = {
    NEXT: "next step",
    SELF: "retry this step",
    END: "finish protocol",
    ABORT: "abort protocol",
}


@dataclass(frozen=True)
class Outcome:
    """One answer a decision can resolve to (one button / one port)."""
    id: str
    label: str
    # Drives port/edge/button colors: "positive" | "negative" | "danger" | "neutral"
    kind: str = "neutral"


@dataclass(frozen=True)
class DecisionSpec:
    """Contributed by a column provider: a question the running protocol may
    pose, its possible outcomes, and provider defaults for where each
    outcome routes. ``default_outcome`` is the answer picked when the
    prompt is suppressed (auto mode / auto-after-N)."""
    id: str
    title: str
    question: str
    outcomes: tuple
    default_routes: dict          # outcome_id -> target (sentinel or step id)
    default_outcome: str
    provider_col_id: str = ""

    def outcome_by_id(self, outcome_id: str) -> Outcome:
        for o in self.outcomes:
            if o.id == outcome_id:
                return o
        raise KeyError(outcome_id)


@dataclass
class RouteConfig:
    """User customization for one (step, decision) pair."""
    # outcome_id -> target; falls back to spec.default_routes when absent.
    routes: dict = field(default_factory=dict)
    # "prompt": always ask. "auto": never ask, pick auto_outcome.
    mode: str = "prompt"
    # If set (and mode == "prompt"), ask the first N times this decision
    # fires for this step in a run, then switch to auto silently.
    auto_after: Optional[int] = None
    # Outcome picked in auto mode; None -> spec.default_outcome.
    auto_outcome: Optional[str] = None

    def to_dict(self):
        return {"routes": dict(self.routes), "mode": self.mode,
                "auto_after": self.auto_after, "auto_outcome": self.auto_outcome}

    @classmethod
    def from_dict(cls, d):
        return cls(routes=dict(d.get("routes", {})), mode=d.get("mode", "prompt"),
                   auto_after=d.get("auto_after"), auto_outcome=d.get("auto_outcome"))


class Step:
    """One protocol step: named, with per-column values and routing state."""

    def __init__(self, name, values=None, step_id=None):
        self.id = step_id or uuid.uuid4().hex[:8]
        self.name = name
        self.values = dict(values or {})
        # Completion route: where execution goes when the step finishes and
        # no decision redirected it. NEXT = table order (the implicit edge).
        self.next_target = NEXT
        # decision_id -> RouteConfig
        self.decision_cfgs = {}
        # Canvas position, persisted with the protocol.
        self.pos = (0.0, 0.0)

    def cfg_for(self, decision_id) -> RouteConfig:
        """Get-or-create the RouteConfig for a decision on this step."""
        cfg = self.decision_cfgs.get(decision_id)
        if cfg is None:
            cfg = RouteConfig()
            self.decision_cfgs[decision_id] = cfg
        return cfg

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "values": dict(self.values),
            "next_target": self.next_target, "pos": list(self.pos),
            "decision_cfgs": {k: v.to_dict() for k, v in self.decision_cfgs.items()},
        }

    @classmethod
    def from_dict(cls, d):
        s = cls(d["name"], d.get("values"), step_id=d["id"])
        s.next_target = d.get("next_target", NEXT)
        s.pos = tuple(d.get("pos", (0.0, 0.0)))
        s.decision_cfgs = {
            k: RouteConfig.from_dict(v)
            for k, v in d.get("decision_cfgs", {}).items()
        }
        return s


class Protocol:
    """Ordered steps + the column set that defines their parameters."""

    def __init__(self, columns):
        self.columns = list(columns)   # list[Column] from columns.py
        self.steps = []

    # -- step management ------------------------------------------------

    def add_step(self, name, values=None, index=None) -> Step:
        seeded = {c.model.col_id: c.model.default_value for c in self.columns}
        seeded.update(values or {})
        step = Step(name, seeded)
        if index is None:
            self.steps.append(step)
        else:
            self.steps.insert(index, step)
        return step

    def remove_step(self, step_id) -> None:
        self.steps = [s for s in self.steps if s.id != step_id]
        # Scrub dangling routes that pointed at the removed step.
        for s in self.steps:
            if s.next_target == step_id:
                s.next_target = NEXT
            for cfg in s.decision_cfgs.values():
                for oid, target in list(cfg.routes.items()):
                    if target == step_id:
                        del cfg.routes[oid]

    def index_of(self, step_id) -> Optional[int]:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        return None

    def step_by_id(self, step_id) -> Optional[Step]:
        i = self.index_of(step_id)
        return self.steps[i] if i is not None else None

    # -- decision specs available on a step (from its columns) ----------

    def decision_specs(self):
        specs = []
        for col in sorted(self.columns, key=lambda c: (c.handler.priority,
                                                       c.model.col_id)):
            specs.extend(col.handler.decision_specs())
        return specs

    def describe_target(self, target) -> str:
        if target in SENTINEL_LABELS:
            return SENTINEL_LABELS[target]
        step = self.step_by_id(target)
        return f"step {step.name!r}" if step else "next step (missing target)"

    # -- persistence ----------------------------------------------------

    def to_dict(self):
        return {"steps": [s.to_dict() for s in self.steps]}

    def load_dict(self, d) -> None:
        self.steps = [Step.from_dict(sd) for sd in d.get("steps", [])]
        # Seed any column values missing from the file (new columns since save).
        for s in self.steps:
            for c in self.columns:
                s.values.setdefault(c.model.col_id, c.model.default_value)
