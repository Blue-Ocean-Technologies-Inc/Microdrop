import time
from pyface.qt.QtCore import QObject, Signal


class ProtocolRunnerWorker(QObject):
    """
    Worker object meant to run in a separate QThread.
    """

    # Signals to update the UI
    step_started = Signal(object)  # Emits the Row object
    step_finished = Signal(object)
    protocol_finished = Signal()
    protocol_started = Signal()

    def __init__(self, root_node, columns):
        super().__init__()
        self.root_node = root_node
        self.columns = columns
        self._is_running = False
        self._context = {}  # Shared memory for the run

    def _get_flattened_rows(self, node):
        """Recursively get all ActionRows (skip Groups for execution)."""
        rows = []
        # specific implementation depends on your Row structure
        # assuming node.children exists
        if hasattr(node, "children"):
            for child in node.children:
                rows.extend(self._get_flattened_rows(child))
        else:
            # It's an action step
            rows.append(node)
        return rows

    def run(self):
        self._is_running = True
        self.protocol_started.emit()
        self._context = {}

        rows = self._get_flattened_rows(self.root_node)

        for row in rows:

            # UI Update: Highlight Row
            self.step_started.emit(row)

            # 3. Execution
            print(f"Running Step: {row.id}\nDuration: {row.duration_s}")
            self._execute_step(row)
            time.sleep(row.duration_s)

            self.step_finished.emit(row)

        self.protocol_finished.emit()

    def _execute_step(self, row):
        """Run execution logic for all columns on this step."""

        # A. Pre-step hooks (if you need them separate)

        # B. Column Execution
        for col in self.columns:
            col.handler.on_run_step(row, self._context)

        print("-" * 100)

        # C. Post-step hooks

    def stop(self):
        self._is_running = False
