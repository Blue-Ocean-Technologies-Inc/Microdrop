"""Demo application shell.

Layout: flowchart canvas (left) | parameter table + run log (right).
The table plays the role of today's protocol grid — it only sets step
parameters (steps = the tree's leaves); the canvas owns the flow: step
order, groups, placed decision shapes, AND combiners, and all routes.
"""

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QMainWindow, QMenu, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout,
)

from .canvas import (
    DEC_W, KIND_COLORS, NODE_W, DecisionShapeItem, EdgeItem, FlowchartScene,
    FlowchartView, OpNodeItem, StepNodeItem,
)
from .columns import make_demo_columns
from .executor import DemoExecutor
from .model import NEXT, Protocol


class DecisionDialog(QDialog):
    """The runtime prompt: question + one colored button per outcome, each
    showing where the protocol will go, plus 'don't ask again this run'."""

    def __init__(self, pending, parent=None):
        super().__init__(parent)
        self.pending = pending
        self.chosen = None
        self.setWindowTitle(f"Decision — {pending.spec.title}")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Step: <b>{pending.step.name}</b>"))
        q = QLabel(pending.spec.question)
        q.setWordWrap(True)
        q.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(q)
        if pending.message:
            m = QLabel(pending.message)
            m.setWordWrap(True)
            m.setStyleSheet("color: #8b95a7;")
            layout.addWidget(m)

        buttons = QHBoxLayout()
        for outcome, target, desc in pending.options:
            color = KIND_COLORS.get(outcome.kind).name()
            btn = QPushButton(f"{outcome.label}\n→ {desc}")
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}; color: #111827; "
                f"font-weight: bold; padding: 8px 14px; "
                f"border-radius: 5px; }}"
                f"QPushButton:hover {{ background: #e5e7eb; }}")
            btn.clicked.connect(
                lambda _=False, oid=outcome.id: self._pick(oid))
            buttons.addWidget(btn)
        layout.addLayout(buttons)

        self.remember = QCheckBox(
            "Don't ask again this run (auto-pick my answer)")
        layout.addWidget(self.remember)

    def _pick(self, outcome_id):
        self.chosen = outcome_id
        self.accept()

    def outcome(self):
        # Esc / close = provider default, never a hang.
        return self.chosen or self.pending.spec.default_outcome


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "MicroDrop — branching protocol flowchart (standalone UX demo)")
        self.resize(1360, 800)

        self.columns = make_demo_columns()
        self.protocol = Protocol(self.columns)
        self._seed_protocol()

        self.executor = DemoExecutor(self.protocol)
        s = self.executor.signals
        s.protocol_started.connect(self._on_started)
        s.protocol_finished.connect(lambda: self._on_terminal("finished"))
        s.protocol_aborted.connect(lambda: self._on_terminal("aborted"))
        s.protocol_error.connect(lambda e: self._on_terminal(f"error: {e}"))
        s.protocol_paused.connect(lambda: self._sync_pause(True))
        s.protocol_resumed.connect(lambda: self._sync_pause(False))
        s.step_started.connect(self._on_step_started)
        s.decision_pending.connect(self._on_decision_pending)
        s.log.connect(self._append_log)

        self.scene = FlowchartScene(self, self.protocol)
        self.view = FlowchartView(self.scene)
        self.scene.selectionChanged.connect(self._on_scene_selection)

        self.table = QTableWidget()
        self.table.itemChanged.connect(self._on_table_edit)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self._updating_table = False
        self._syncing_selection = False

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setStyleSheet(
            "font-family: monospace; font-size: 11px; background: #111827; "
            "color: #e5e7eb;")

        right = QSplitter(Qt.Vertical)
        right.addWidget(self.table)
        right.addWidget(self.log)
        right.setSizes([420, 300])
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.view)
        split.addWidget(right)
        split.setSizes([940, 420])
        self.setCentralWidget(split)

        self._build_toolbar()
        self._active_dialog = None

        self._arrange("vertical", rebuild=False)
        self.rebuild()
        self.view.fit_all()
        self.statusBar().showMessage(
            "＋ on a step: add decision/AND/OR shapes · drag a port to a "
            "node: route (onto a sibling decision: resolve serially; onto "
            "blank space: mint a step) · drag a selection box + Group · "
            "Ctrl+wheel: zoom · middle-drag: pan")

    # ------------------------------------------------------------------
    # toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.run_action = QAction("▶ Run", self)
        self.run_action.triggered.connect(lambda _=False: self._on_run())
        tb.addAction(self.run_action)

        self.pause_action = QAction("⏸ Pause", self)
        self.pause_action.setCheckable(True)
        self.pause_action.setEnabled(False)
        self.pause_action.toggled.connect(self._on_pause_toggled)
        tb.addAction(self.pause_action)

        self.stop_action = QAction("⏹ Stop", self)
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(
            lambda _=False: self.executor.stop())
        tb.addAction(self.stop_action)

        tb.addSeparator()
        tb.addWidget(QLabel(" Repeats: "))
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 99)
        tb.addWidget(self.repeats)

        tb.addSeparator()
        add = QAction("＋ Add step", self)
        add.triggered.connect(lambda _=False: self._on_add_step())
        tb.addAction(add)
        delete = QAction("🗑 Delete", self)
        delete.setShortcut(QKeySequence.Delete)
        delete.triggered.connect(lambda _=False: self.delete_selected())
        tb.addAction(delete)

        tb.addSeparator()
        group = QAction("▣ Group", self)
        group.triggered.connect(lambda _=False: self.group_selected())
        tb.addAction(group)
        ungroup = QAction("▢ Ungroup", self)
        ungroup.triggered.connect(lambda _=False: self.ungroup_selected())
        tb.addAction(ungroup)

        tb.addSeparator()
        av = QAction("⇩ Arrange V", self)
        av.triggered.connect(lambda _=False: self._arrange("vertical"))
        tb.addAction(av)
        ah = QAction("⇨ Arrange H", self)
        ah.triggered.connect(lambda _=False: self._arrange("horizontal"))
        tb.addAction(ah)
        fit = QAction("⤢ Fit", self)
        fit.triggered.connect(lambda _=False: self.view.fit_all())
        tb.addAction(fit)

        tb.addSeparator()
        save = QAction("Save…", self)
        save.triggered.connect(lambda _=False: self._on_save())
        tb.addAction(save)
        load = QAction("Load…", self)
        load.triggered.connect(lambda _=False: self._on_load())
        tb.addAction(load)

    # ------------------------------------------------------------------
    # seed protocol
    # ------------------------------------------------------------------

    def _seed_protocol(self):
        p = self.protocol
        p.add_step("Prime reservoir", {"voltage": 90.0, "duration_s": 0.8})
        dispense = p.add_step(
            "Dispense droplet",
            {"voltage": 110.0, "duration_s": 1.0, "fail_pct": 40,
             "op_check": True})
        mix = p.add_step("Corrective mix 4×",
                         {"voltage": 120.0, "duration_s": 1.5})
        p.add_step("Operator inspect",
                   {"voltage": 0.0, "duration_s": 0.3, "op_check": True})
        collect = p.add_step("Collect to waste",
                             {"voltage": 100.0, "duration_s": 0.8})

        # Placed shapes on Dispense: both its decisions, resolved SERIALLY
        # (volume first; the operator check is only asked when the volume
        # answer is Continue — the dashed chain edge), plus an AND that
        # skips the corrective mix when everything checks out.
        dn_vol = p.add_decision_node(dispense.id, "volume_check", (0, 0))
        dn_vol.routes["retry"] = dispense.id       # orange self-loop
        dn_vol.auto_after = 3
        dn_op = p.add_decision_node(dispense.id, "operator_check", (0, 0))
        dn_vol.routes["continue"] = dn_op.id       # chain: then ask operator
        op = p.add_op_node((0, 0))
        op.inputs = [(dn_vol.id, "continue"), (dn_op.id, "yes")]
        op.target = collect.id
        # "Operator inspect" keeps its decision UNplaced — it still
        # prompts, with the provider defaults (yes→next, no→retry).

        # A starter group so the concept is visible out of the box.
        p.group_rows([dispense.id, mix.id], name="Droplet prep")

    # ------------------------------------------------------------------
    # canvas callbacks — palette, drops, menus, deletion
    # ------------------------------------------------------------------

    def rebuild(self):
        self.scene.rebuild()
        self._rebuild_table()

    def open_shape_palette(self, row_id, screen_pos, scene_pos):
        step = self.protocol.row_by_id(row_id)
        if step is None or step.is_group:
            return
        menu = QMenu(self)
        placed_any = False
        for spec in self.protocol.all_specs():
            existing = self.protocol.decision_node_for(row_id, spec.id)
            action = menu.addAction(f"⬥ Decision: {spec.title}")
            if existing is not None:
                action.setEnabled(False)
                action.setText(f"⬥ Decision: {spec.title} (placed)")
            else:
                action.triggered.connect(
                    lambda _=False, s=spec: self._place_decision(step, s))
            placed_any = True
        if placed_any:
            menu.addSeparator()
        menu.addAction("◇ AND operator — all connected outcomes chosen",
                       lambda: self._place_op(step, "and"))
        menu.addAction("◇ OR operator — any connected outcome chosen",
                       lambda: self._place_op(step, "or"))
        menu.exec(screen_pos.toPoint() if hasattr(screen_pos, "toPoint")
                  else screen_pos)

    def _place_decision(self, step, spec):
        k = len([d for d in self.protocol.decision_nodes
                 if d.step_id == step.id])
        self.protocol.add_decision_node(
            step.id, spec.id,
            (step.pos[0] + NODE_W + 90, step.pos[1] - 10 + k * 78))
        self.rebuild()

    def _place_op(self, step, kind="and"):
        self.protocol.add_op_node(
            (step.pos[0] + NODE_W + 90 + DEC_W + 70, step.pos[1] + 40),
            kind=kind)
        self.rebuild()

    def commit_port_drop(self, port, target):
        proto = self.protocol
        if port.role == "done" and isinstance(target, StepNodeItem):
            step = port.owner.row
            step.next_target = target.row.id
            self._append_log(
                f"Routed completion of {step.name!r} → "
                f"{proto.describe_target(target.row.id)}")
        elif port.role == "outcome":
            dn = port.owner.dnode
            if isinstance(target, StepNodeItem):
                dn.routes[port.outcome_id] = target.row.id
                self._append_log(
                    f"Routed {port.owner.spec.title} / {port.outcome_id} → "
                    f"{proto.describe_target(target.row.id)}")
            elif isinstance(target, DecisionShapeItem):
                if target.dnode.step_id != dn.step_id:
                    self.statusBar().showMessage(
                        "Decisions can only chain to another decision of "
                        "the same step.", 6000)
                    return
                dn.routes[port.outcome_id] = target.dnode.id
                self._append_log(
                    f"Chained {port.owner.spec.title} / {port.outcome_id} "
                    f"→ then resolve {target.spec.title!r}")
            elif isinstance(target, OpNodeItem):
                op = target.opnode
                owners = {d.step_id for i in op.inputs
                          for d in [proto.decision_node_by_id(i[0])]
                          if d is not None}
                if owners and owners != {dn.step_id}:
                    self.statusBar().showMessage(
                        "An AND can only combine outcomes from the same "
                        "step's decisions.", 6000)
                    return
                pair = (dn.id, port.outcome_id)
                if pair not in op.inputs:
                    op.inputs.append(pair)
                self._append_log(
                    f"Fed {port.owner.spec.title} / {port.outcome_id} "
                    f"into {op.kind.upper()}")
        elif port.role == "opout" and isinstance(target, StepNodeItem):
            op = port.owner.opnode
            op.target = target.row.id
            self._append_log(
                f"Routed {op.kind.upper()} → "
                f"{proto.describe_target(target.row.id)}")
        else:
            return
        self.rebuild()

    def commit_port_drop_on_blank(self, port, pos):
        """Drag released over blank space: mint a new step where the ghost
        sat, insert it after the source step in the tree, and wire the
        dragged port to it."""
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't add steps while the protocol is running.", 5000)
            return
        proto = self.protocol
        if port.role == "done":
            anchor = port.owner.row
        elif port.role == "outcome":
            anchor = proto.row_by_id(port.owner.dnode.step_id)
        else:  # opout
            op = port.owner.opnode
            anchor = None
            if op.inputs:
                dn = proto.decision_node_by_id(op.inputs[0][0])
                if dn is not None:
                    anchor = proto.row_by_id(dn.step_id)
        new_step = proto.add_step(
            f"Step {len(proto.leaves()) + 1}",
            after_id=anchor.id if anchor is not None else None)
        new_step.pos = pos
        if port.role == "done":
            port.owner.row.next_target = new_step.id
        elif port.role == "outcome":
            port.owner.dnode.routes[port.outcome_id] = new_step.id
        else:
            port.owner.opnode.target = new_step.id
        self._append_log(f"Added {new_step.name!r} from a port drag")
        self.rebuild()

    def delete_selected(self):
        proto = self.protocol
        edges = [i for i in self.scene.selectedItems()
                 if isinstance(i, EdgeItem) and i.payload]
        decs = [i.dnode.id for i in self.scene.selectedItems()
                if isinstance(i, DecisionShapeItem)]
        ops = [i.opnode.id for i in self.scene.selectedItems()
               if isinstance(i, OpNodeItem)]
        rows = [i.row.id for i in self.scene.selectedItems()
                if isinstance(i, StepNodeItem)]
        if rows and self.executor.is_running():
            self.statusBar().showMessage(
                "Can't delete steps while the protocol is running.", 5000)
            rows = []
        if not (edges or decs or ops or rows):
            return
        for e in edges:
            self._reset_edge(e)
        for dn_id in decs:
            proto.remove_decision_node(dn_id)
        for op_id in ops:
            proto.remove_op_node(op_id)
        if rows:
            proto.remove_rows(rows)
        self.rebuild()

    def _reset_edge(self, edge):
        proto = self.protocol
        kind = edge.payload[0]
        if kind == "flow":
            row = proto.row_by_id(edge.payload[1])
            if row is not None:
                row.next_target = NEXT
        elif kind == "outcome":
            dn = proto.decision_node_by_id(edge.payload[1])
            if dn is not None:
                dn.routes.pop(edge.payload[2], None)
        elif kind == "feed":
            op = proto.op_node_by_id(edge.payload[1])
            if op is not None:
                pair = (edge.payload[2], edge.payload[3])
                if pair in op.inputs:
                    op.inputs.remove(pair)
        elif kind == "op":
            op = proto.op_node_by_id(edge.payload[1])
            if op is not None:
                op.target = None

    def edge_menu(self, edge, screen_pos):
        menu = QMenu(self)
        menu.addAction("Delete route",
                       lambda: (self._reset_edge(edge), self.rebuild()))
        menu.exec(screen_pos)

    def rename_row(self, row_id):
        row = self.protocol.row_by_id(row_id)
        if row is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename", "Name:", text=row.name)
        if ok and name.strip():
            row.name = name.strip()
            self.rebuild()

    def row_menu(self, row_id, screen_pos):
        row = self.protocol.row_by_id(row_id)
        if row is None:
            return
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_row(row_id))
        if not row.is_group:
            node = self.scene.row_items.get(row_id)
            if node is not None and node.plus is not None:
                menu.addAction(
                    "Add shape…",
                    lambda: self.open_shape_palette(
                        row_id, screen_pos, None))
        else:
            menu.addAction("Ungroup",
                           lambda: (self.protocol.ungroup(row_id),
                                    self.rebuild()))
        menu.addSeparator()
        menu.addAction(
            "Delete",
            lambda: (self.scene.clearSelection(),
                     self.scene.row_items[row_id].setSelected(True),
                     self.delete_selected()))
        menu.exec(screen_pos)

    def decision_menu(self, dn_id, screen_pos):
        dn = self.protocol.decision_node_by_id(dn_id)
        if dn is None:
            return
        menu = QMenu(self)
        a1 = menu.addAction("Always prompt")
        a1.setCheckable(True)
        a1.setChecked(dn.mode == "prompt" and dn.auto_after is None)
        a1.triggered.connect(
            lambda _=False: self._set_decision_mode(dn, "prompt", None))
        a2 = menu.addAction("Prompt first N times, then auto…")
        a2.setCheckable(True)
        a2.setChecked(dn.mode == "prompt" and dn.auto_after is not None)
        a2.triggered.connect(lambda _=False: self._ask_auto_after(dn))
        a3 = menu.addAction("Auto (never prompt)")
        a3.setCheckable(True)
        a3.setChecked(dn.mode == "auto")
        a3.triggered.connect(
            lambda _=False: self._set_decision_mode(dn, "auto", None))
        menu.addSeparator()
        menu.addAction(
            "Delete shape",
            lambda: (self.protocol.remove_decision_node(dn_id),
                     self.rebuild()))
        menu.exec(screen_pos)

    def _set_decision_mode(self, dn, mode, auto_after):
        dn.mode = mode
        dn.auto_after = auto_after
        self.rebuild()

    def _ask_auto_after(self, dn):
        n, ok = QInputDialog.getInt(
            self, "Auto after N prompts",
            "Prompt this many times per run, then answer automatically\n"
            "with the default outcome:",
            dn.auto_after or 3, 1, 99)
        if ok:
            self._set_decision_mode(dn, "prompt", n)

    def op_menu(self, op_id, screen_pos):
        op = self.protocol.op_node_by_id(op_id)
        if op is None:
            return
        menu = QMenu(self)
        other = "or" if op.kind == "and" else "and"
        menu.addAction(
            f"Convert to {other.upper()}",
            lambda: (setattr(op, "kind", other), self.rebuild()))
        menu.addSeparator()
        menu.addAction(
            "Delete shape",
            lambda: (self.protocol.remove_op_node(op_id), self.rebuild()))
        menu.exec(screen_pos)

    def blank_menu(self, screen_pos):
        ids = self.scene.selected_row_ids()
        menu = QMenu(self)
        group = menu.addAction("Group selected…",
                               lambda: self.group_selected())
        group.setEnabled(self.protocol.can_group(ids))
        ungroup = menu.addAction("Ungroup", self.ungroup_selected)
        row = self.protocol.row_by_id(ids[0]) if len(ids) == 1 else None
        ungroup.setEnabled(row is not None and row.is_group)
        menu.exec(screen_pos)

    # ------------------------------------------------------------------
    # grouping
    # ------------------------------------------------------------------

    def group_selected(self):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't regroup while the protocol is running.", 5000)
            return
        ids = self.scene.selected_row_ids()
        if not self.protocol.can_group(ids):
            self.statusBar().showMessage(
                "Select a contiguous run of sibling rows to group "
                "(drag a box around them or Ctrl-click).", 6000)
            return
        name, ok = QInputDialog.getText(
            self, "Group selected rows", "Group name:", text="Group")
        if not ok:
            return
        members = [self.protocol.row_by_id(i) for i in ids]
        cx = sum(m.pos[0] for m in members) / len(members)
        cy = sum(m.pos[1] for m in members) / len(members)
        group = self.protocol.group_rows(ids, name=(name.strip() or "Group"))
        if group is not None:
            group.pos = (cx - 30, cy - 30)
        self.rebuild()

    def ungroup_selected(self):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't regroup while the protocol is running.", 5000)
            return
        ids = self.scene.selected_row_ids()
        done = False
        for rid in ids:
            row = self.protocol.row_by_id(rid)
            if row is not None and row.is_group:
                self.protocol.ungroup(rid)
                done = True
        if done:
            self.rebuild()
        else:
            self.statusBar().showMessage(
                "Select a group node to ungroup.", 5000)

    # ------------------------------------------------------------------
    # toolbar handlers
    # ------------------------------------------------------------------

    def _on_run(self):
        if self.executor.is_running():
            return
        self.log.clear()
        self.executor.start(repeats=self.repeats.value())

    def _on_pause_toggled(self, checked):
        if not self.executor.is_running():
            return
        if checked:
            self.executor.pause()
        else:
            self.executor.resume()

    def _sync_pause(self, paused):
        self.pause_action.blockSignals(True)
        self.pause_action.setChecked(paused)
        self.pause_action.blockSignals(False)

    def _on_add_step(self):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't add steps while the protocol is running.", 5000)
            return
        leaves = self.protocol.leaves()
        step = self.protocol.add_step(
            f"Step {len(leaves) + 1}",
            after_id=leaves[-1].id if leaves else None)
        if leaves:
            prev = leaves[-1]
            step.pos = (prev.pos[0], prev.pos[1] + 90)
        self.rebuild()

    def _arrange(self, orientation, rebuild=True):
        """Clean layout: rows in tree order (indented by depth), each
        step's decision shapes in a column beside/below it, AND shapes
        one lane further out."""
        proto = self.protocol
        shape_count = {}
        if orientation == "vertical":
            for i, (row, depth) in enumerate(proto.iter_rows()):
                row.pos = (60 + depth * 46, 40 + i * (36 + 30))
            for dn in proto.decision_nodes:
                step = proto.row_by_id(dn.step_id)
                if step is None:
                    continue
                k = shape_count.get(dn.step_id, 0)
                shape_count[dn.step_id] = k + 1
                dn.pos = (step.pos[0] + NODE_W + 150,
                          step.pos[1] - 8 + k * 78)
        else:
            for i, (row, depth) in enumerate(proto.iter_rows()):
                row.pos = (60 + i * (NODE_W + 90), 60 + depth * 70)
            for dn in proto.decision_nodes:
                step = proto.row_by_id(dn.step_id)
                if step is None:
                    continue
                k = shape_count.get(dn.step_id, 0)
                shape_count[dn.step_id] = k + 1
                dn.pos = (step.pos[0] - 20 + k * 40,
                          step.pos[1] + 170 + k * 78)
        for op in proto.op_nodes:
            dns = [proto.decision_node_by_id(i[0]) for i in op.inputs]
            dns = [d for d in dns if d is not None]
            if dns:
                cx = sum(d.pos[0] for d in dns) / len(dns)
                cy = sum(d.pos[1] for d in dns) / len(dns)
                op.pos = (cx + DEC_W + 90, cy + 20)
        if rebuild:
            self.rebuild()
            self.view.fit_all()

    def _on_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save protocol", "branching_protocol.json",
            "JSON (*.json)")
        if path:
            with open(path, "w") as f:
                json.dump(self.protocol.to_dict(), f, indent=2)
            self.statusBar().showMessage(f"Saved {path}", 5000)

    def _on_load(self):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Stop the run before loading a protocol.", 5000)
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load protocol", "", "JSON (*.json)")
        if path:
            with open(path) as f:
                self.protocol.load_dict(json.load(f))
            self.rebuild()
            self.view.fit_all()

    # ------------------------------------------------------------------
    # executor signal handlers (GUI thread — Qt queued the emits)
    # ------------------------------------------------------------------

    def _on_started(self):
        self.run_action.setEnabled(False)
        self.pause_action.setEnabled(True)
        self.stop_action.setEnabled(True)

    def _on_terminal(self, what):
        self.scene.clear_run_states()
        self.run_action.setEnabled(True)
        self.pause_action.setEnabled(False)
        self._sync_pause(False)
        self.stop_action.setEnabled(False)
        self.statusBar().showMessage(f"Protocol {what}", 8000)
        if self._active_dialog is not None:
            self._active_dialog.reject()

    def _on_step_started(self, step_id, n, total):
        self.scene.clear_run_states()
        self.scene.set_row_state(step_id, "active")
        step = self.protocol.row_by_id(step_id)
        if step:
            self.statusBar().showMessage(
                f"Running step {n}/{total}: {step.name}")

    def _on_decision_pending(self, pending):
        dn = pending.decision_node
        if dn is not None:
            self.scene.set_decision_state(dn.id, True)
        else:
            self.scene.set_row_state(pending.step.id, "deciding")
        dialog = DecisionDialog(pending, self)
        self._active_dialog = dialog
        dialog.exec()
        self._active_dialog = None
        remember = dialog.remember.isChecked()
        pending.resolve(dialog.outcome(), remember)
        if dn is not None:
            self.scene.set_decision_state(dn.id, False)
        self.scene.set_row_state(pending.step.id, "active")
        if remember:
            self.scene.rebuild()   # shape (possibly minted) shows [auto]

    def _append_log(self, msg):
        self.log.appendPlainText(msg)

    # ------------------------------------------------------------------
    # table <-> model <-> canvas sync (leaves only)
    # ------------------------------------------------------------------

    def _rebuild_table(self):
        self._updating_table = True
        try:
            cols = self.columns
            leaves = self.protocol.leaves()
            self.table.clear()
            self.table.setColumnCount(1 + len(cols))
            self.table.setHorizontalHeaderLabels(
                ["Step"] + [c.model.col_name for c in cols])
            self.table.setRowCount(len(leaves))
            for r, step in enumerate(leaves):
                self.table.setItem(r, 0, QTableWidgetItem(step.name))
                for c, col in enumerate(cols, start=1):
                    v = col.model.get_value(step)
                    if col.model.kind == "bool":
                        item = QTableWidgetItem()
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable
                                      | Qt.ItemIsUserCheckable)
                        item.setCheckState(
                            Qt.Checked if v else Qt.Unchecked)
                    else:
                        item = QTableWidgetItem(str(v))
                    self.table.setItem(r, c, item)
            self.table.resizeColumnsToContents()
        finally:
            self._updating_table = False

    def _on_table_edit(self, item):
        if self._updating_table:
            return
        leaves = self.protocol.leaves()
        r, c = item.row(), item.column()
        if r >= len(leaves):
            return
        step = leaves[r]
        if c == 0:
            if item.text().strip():
                step.name = item.text().strip()
            self.scene.rebuild()
            return
        col = self.columns[c - 1]
        if col.model.kind == "bool":
            col.model.set_value(step, item.checkState() == Qt.Checked)
        else:
            try:
                value = (int(float(item.text()))
                         if col.model.kind == "int"
                         else float(item.text()))
            except ValueError:
                self._updating_table = True
                item.setText(str(col.model.get_value(step)))
                self._updating_table = False
                return
            value = min(max(value, col.model.minimum), col.model.maximum)
            col.model.set_value(step, value)
            self._updating_table = True
            item.setText(str(value))
            self._updating_table = False
        # Values can flip a decision active/inactive — refresh shapes.
        self.scene.rebuild()

    def _on_scene_selection(self):
        if self._syncing_selection:
            return
        ids = self.scene.selected_row_ids()
        if not ids:
            return
        leaves = self.protocol.leaves()
        for i, leaf in enumerate(leaves):
            if leaf.id == ids[0]:
                self._syncing_selection = True
                self.table.selectRow(i)
                self._syncing_selection = False
                return

    def _on_table_selection(self):
        if self._syncing_selection:
            return
        rows = {i.row() for i in self.table.selectedIndexes()}
        if len(rows) != 1:
            return
        leaves = self.protocol.leaves()
        row = rows.pop()
        if row >= len(leaves):
            return
        node = self.scene.row_items.get(leaves[row].id)
        if node is not None:
            self._syncing_selection = True
            self.scene.clearSelection()
            node.setSelected(True)
            self.view.centerOn(node)
            self._syncing_selection = False
