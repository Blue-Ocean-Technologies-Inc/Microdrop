"""Headed demo for the compound column framework.

Builds a protocol tree with the existing PPT-3 builtins + the
synthetic enabled+count compound from enabled_count_compound.py.
Auto-populates 3 sample steps so the user can immediately verify:

  1. Two columns render ('Enabled' checkbox + 'Count' spinner) for the
     one compound contribution
  2. The Count cell is read-only when Enabled is unchecked (greyed out
     spinner that won't accept clicks)
  3. Toggling Enabled makes the Count cell editable
  4. Save -> reload via the toolbar's Save / Load buttons preserves
     both fields
  5. The compound handler's on_step fires exactly once per row (via
     the logged invocation count line)

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget_compound_demo
"""

import logging
import sys

import dramatiq

# Centralised middleware strip — see broker_server_helpers.
from microdrop_utils.broker_server_helpers import (
    remove_middleware_from_dramatiq_broker,
)
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QApplication, QMainWindow, QSplitter, QToolBar

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.enabled_count_compound import (
    make_enabled_count_compound,
)
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


logger = logging.getLogger(__name__)


class _CountingHandler(BaseCompoundColumnHandler):
    """Subclass of the demo's default handler that logs every on_step
    invocation count — so the user can verify the owner-field guard
    works (one log line per row, not two)."""
    _on_step_count = 0
    def on_step(self, row, ctx):
        type(self)._on_step_count += 1
        logger.info("[demo compound] on_step #%d for row %r",
                    type(self)._on_step_count, getattr(row, "name", "<?>"))


def _columns():
    cc = make_enabled_count_compound()
    cc.handler = _CountingHandler()
    cc.handler.model = cc.model
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(cc),
    ]


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPT-11 Demo — Compound Column Framework")
        self.resize(900, 500)

        self.manager = RowManager(columns=_columns())
        # Pre-populate so Run / save+load have something to work with.
        self.manager.add_step(values={
            "name": "Step 1: enabled, count=5",
            "duration_s": 0.2,
            "ec_enabled": True,
            "ec_count": 5,
        })
        self.manager.add_step(values={
            "name": "Step 2: disabled (count read-only)",
            "duration_s": 0.2,
            "ec_enabled": False,
            "ec_count": 0,
        })
        self.manager.add_step(values={
            "name": "Step 3: enabled, count=99",
            "duration_s": 0.2,
            "ec_enabled": True,
            "ec_count": 99,
        })

        self.widget = ProtocolTreeWidget(self.manager, parent=self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.widget)
        self.setCentralWidget(splitter)

        tb = QToolBar("Demo")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.manager.add_step())


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    app = QApplication.instance() or QApplication(sys.argv)
    w = DemoWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
