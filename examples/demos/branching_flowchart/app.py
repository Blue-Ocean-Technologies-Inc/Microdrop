"""Demo application shell.

Layout: flowchart canvas (left) | parameter table + run log (right).
The table plays the role of today's protocol grid — it only sets step
parameters (steps = the tree's leaves); the canvas owns the flow: step
order, group frames, placed decision shapes, AND/OR combiners, terminal
Stop/Finish nodes, and all routes.

Every model mutation snapshots the protocol first (Ctrl+Z / Ctrl+Shift+Z
undo/redo); node drags stage their snapshot on press and commit it on
release only if something actually moved.
"""

import json

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction, QBrush, QColor, QFont, QImage, QKeySequence, QPainter, QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QMainWindow, QMenu, QPlainTextEdit, QPushButton,
    QSpinBox, QSplitter, QToolBar, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .canvas import (
    BG_COLOR, DEC_W, FLOW_COLOR, KIND_COLORS, NODE_W, OP_COLORS,
    SPINE_COLOR, TETHER_COLOR, DecisionShapeItem, EdgeItem,
    FlowchartScene, FlowchartView, GroupFrameItem, OpNodeItem,
    StepNodeItem, TerminalNodeItem,
)
from .columns import make_demo_columns
from .executor import DemoExecutor
from .model import ABORT, END, NEXT, Protocol


class DecisionDialog(QDialog):
    """The runtime prompt: question + one colored button per outcome
    (keyboard 1..n; Esc = provider default), an optional unattended
    countdown that auto-picks the decision's auto answer, and 'don't ask
    again this run'."""

    def __init__(self, pending, parent=None, countdown_s=0):
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
        for idx, (outcome, target, desc, label) in enumerate(
                pending.options):
            color = KIND_COLORS.get(outcome.kind).name()
            btn = QPushButton(f"{label}  [{idx + 1}]\n→ {desc}")
            btn.setShortcut(QKeySequence(str(idx + 1)))
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

        self._countdown = 0
        self._timer = None
        if countdown_s > 0:
            dn = pending.decision_node
            self._auto_id = ((dn.auto_outcome if dn else None)
                             or pending.spec.default_outcome)
            auto_label = next(
                (label for outcome, _t, _d, label in pending.options
                 if outcome.id == self._auto_id),
                pending.spec.outcome_by_id(self._auto_id).label)
            self._countdown = countdown_s
            self._cd_label = QLabel()
            self._cd_label.setStyleSheet("color: #f59e0b;")
            layout.addWidget(self._cd_label)
            self._auto_label = auto_label
            self._tick()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(1000)

    def _tick(self):
        if self._countdown <= 0:
            self._pick(self._auto_id)
            return
        self._cd_label.setText(
            f"⏱ Unattended: auto-answering {self._auto_label!r} "
            f"in {self._countdown}s")
        self._countdown -= 1

    def _pick(self, outcome_id):
        if self._timer is not None:
            self._timer.stop()
        self.chosen = outcome_id
        self.accept()

    def outcome(self):
        # Esc / close = provider default, never a hang.
        return self.chosen or self.pending.spec.default_outcome


class _LineSample(QWidget):
    """A tiny line swatch for the legend."""

    def __init__(self, color, style=Qt.SolidLine, width=2.0):
        super().__init__()
        self.setFixedSize(30, 12)
        self._pen = QPen(color, width, style)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(self._pen)
        p.drawLine(2, self.height() // 2, self.width() - 2,
                   self.height() // 2)
        p.end()


class LegendWidget(QFrame):
    """Collapsible key for the canvas's visual vocabulary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "LegendWidget { background: rgba(17, 24, 39, 235); "
            "border: 1px solid #3b5b8a; border-radius: 6px; }"
            "QLabel { color: #cbd5e1; font-size: 11px; }")
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        rows = [
            (_LineSample(SPINE_COLOR, Qt.DashLine, 1.4), "table order (default)"),
            (_LineSample(FLOW_COLOR), "completion route"),
            (_LineSample(KIND_COLORS["positive"]),
             "outcome route (color = answer)"),
            (_LineSample(KIND_COLORS["negative"], Qt.DashLine),
             "chain — resolve that decision next"),
            (_LineSample(OP_COLORS["and"]), "AND / OR combined route"),
            (_LineSample(TETHER_COLOR, Qt.DotLine, 1.2),
             "decision shape ↔ its step"),
            (None, "defaults:  ↻ retry   → next   ⏹ abort   ▦ finish"),
            (None, "bright edge = route just taken (trail)"),
        ]
        for r, (sample, text) in enumerate(rows):
            if sample is not None:
                grid.addWidget(sample, r, 0)
            grid.addWidget(QLabel(text), r, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "MicroDrop — branching protocol flowchart (standalone UX demo)")
        self.resize(1360, 800)

        self.columns = make_demo_columns()
        self.protocol = Protocol(self.columns)
        self._seed_protocol()

        self._undo_stack = []
        self._redo_stack = []
        self._staged_move = None

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
        s.route_taken.connect(lambda key: self.scene.flash_route(key))
        s.canvas_note.connect(lambda tid, txt: self.scene.toast(tid, txt))
        s.log.connect(self._append_log)

        self.scene = FlowchartScene(self, self.protocol)
        self.view = FlowchartView(self.scene)
        self.scene.selectionChanged.connect(self._on_scene_selection)
        self._recent_steps = []

        # The parameter grid mirrors the protocol TREE: groups are parent
        # rows (with their Reps editable), steps are children — same
        # structure as the real protocol tree. Expanding/collapsing a
        # group here collapses its frame on the canvas and vice versa.
        self.table = QTreeWidget()
        self.table.setIndentation(16)
        self.table.setUniformRowHeights(True)
        self.table.itemChanged.connect(self._on_table_edit)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table.itemExpanded.connect(
            lambda it: self._on_tree_toggled(it, False))
        self.table.itemCollapsed.connect(
            lambda it: self._on_tree_toggled(it, True))
        self._tree_items = {}
        self._running_row_id = None
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

        self.legend = LegendWidget(self.view)
        self.view.on_resized = self._place_legend

        QShortcut(QKeySequence.Undo, self, self.undo)
        QShortcut(QKeySequence.Redo, self, self.redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.redo)

        self._arrange("vertical", rebuild=False)
        self.rebuild()
        self.view.fit_all()
        self._place_legend()
        self.statusBar().showMessage(
            "＋ on a step: add decision/AND/OR shapes · drag a port to a "
            "node, group frame, or ⏹/▦ · drag the ▾ title bar to move a "
            "group · Ctrl+Z undo · Ctrl+wheel zoom · middle-drag pan")

    # ------------------------------------------------------------------
    # undo / redo
    # ------------------------------------------------------------------

    def _snapshot(self):
        return json.dumps(self.protocol.to_dict())

    def push_undo(self, snap=None):
        self._undo_stack.append(snap if snap is not None
                                else self._snapshot())
        del self._undo_stack[:-80]
        self._redo_stack.clear()

    def stage_move_undo(self):
        self._staged_move = self._snapshot()

    def commit_move_undo(self):
        if self._staged_move is not None:
            self.push_undo(self._staged_move)
            self._staged_move = None

    def discard_move_undo(self):
        self._staged_move = None

    def undo(self):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't undo while the protocol is running.", 4000)
            return
        if not self._undo_stack:
            self.statusBar().showMessage("Nothing to undo.", 3000)
            return
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        self.statusBar().showMessage("Undo", 2000)

    def redo(self):
        if self.executor.is_running():
            return
        if not self._redo_stack:
            self.statusBar().showMessage("Nothing to redo.", 3000)
            return
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        self.statusBar().showMessage("Redo", 2000)

    def _restore(self, snap):
        self.protocol.load_dict(json.loads(snap))
        self.rebuild()

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

        tb.addWidget(QLabel(" Repeats: "))
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 99)
        tb.addWidget(self.repeats)

        self.follow_action = QAction("◎ Follow", self)
        self.follow_action.setCheckable(True)
        self.follow_action.setChecked(True)
        self.follow_action.setToolTip(
            "Keep the running step centered in the view")
        tb.addAction(self.follow_action)

        tb.addWidget(QLabel(" Unattended: "))
        self.unattended = QSpinBox()
        self.unattended.setRange(0, 600)
        self.unattended.setSuffix(" s")
        self.unattended.setSpecialValueText("off")
        self.unattended.setToolTip(
            "When set, prompts auto-answer their default after this many "
            "seconds — the run never stalls unattended")
        tb.addWidget(self.unattended)

        tb.addSeparator()
        undo_a = QAction("↶ Undo", self)
        undo_a.triggered.connect(lambda _=False: self.undo())
        tb.addAction(undo_a)
        redo_a = QAction("↷ Redo", self)
        redo_a.triggered.connect(lambda _=False: self.redo())
        tb.addAction(redo_a)

        tb.addSeparator()
        add = QAction("＋ Add step", self)
        add.triggered.connect(lambda _=False: self._on_add_step())
        tb.addAction(add)
        dup = QAction("⧉ Duplicate", self)
        dup.setShortcut(QKeySequence("Ctrl+D"))
        dup.triggered.connect(lambda _=False: self.duplicate_selected())
        tb.addAction(dup)
        delete = QAction("🗑 Delete", self)
        delete.setShortcut(QKeySequence.Delete)
        delete.triggered.connect(lambda _=False: self.delete_selected())
        tb.addAction(delete)
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
        self.legend_action = QAction("🗺 Legend", self)
        self.legend_action.setCheckable(True)
        self.legend_action.setChecked(True)
        self.legend_action.toggled.connect(
            lambda on: (self.legend.setVisible(on), self._place_legend()))
        tb.addAction(self.legend_action)

        tb.addSeparator()
        save = QAction("Save…", self)
        save.triggered.connect(lambda _=False: self._on_save())
        tb.addAction(save)
        load = QAction("Load…", self)
        load.triggered.connect(lambda _=False: self._on_load())
        tb.addAction(load)
        export = QAction("📷 Export…", self)
        export.setToolTip("Export the flowchart as a PNG image")
        export.triggered.connect(lambda _=False: self._on_export())
        tb.addAction(export)

    def _place_legend(self):
        if not self.legend.isVisible():
            return
        self.legend.adjustSize()
        self.legend.move(
            self.view.viewport().width() - self.legend.width() - 12,
            self.view.viewport().height() - self.legend.height() - 12)

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
        detect = p.add_step(
            "Droplet detect",
            {"voltage": 0.0, "duration_s": 0.4, "detect_fail": 35})
        mix_l = p.add_step("Mix left", {"voltage": 120.0, "duration_s": 0.6})
        mix_l.repetitions = 2      # per-STEP repeats, editable in the table
        mix_r = p.add_step("Mix right", {"voltage": 120.0, "duration_s": 0.6})
        inspect = p.add_step(
            "Operator inspect",
            {"voltage": 0.0, "duration_s": 0.3, "op_check": True,
             "detect_fail": 30})
        p.add_step("Collect to waste",
                   {"voltage": 100.0, "duration_s": 0.8})

        # Two groups: "Dispense & verify" ends with the droplet-detect
        # step; "Mix cycle" repeats twice per formal entry.
        grp_dispense = p.group_rows([dispense.id, detect.id],
                                    name="Dispense & verify")
        grp_mix = p.group_rows([mix_l.id, mix_r.id], name="Mix cycle")
        grp_mix.repetitions = 2

        # --- Dispense droplet: serial CHAIN + AND -----------------------
        # Volume check: silent auto-retry twice, then prompt.
        dn_vol = p.add_decision_node(dispense.id, "volume_check", (0, 0))
        dn_vol.routes["retry"] = dispense.id       # orange self-loop
        dn_vol.mode = "auto_first"
        dn_vol.auto_after = 2
        dn_vol.auto_outcome = "retry"
        # CHAIN (serial resolution): the operator confirm is only asked
        # AFTER a failed volume check is answered Continue — the dashed
        # "Continue → then" edge.
        dn_op = p.add_decision_node(dispense.id, "operator_check", (0, 0))
        dn_vol.routes["continue"] = dn_op.id
        # AND: volume Continue + operator Yes = manually verified — skip
        # the droplet-detect sensor check and enter the Mix group
        # formally (its ×2 passes still apply).
        op_and = p.add_op_node((0, 0), kind="and")
        op_and.inputs = [(dn_vol.id, "continue"), (dn_op.id, "yes")]
        op_and.target = grp_mix.id

        # --- Droplet detect: the group-restart scenario -----------------
        # Restart is routed to the GROUP NODE, so a missing droplet
        # formally re-enters the whole group (entry hooks + fresh pass
        # budget). Routing it to 'Dispense droplet' instead would just
        # re-run the steps with none of that.
        dn_det = p.add_decision_node(detect.id, "droplet_detect", (0, 0))
        dn_det.routes["restart"] = grp_dispense.id

        # --- Operator inspect: OR over two independent checks -----------
        # Both decisions fire in the same round (parallel — contrast with
        # the chained pair on Dispense). If EITHER the operator says No
        # OR the sensor sees no droplet, redo the whole dispense group.
        dn_iop = p.add_decision_node(inspect.id, "operator_check", (0, 0))
        dn_idet = p.add_decision_node(inspect.id, "droplet_detect", (0, 0))
        dn_idet.labels["restart"] = "Redo prep"    # custom button label
        op_or = p.add_op_node((0, 0), kind="or")
        op_or.inputs = [(dn_iop.id, "no"), (dn_idet.id, "restart")]
        op_or.target = grp_dispense.id
        # Tip: tick 'Operator check' on any OTHER step to see an
        # UNplaced decision — it still prompts with provider defaults.

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

    def _free_shape_pos(self, step, width=DEC_W, height=60):
        """A spot near the step that doesn't overlap existing shapes."""
        base_x = step.pos[0] + NODE_W + 90
        base_y = step.pos[1] - 10
        taken = ([tuple(d.pos) for d in self.protocol.decision_nodes]
                 + [tuple(o.pos) for o in self.protocol.op_nodes])
        for k in range(12):
            candidate = (base_x, base_y + k * 82)
            if all(abs(candidate[0] - t[0]) > width * 0.6
                   or abs(candidate[1] - t[1]) > height
                   for t in taken):
                return candidate
        return (base_x + 40, base_y + 12 * 82)

    def _place_decision(self, step, spec):
        self.push_undo()
        dn = self.protocol.add_decision_node(
            step.id, spec.id, self._free_shape_pos(step))
        self.rebuild()
        item = self.scene.dec_items.get(dn.id)
        if item is not None:
            self.scene.clearSelection()
            item.setSelected(True)

    def _place_op(self, step, kind="and"):
        self.push_undo()
        self.protocol.add_op_node(
            self._free_shape_pos(step, width=80), kind=kind)
        self.rebuild()

    def commit_port_drop(self, port, target):
        proto = self.protocol
        # Resolve the drop target to a route target id/sentinel.
        if isinstance(target, TerminalNodeItem):
            target_id = ABORT if target.kind == "stop" else END
        elif isinstance(target, GroupFrameItem):
            target_id = target.row.id
        elif isinstance(target, StepNodeItem):
            target_id = target.row.id
        else:
            target_id = None    # DecisionShapeItem / OpNodeItem handled below

        if port.role == "done":
            if target_id is None:
                return
            step = port.owner.row
            if target_id == step.id:
                self.statusBar().showMessage(
                    "A step's completion route can't loop onto itself — "
                    "use a decision outcome for retries.", 5000)
                return
            self.push_undo()
            step.next_target = target_id
            self._append_log(
                f"Routed completion of {step.name!r} → "
                f"{proto.describe_target(target_id)}")
        elif port.role == "outcome":
            dn = port.owner.dnode
            if isinstance(target, DecisionShapeItem):
                if target.dnode.step_id != dn.step_id:
                    self.statusBar().showMessage(
                        "Decisions can only chain to another decision of "
                        "the same step.", 6000)
                    return
                self.push_undo()
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
                        "An operator can only combine outcomes from the "
                        "same step's decisions.", 6000)
                    return
                pair = (dn.id, port.outcome_id)
                if pair in op.inputs:
                    return
                self.push_undo()
                op.inputs.append(pair)
                self._append_log(
                    f"Fed {port.owner.spec.title} / {port.outcome_id} "
                    f"into {op.kind.upper()}")
            elif target_id is not None:
                self.push_undo()
                dn.routes[port.outcome_id] = target_id
                self._append_log(
                    f"Routed {port.owner.spec.title} / {port.outcome_id} "
                    f"→ {proto.describe_target(target_id)}")
            else:
                return
        elif port.role == "opout":
            if target_id is None:
                return
            self.push_undo()
            op = port.owner.opnode
            op.target = target_id
            self._append_log(
                f"Routed {op.kind.upper()} → "
                f"{proto.describe_target(target_id)}")
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
        self.push_undo()
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
        rows = self.scene.selected_row_ids()
        if rows and self.executor.is_running():
            self.statusBar().showMessage(
                "Can't delete steps while the protocol is running.", 5000)
            rows = []
        if not (edges or decs or ops or rows):
            return
        self.push_undo()
        for e in edges:
            self._reset_edge(e)
        for dn_id in decs:
            proto.remove_decision_node(dn_id)
        for op_id in ops:
            proto.remove_op_node(op_id)
        if rows:
            proto.remove_rows(rows)
        self.rebuild()

    def delete_row(self, row_id):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't delete steps while the protocol is running.", 5000)
            return
        self.push_undo()
        self.protocol.remove_rows([row_id])
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
        # Outcome-carrying edges can rename their button/edge label.
        if edge.payload[0] == "outcome":
            menu.addAction(
                "Rename button label…",
                lambda: self.edit_outcome_label(edge.payload[1],
                                                edge.payload[2]))
        elif edge.payload[0] == "feed":
            menu.addAction(
                "Rename button label…",
                lambda: self.edit_outcome_label(edge.payload[2],
                                                edge.payload[3]))
        menu.addAction(
            "Delete route",
            lambda: (self.push_undo(), self._reset_edge(edge),
                     self.rebuild()))
        menu.exec(screen_pos)

    def edit_outcome_label(self, dn_id, outcome_id):
        dn = self.protocol.decision_node_by_id(dn_id)
        spec = self.protocol.spec_by_id(dn.decision_id) if dn else None
        if dn is None or spec is None:
            return
        outcome = spec.outcome_by_id(outcome_id)
        text, ok = QInputDialog.getText(
            self, "Button label",
            f"Custom label for {outcome.label!r}\n"
            f"(shown on the prompt button and the edge; empty resets):",
            text=dn.labels.get(outcome_id, ""))
        if not ok:
            return
        self.push_undo()
        if text.strip():
            dn.labels[outcome_id] = text.strip()
        else:
            dn.labels.pop(outcome_id, None)
        self.rebuild()

    def rename_row(self, row_id):
        row = self.protocol.row_by_id(row_id)
        if row is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename", "Name:", text=row.name)
        if ok and name.strip() and name.strip() != row.name:
            self.push_undo()
            row.name = name.strip()
            self.rebuild()

    def toggle_group_collapse(self, row_id):
        row = self.protocol.row_by_id(row_id)
        if row is None or not row.is_group:
            return
        self.push_undo()
        row.collapsed = not row.collapsed
        self.rebuild()

    def row_menu(self, row_id, screen_pos):
        row = self.protocol.row_by_id(row_id)
        if row is None:
            return
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_row(row_id))
        if not row.is_group:
            menu.addAction(
                "Add shape…",
                lambda: self.open_shape_palette(row_id, screen_pos, None))
            menu.addAction("Duplicate",
                           lambda: self._duplicate_one(row))
            menu.addAction("Repetitions…",
                           lambda: self._ask_group_reps(row))
        else:
            menu.addAction("Expand" if row.collapsed else "Collapse",
                           lambda: self.toggle_group_collapse(row_id))
            menu.addAction("Repetitions…",
                           lambda: self._ask_group_reps(row))
            menu.addAction(
                "Ungroup",
                lambda: (self.push_undo(), self.protocol.ungroup(row_id),
                         self.rebuild()))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.delete_row(row_id))
        menu.exec(screen_pos)

    def _duplicate_one(self, row):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't duplicate while the protocol is running.", 5000)
            return
        self.push_undo()
        self._duplicate_step(row)
        self.rebuild()

    def _ask_group_reps(self, row):
        if row.is_group:
            caption = ("Passes scheduled by a formal group entry\n"
                       "(fall-through or a route to the group node):")
        else:
            caption = ("Times this step runs in place on fall-through\n"
                       "(explicit routes override):")
        n, ok = QInputDialog.getInt(
            self, "Repetitions", caption, row.repetitions, 1, 99)
        if ok and n != row.repetitions:
            self.push_undo()
            row.repetitions = n
            self.rebuild()

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
        a2 = menu.addAction("Auto first N times, then prompt…")
        a2.setCheckable(True)
        a2.setChecked(dn.mode == "auto_first")
        a2.triggered.connect(
            lambda _=False: self._ask_auto_policy(dn, "auto_first"))
        a3 = menu.addAction("Prompt first N times, then auto…")
        a3.setCheckable(True)
        a3.setChecked(dn.mode == "prompt" and dn.auto_after is not None)
        a3.triggered.connect(
            lambda _=False: self._ask_auto_policy(dn, "prompt"))
        a4 = menu.addAction("Auto (never prompt)")
        a4.setCheckable(True)
        a4.setChecked(dn.mode == "auto")
        a4.triggered.connect(
            lambda _=False: self._pick_auto_outcome(dn, "auto", None))
        menu.addSeparator()
        spec = self.protocol.spec_by_id(dn.decision_id)
        if spec is not None:
            labels = menu.addMenu("Button labels")
            for outcome in spec.outcomes:
                labels.addAction(
                    f"{dn.label_for(outcome)}…",
                    lambda oid=outcome.id: self.edit_outcome_label(
                        dn_id, oid))
        menu.addAction(
            "Delete shape",
            lambda: (self.push_undo(),
                     self.protocol.remove_decision_node(dn_id),
                     self.rebuild()))
        menu.exec(screen_pos)

    def _set_decision_mode(self, dn, mode, auto_after):
        self.push_undo()
        dn.mode = mode
        dn.auto_after = auto_after
        self.rebuild()

    def _ask_auto_policy(self, dn, mode):
        """Ask for N, then which outcome the auto answer should be."""
        if mode == "auto_first":
            caption = ("Answer automatically the first N times per run,\n"
                       "then start prompting the user:")
        else:
            caption = ("Prompt this many times per run, then answer\n"
                       "automatically:")
        n, ok = QInputDialog.getInt(
            self, "Auto policy", caption, dn.auto_after or 3, 1, 99)
        if not ok:
            return
        self._pick_auto_outcome(dn, mode, n)

    def _pick_auto_outcome(self, dn, mode, auto_after):
        spec = self.protocol.spec_by_id(dn.decision_id)
        if spec is not None:
            labels = [o.label for o in spec.outcomes]
            current = dn.auto_outcome or spec.default_outcome
            current_ix = next(
                (k for k, o in enumerate(spec.outcomes)
                 if o.id == current), 0)
            label, ok = QInputDialog.getItem(
                self, "Auto answer",
                "Outcome to pick automatically:",
                labels, current_ix, False)
            if not ok:
                return
            dn.auto_outcome = next(
                o.id for o in spec.outcomes if o.label == label)
        self._set_decision_mode(dn, mode, auto_after)

    def op_menu(self, op_id, screen_pos):
        op = self.protocol.op_node_by_id(op_id)
        if op is None:
            return
        menu = QMenu(self)
        other = "or" if op.kind == "and" else "and"
        menu.addAction(
            f"Convert to {other.upper()}",
            lambda: (self.push_undo(), setattr(op, "kind", other),
                     self.rebuild()))
        menu.addSeparator()
        menu.addAction(
            "Delete shape",
            lambda: (self.push_undo(), self.protocol.remove_op_node(op_id),
                     self.rebuild()))
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
        self.push_undo()
        self.protocol.group_rows(ids, name=(name.strip() or "Group"))
        self.rebuild()

    def ungroup_selected(self):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't regroup while the protocol is running.", 5000)
            return
        ids = self.scene.selected_row_ids()
        groups = [rid for rid in ids
                  for row in [self.protocol.row_by_id(rid)]
                  if row is not None and row.is_group]
        if not groups:
            self.statusBar().showMessage(
                "Select a group to ungroup.", 5000)
            return
        self.push_undo()
        for rid in groups:
            self.protocol.ungroup(rid)
        self.rebuild()

    # ------------------------------------------------------------------
    # toolbar handlers
    # ------------------------------------------------------------------

    def _on_run(self):
        if self.executor.is_running():
            return
        self.log.clear()
        self.scene.clear_run_states()
        self._recent_steps = []
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
        self.push_undo()
        leaves = self.protocol.leaves()
        step = self.protocol.add_step(
            f"Step {len(leaves) + 1}",
            after_id=leaves[-1].id if leaves else None)
        if leaves:
            prev = leaves[-1]
            step.pos = (prev.pos[0], prev.pos[1] + 90)
        self.rebuild()

    def add_step_at(self, pos):
        """Double-click on blank canvas: add a step right there (appended
        at the end of the sequence)."""
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't add steps while the protocol is running.", 5000)
            return
        self.push_undo()
        leaves = self.protocol.leaves()
        step = self.protocol.add_step(
            f"Step {len(leaves) + 1}",
            after_id=leaves[-1].id if leaves else None)
        step.pos = pos
        self.rebuild()

    def duplicate_selected(self):
        if self.executor.is_running():
            self.statusBar().showMessage(
                "Can't duplicate while the protocol is running.", 5000)
            return
        steps = [row for rid in self.scene.selected_row_ids()
                 for row in [self.protocol.row_by_id(rid)]
                 if row is not None and not row.is_group]
        if not steps:
            self.statusBar().showMessage(
                "Select one or more steps to duplicate "
                "(groups can't be duplicated yet).", 5000)
            return
        self.push_undo()
        for row in steps:
            self._duplicate_step(row)
        self.rebuild()

    def _duplicate_step(self, row):
        """Copy a step with its values, repetitions, and decision shapes
        (routes remapped so self-loops and chains follow the copy)."""
        proto = self.protocol
        new = proto.add_step(f"{row.name} (copy)", dict(row.values),
                             after_id=row.id)
        new.repetitions = row.repetitions
        new.pos = (row.pos[0] + 40, row.pos[1] + 56)
        mapping = {}
        for dn in [d for d in proto.decision_nodes
                   if d.step_id == row.id]:
            c = proto.add_decision_node(
                new.id, dn.decision_id, (dn.pos[0] + 40, dn.pos[1] + 56))
            c.mode = dn.mode
            c.auto_after = dn.auto_after
            c.auto_outcome = dn.auto_outcome
            c.labels = dict(dn.labels)
            c.routes = dict(dn.routes)
            mapping[dn.id] = c.id
        for new_id in mapping.values():
            c = proto.decision_node_by_id(new_id)
            c.routes = {k: (new.id if v == row.id else mapping.get(v, v))
                        for k, v in c.routes.items()}

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export flowchart", "protocol_flowchart.png",
            "PNG (*.png)")
        if not path:
            return
        rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        scale = 2  # crisp on hi-dpi screens
        img = QImage(int(rect.width() * scale), int(rect.height() * scale),
                     QImage.Format_ARGB32)
        img.fill(BG_COLOR)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.scene.clearSelection()
        self.scene.render(painter, QRectF(img.rect()), rect)
        painter.end()
        img.save(path)
        self.statusBar().showMessage(f"Exported {path}", 5000)

    def _arrange(self, orientation, rebuild=True):
        """Clean layout: rows in tree order (indented by depth), each
        step's decision shapes in a column beside/below it, AND/OR shapes
        one lane further out. Group frames auto-fit their members."""
        if rebuild:
            self.push_undo()
        proto = self.protocol
        shape_count = {}
        if orientation == "vertical":
            # Each row is given enough vertical room for its decision
            # shapes, so shapes never overlap and group frames don't
            # collide with the next group.
            by_step = {}
            for dn in proto.decision_nodes:
                by_step.setdefault(dn.step_id, []).append(dn)
            y = 40
            for row, depth in proto.iter_rows():
                row.pos = (60 + depth * 46, y)
                shapes = by_step.get(row.id, [])
                for k, dn in enumerate(shapes):
                    dn.pos = (row.pos[0] + NODE_W + 150, y - 8 + k * 82)
                y += max(70, len(shapes) * 82 + 10)
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
        proto.terminal_pos = {}    # re-derive default spots
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
            self.push_undo()
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
        self._clear_running_row()
        self._recent_steps = []
        self.run_action.setEnabled(True)
        self.pause_action.setEnabled(False)
        self._sync_pause(False)
        self.stop_action.setEnabled(False)
        self.statusBar().showMessage(f"Protocol {what}", 8000)
        if self._active_dialog is not None:
            self._active_dialog.reject()

    def _on_step_started(self, step_id, n, total):
        # Decaying trail: the previous few steps stay faintly marked.
        for rid in self._recent_steps:
            self.scene.set_row_state(rid, "recent")
        self.scene.set_row_state(step_id, "active")
        self._recent_steps.insert(0, step_id)
        for rid in self._recent_steps[3:]:
            self.scene.set_row_state(rid, None)
        del self._recent_steps[3:]
        self._mark_running_row(step_id)
        step = self.protocol.row_by_id(step_id)
        if step:
            self.statusBar().showMessage(
                f"Running step {n}/{total}: {step.name}")
        if self.follow_action.isChecked():
            item = self.scene.display_for(step_id)
            if item is not None:
                self.view.centerOn(item)

    def _on_decision_pending(self, pending):
        dn = pending.decision_node
        anchor_item = None
        if dn is not None:
            self.scene.highlight_decision(dn.id, True)
            self.scene.set_decision_state(dn.id, True)
            anchor_item = (self.scene.dec_items.get(dn.id)
                           or self.scene.display_for(pending.step.id))
        else:
            self.scene.set_row_state(pending.step.id, "deciding")
            anchor_item = self.scene.display_for(pending.step.id)
        if anchor_item is not None:
            self.view.centerOn(anchor_item)

        dialog = DecisionDialog(pending, self,
                                countdown_s=self.unattended.value())
        self._position_dialog(dialog, anchor_item)
        self._active_dialog = dialog
        dialog.exec()
        self._active_dialog = None
        remember = dialog.remember.isChecked()
        pending.resolve(dialog.outcome(), remember)
        if dn is not None:
            self.scene.highlight_decision(dn.id, False)
            self.scene.set_decision_state(dn.id, False)
        self.scene.set_row_state(pending.step.id, "active")
        if remember:
            self.scene.rebuild()   # shape (possibly minted) shows [auto]

    def _position_dialog(self, dialog, item):
        """Open the prompt next to the shape it belongs to, so the
        candidate edges stay visible around it."""
        if item is None:
            return
        rect = self.view.mapFromScene(
            item.sceneBoundingRect()).boundingRect()
        top_right = self.view.viewport().mapToGlobal(rect.topRight())
        dialog.adjustSize()
        screen = self.screen().availableGeometry()
        x = min(top_right.x() + 16, screen.right() - dialog.width() - 8)
        y = min(max(screen.top() + 8, top_right.y() - 24),
                screen.bottom() - dialog.height() - 8)
        dialog.move(QPoint(x, y))

    def _append_log(self, msg):
        self.log.appendPlainText(msg)

    # ------------------------------------------------------------------
    # table <-> model <-> canvas sync (leaves only)
    # ------------------------------------------------------------------

    #: fixed columns before the contributed value columns
    _COL_NUM, _COL_NAME, _COL_REPS = 0, 1, 2

    def _rebuild_table(self):
        self._updating_table = True
        try:
            cols = self.columns
            self.table.clear()
            self._tree_items = {}
            self.table.setColumnCount(3 + len(cols))
            self.table.setHeaderLabels(
                ["#", "Step / Group", "Reps"]
                + [c.model.col_name for c in cols])
            group_font = QFont()
            group_font.setBold(True)

            def build(rows, parent, prefix):
                for idx, row in enumerate(rows, 1):
                    number = f"{prefix}{idx}"
                    item = QTreeWidgetItem()
                    item.setData(0, Qt.UserRole, row.id)
                    item.setText(self._COL_NUM, number)
                    item.setText(self._COL_NAME, row.name)
                    item.setText(self._COL_REPS, str(row.repetitions))
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                    if row.is_group:
                        item.setFont(self._COL_NAME, group_font)
                        for c in range(self.table.columnCount()):
                            item.setForeground(c, QBrush(QColor("#9db4d8")))
                    else:
                        for c, col in enumerate(cols, start=3):
                            v = col.model.get_value(row)
                            if col.model.kind == "bool":
                                item.setCheckState(
                                    c, Qt.Checked if v else Qt.Unchecked)
                            else:
                                item.setText(c, str(v))
                    if parent is None:
                        self.table.addTopLevelItem(item)
                    else:
                        parent.addChild(item)
                    self._tree_items[row.id] = item
                    if row.is_group:
                        build(row.children, item, number + ".")
                        item.setExpanded(not row.collapsed)

            build(self.protocol.rows, None, "")
            for c in range(self.table.columnCount()):
                self.table.resizeColumnToContents(c)
            if self._running_row_id is not None:
                self._mark_running_row(self._running_row_id)
        finally:
            self._updating_table = False

    def _on_tree_toggled(self, item, collapsed):
        """Expanding/collapsing a group row mirrors the canvas frame."""
        if self._updating_table:
            return
        row = self.protocol.row_by_id(item.data(0, Qt.UserRole))
        if row is None or not row.is_group or row.collapsed == collapsed:
            return
        row.collapsed = collapsed
        self.scene.rebuild()

    def _on_table_edit(self, item, column):
        if self._updating_table:
            return
        row = self.protocol.row_by_id(item.data(0, Qt.UserRole))
        if row is None:
            return

        def revert():
            self._updating_table = True
            self._rebuild_table()
            self._updating_table = False

        if column == self._COL_NUM:
            revert()                      # numbering is derived
            return
        if column == self._COL_NAME:
            name = item.text(column).strip()
            if name and name != row.name:
                self.push_undo()
                row.name = name
                self.rebuild()
            else:
                revert()
            return
        if column == self._COL_REPS:
            try:
                n = max(1, int(float(item.text(column))))
            except ValueError:
                revert()
                return
            if n != row.repetitions:
                self.push_undo()
                row.repetitions = n
                self.rebuild()
            else:
                revert()
            return
        # Value columns apply to steps only.
        if row.is_group:
            revert()
            return
        col = self.columns[column - 3]
        if col.model.kind == "bool":
            new = item.checkState(column) == Qt.Checked
            if bool(col.model.get_value(row)) == new:
                return
            self.push_undo()
            col.model.set_value(row, new)
        else:
            try:
                value = (int(float(item.text(column)))
                         if col.model.kind == "int"
                         else float(item.text(column)))
            except ValueError:
                revert()
                return
            value = min(max(value, col.model.minimum), col.model.maximum)
            if value == col.model.get_value(row):
                revert()
                return
            self.push_undo()
            col.model.set_value(row, value)
            self._updating_table = True
            item.setText(column, str(value))
            self._updating_table = False
        # Values can flip a decision active/inactive — refresh shapes.
        self.scene.rebuild()

    def _mark_running_row(self, row_id):
        # setBackground emits itemChanged — shield the edit handler.
        was = self._updating_table
        self._updating_table = True
        try:
            prev = self._tree_items.get(self._running_row_id)
            if prev is not None and self._running_row_id != row_id:
                for c in range(self.table.columnCount()):
                    prev.setBackground(c, QBrush())
            self._running_row_id = row_id
            item = self._tree_items.get(row_id)
            if item is not None:
                tint = QBrush(QColor(59, 130, 246, 70))
                for c in range(self.table.columnCount()):
                    item.setBackground(c, tint)
                self.table.scrollToItem(item)
        finally:
            self._updating_table = was

    def _clear_running_row(self):
        was = self._updating_table
        self._updating_table = True
        try:
            item = self._tree_items.get(self._running_row_id)
            if item is not None:
                for c in range(self.table.columnCount()):
                    item.setBackground(c, QBrush())
        finally:
            self._updating_table = was
        self._running_row_id = None

    def _on_scene_selection(self):
        if self._syncing_selection:
            return
        ids = self.scene.selected_row_ids()
        if not ids:
            return
        item = self._tree_items.get(ids[0])
        if item is not None:
            self._syncing_selection = True
            self.table.setCurrentItem(item)
            self._syncing_selection = False

    def _on_table_selection(self):
        if self._syncing_selection:
            return
        item = self.table.currentItem()
        if item is None:
            return
        node = self.scene.display_for(item.data(0, Qt.UserRole))
        if node is not None:
            self._syncing_selection = True
            self.scene.clearSelection()
            node.setSelected(True)
            self.view.centerOn(node)
            self._syncing_selection = False
