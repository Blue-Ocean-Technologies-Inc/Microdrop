"""Demo application shell.

Layout: flowchart canvas (left) | parameter table + run log (right).
The table plays the role of today's protocol grid — it only sets step
parameters; the canvas owns the flow. Both are views over the same
Protocol model and stay in sync.
"""

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QMainWindow, QMenu, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout,
)

from .canvas import KIND_COLORS, FlowchartScene, FlowchartView
from .columns import make_demo_columns
from .executor import DemoExecutor
from .model import Protocol


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
        step_lbl = QLabel(f"Step: <b>{pending.step.name}</b>")
        layout.addWidget(step_lbl)
        q = QLabel(pending.spec.question)
        q.setWordWrap(True)
        q.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(q)
        if pending.message:
            m = QLabel(pending.message)
            m.setWordWrap(True)
            m.setStyleSheet("color: #546e7a;")
            layout.addWidget(m)

        buttons = QHBoxLayout()
        for outcome, target, desc in pending.options:
            color = KIND_COLORS.get(outcome.kind, "#546e7a")
            btn = QPushButton(f"{outcome.label}\n→ {desc}")
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}; color: white; "
                f"padding: 8px 14px; border-radius: 5px; }}"
                f"QPushButton:hover {{ background: #263238; }}")
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
        self.resize(1280, 760)

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
            "font-family: monospace; font-size: 11px; background: #263238; "
            "color: #eceff1;")

        right = QSplitter(Qt.Vertical)
        right.addWidget(self.table)
        right.addWidget(self.log)
        right.setSizes([420, 280])
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.view)
        split.addWidget(right)
        split.setSizes([840, 440])
        self.setCentralWidget(split)

        self._build_toolbar()
        self._active_dialog = None

        self._auto_layout(rebuild=False)
        self.rebuild()
        self.view.fit_all()
        self.statusBar().showMessage(
            "Drag from a ▸ done-port or a colored outcome port onto a step "
            "to route it. Right-click nodes to configure prompts. "
            "Double-click to rename.")

    # ------------------------------------------------------------------
    # toolbar / actions
    # ------------------------------------------------------------------

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.run_action = QAction("▶ Run", self)
        self.run_action.triggered.connect(self._on_run)
        tb.addAction(self.run_action)

        self.pause_action = QAction("⏸ Pause", self)
        self.pause_action.setCheckable(True)
        self.pause_action.setEnabled(False)
        self.pause_action.toggled.connect(self._on_pause_toggled)
        tb.addAction(self.pause_action)

        self.stop_action = QAction("⏹ Stop", self)
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(self.executor.stop)
        tb.addAction(self.stop_action)

        tb.addSeparator()
        tb.addWidget(QLabel(" Repeats: "))
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 99)
        tb.addWidget(self.repeats)

        tb.addSeparator()
        add = QAction("＋ Add step", self)
        add.triggered.connect(self._on_add_step)
        tb.addAction(add)
        delete = QAction("🗑 Delete selected", self)
        delete.setShortcut(QKeySequence.Delete)
        delete.triggered.connect(self._on_delete_selected)
        tb.addAction(delete)
        layout_a = QAction("⌗ Auto-layout", self)
        # QAction.triggered carries a bool; don't let it land in rebuild=.
        layout_a.triggered.connect(lambda _=False: self._auto_layout())
        tb.addAction(layout_a)
        fit = QAction("⤢ Fit", self)
        fit.triggered.connect(self.view.fit_all)
        tb.addAction(fit)

        tb.addSeparator()
        save = QAction("Save…", self)
        save.triggered.connect(self._on_save)
        tb.addAction(save)
        load = QAction("Load…", self)
        load.triggered.connect(self._on_load)
        tb.addAction(load)

    # ------------------------------------------------------------------
    # seed protocol
    # ------------------------------------------------------------------

    def _seed_protocol(self):
        p = self.protocol
        p.add_step("Prime reservoir", {"voltage": 90.0, "duration_s": 0.8})
        dispense = p.add_step("Dispense droplet",
                              {"voltage": 110.0, "duration_s": 1.0,
                               "fail_pct": 50})
        mix = p.add_step("Mix 4×", {"voltage": 120.0, "duration_s": 1.5})
        inspect = p.add_step("Operator inspect",
                             {"voltage": 0.0, "duration_s": 0.3,
                              "op_check": True})
        p.add_step("Collect to waste", {"voltage": 100.0, "duration_s": 0.8})

        # Pre-wired customizations so the canvas shows the vocabulary:
        # a retry self-loop that stops prompting after 3 tries...
        cfg = dispense.cfg_for("volume_check")
        cfg.routes["retry"] = dispense.id
        cfg.auto_after = 3
        # ...and a cross-edge: operator says "no" -> go back and re-dispense.
        cfg2 = inspect.cfg_for("operator_check")
        cfg2.routes["no"] = dispense.id

    # ------------------------------------------------------------------
    # model mutation entry points (called by the scene too)
    # ------------------------------------------------------------------

    def rebuild(self):
        self.scene.rebuild()
        self._rebuild_table()

    def commit_route(self, src_port, target_step_id):
        step = src_port.node.step
        if src_port.role == "done":
            if target_step_id == step.id:
                self.statusBar().showMessage(
                    "A step's completion route can't loop onto itself — "
                    "use a decision outcome for retries.", 5000)
                return
            step.next_target = target_step_id
            self._append_log(
                f"Routed completion of {step.name!r} → "
                f"{self.protocol.describe_target(target_step_id)}")
        else:
            cfg = step.cfg_for(src_port.decision_id)
            cfg.routes[src_port.outcome_id] = target_step_id
            self._append_log(
                f"Routed {step.name!r} / {src_port.decision_id} / "
                f"{src_port.outcome_id} → "
                f"{self.protocol.describe_target(target_step_id)}")
        self.rebuild()

    def delete_items(self, edges, node_ids):
        if self.executor.is_running() and node_ids:
            self.statusBar().showMessage(
                "Can't delete steps while the protocol is running.", 5000)
            return
        for e in edges:
            step = self.protocol.step_by_id(e.src_step_id)
            if step is None:
                continue
            if e.src_key == ("done",):
                step.next_target = "__next__"
            elif e.src_key[0] == "outcome":
                cfg = step.decision_cfgs.get(e.src_key[1])
                if cfg:
                    cfg.routes.pop(e.src_key[2], None)
        for sid in node_ids:
            self.protocol.remove_step(sid)
        self.rebuild()

    def rename_step(self, step_id):
        step = self.protocol.step_by_id(step_id)
        if step is None:
            return
        name, ok = QInputDialog.getText(self, "Rename step", "Name:",
                                        text=step.name)
        if ok and name.strip():
            step.name = name.strip()
            self.rebuild()

    def node_menu(self, step_id, screen_pos):
        step = self.protocol.step_by_id(step_id)
        node = self.scene.node_by_id.get(step_id)
        if step is None or node is None:
            return
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_step(step_id))
        menu.addAction("Delete step",
                       lambda: self.delete_items([], [step_id]))
        for handler, spec in node.decisions:
            sub = menu.addMenu(f"{spec.title} prompt")
            cfg = step.decision_cfgs.get(spec.id)
            mode = cfg.mode if cfg else "prompt"
            auto_after = cfg.auto_after if cfg else None

            a1 = sub.addAction("Always prompt")
            a1.setCheckable(True)
            a1.setChecked(mode == "prompt" and auto_after is None)
            a1.triggered.connect(
                lambda _=False, s=step, d=spec.id: self._set_decision_mode(
                    s, d, "prompt", None))

            a2 = sub.addAction("Prompt first N times, then auto…")
            a2.setCheckable(True)
            a2.setChecked(mode == "prompt" and auto_after is not None)
            a2.triggered.connect(
                lambda _=False, s=step, d=spec.id: self._ask_auto_after(s, d))

            a3 = sub.addAction("Auto (never prompt)")
            a3.setCheckable(True)
            a3.setChecked(mode == "auto")
            a3.triggered.connect(
                lambda _=False, s=step, d=spec.id: self._set_decision_mode(
                    s, d, "auto", None))
        menu.exec(screen_pos)

    def _set_decision_mode(self, step, decision_id, mode, auto_after):
        cfg = step.cfg_for(decision_id)
        cfg.mode = mode
        cfg.auto_after = auto_after
        self.scene.refresh_nodes()

    def _ask_auto_after(self, step, decision_id):
        cfg = step.cfg_for(decision_id)
        n, ok = QInputDialog.getInt(
            self, "Auto after N prompts",
            "Prompt this many times per run, then answer automatically\n"
            "with the default outcome:",
            cfg.auto_after or 3, 1, 99)
        if ok:
            self._set_decision_mode(step, decision_id, "prompt", n)

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
        step = self.protocol.add_step(
            f"Step {len(self.protocol.steps) + 1}")
        # Drop it below the last node so it doesn't land on top of one.
        if len(self.protocol.steps) > 1:
            prev = self.protocol.steps[-2]
            step.pos = (prev.pos[0], prev.pos[1] + 280)
        self.rebuild()

    def _on_delete_selected(self):
        from .canvas import EdgeItem, StepNodeItem
        edges = [e for e in self.scene.selectedItems()
                 if isinstance(e, EdgeItem) and e.user]
        nodes = [n.step.id for n in self.scene.selectedItems()
                 if isinstance(n, StepNodeItem)]
        if edges or nodes:
            self.delete_items(edges, nodes)

    def _auto_layout(self, rebuild=True):
        per_row = 3
        for i, step in enumerate(self.protocol.steps):
            row, col = divmod(i, per_row)
            step.pos = (60 + col * 300, 60 + row * 300)
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
        self.scene.clear_step_states()
        self.run_action.setEnabled(True)
        self.pause_action.setEnabled(False)
        self._sync_pause(False)
        self.stop_action.setEnabled(False)
        self.statusBar().showMessage(f"Protocol {what}", 8000)
        if self._active_dialog is not None:
            self._active_dialog.reject()

    def _on_step_started(self, step_id, n, total):
        self.scene.clear_step_states()
        self.scene.set_step_state(step_id, "active")
        step = self.protocol.step_by_id(step_id)
        if step:
            self.statusBar().showMessage(
                f"Running step {n} ({step.name}) — {total} steps in table")

    def _on_decision_pending(self, pending):
        self.scene.set_step_state(pending.step.id, "deciding")
        dialog = DecisionDialog(pending, self)
        self._active_dialog = dialog
        dialog.exec()
        self._active_dialog = None
        pending.resolve(dialog.outcome(), dialog.remember.isChecked())
        self.scene.set_step_state(pending.step.id, "active")
        if dialog.remember.isChecked():
            self.scene.refresh_nodes()   # strip now shows [auto]

    def _append_log(self, msg):
        self.log.appendPlainText(msg)

    # ------------------------------------------------------------------
    # table <-> model <-> canvas sync
    # ------------------------------------------------------------------

    def _rebuild_table(self):
        self._updating_table = True
        try:
            cols = self.columns
            self.table.clear()
            self.table.setColumnCount(1 + len(cols))
            self.table.setHorizontalHeaderLabels(
                ["Step"] + [c.model.col_name for c in cols])
            self.table.setRowCount(len(self.protocol.steps))
            for r, step in enumerate(self.protocol.steps):
                name_item = QTableWidgetItem(step.name)
                self.table.setItem(r, 0, name_item)
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
        r, c = item.row(), item.column()
        if r >= len(self.protocol.steps):
            return
        step = self.protocol.steps[r]
        if c == 0:
            if item.text().strip():
                step.name = item.text().strip()
        else:
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
        self.scene.refresh_nodes()

    def _on_scene_selection(self):
        if self._syncing_selection:
            return
        from .canvas import StepNodeItem
        nodes = [n for n in self.scene.selectedItems()
                 if isinstance(n, StepNodeItem)]
        if not nodes:
            return
        idx = self.protocol.index_of(nodes[0].step.id)
        if idx is not None:
            self._syncing_selection = True
            self.table.selectRow(idx)
            self._syncing_selection = False

    def _on_table_selection(self):
        if self._syncing_selection:
            return
        rows = {i.row() for i in self.table.selectedIndexes()}
        if len(rows) != 1:
            return
        row = rows.pop()
        if row >= len(self.protocol.steps):
            return
        node = self.scene.node_by_id.get(self.protocol.steps[row].id)
        if node is not None:
            self._syncing_selection = True
            self.scene.clearSelection()
            node.setSelected(True)
            self.view.centerOn(node)
            self._syncing_selection = False
