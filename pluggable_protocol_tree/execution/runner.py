import json
import time
import dramatiq
from traits.api import HasTraits, Instance, Any, List, Str
from PySide6.QtCore import Signal, QObject

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor
)
from pluggable_protocol_tree.consts import LISTENER_NAME
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.interfaces.i_row import IGroupRow

logger = get_logger(__name__)

class ProtocolRunnerListener(HasTraits):
    """
    Helper class to handle Dramatiq listener setup.
    Passes messages to the worker via a thread-safe callback.
    """
    runner = Any()  # Reference to the worker instance
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = LISTENER_NAME

    def traits_init(self):
        logger.info(f"Initializing {self.listener_name}")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine
        )

    def listener_actor_routine(self, message, topic):
        """
        Callback triggered by the Dramatiq actor infrastructure.
        """
        if self.runner:
            self.runner.handle_message(topic, message)

class ProtocolRunnerWorkerSignals(QObject):
    """
    Worker object running in a separate thread.
    Uses standard Python threading.Condition for non-blocking synchronization.
    """

    # Signals to update the UI (Qt Signals are thread-safe)
    step_started = Signal(object)
    step_finished = Signal(object)
    protocol_finished = Signal()
    protocol_started = Signal()

class ProtocolRunnerWorker(HasTraits):
    """
    Worker object running in a separate thread.
    Uses standard Python threading.Condition for non-blocking synchronization.
    """

    root_node = Instance(IGroupRow)
    columns = List(IColumn)

    awaiting_step_tasks = List(Str)

    qsignals = Instance(ProtocolRunnerWorkerSignals)
    listener = Instance(ProtocolRunnerListener)


    def traits_init(self):

        self.awaiting_step_tasks = []

        # qt signals
        self.qsignals = ProtocolRunnerWorkerSignals()

        # Initialize the Dramatiq listener
        self.listener = ProtocolRunnerListener(runner=self)

    def _get_flattened_rows(self, node):
        """Recursively get all ActionRows."""
        rows = []
        if hasattr(node, "children"):
            for child in node.children:
                rows.extend(self._get_flattened_rows(child))
        else:
            rows.append(node)
        return rows

    def handle_message(self, topic, message):
        """
        Called by the listener when a Dramatiq message arrives.
        Updates state, and notifies the runner.
        """

        # Check if the topic matches any expected task
        match_index = -1
        for i, task in enumerate(self.awaiting_step_tasks):
            if task == json.dumps({"topic": topic, "message": message}):
                match_index = i
                break

        if match_index != -1:
            self.awaiting_step_tasks.pop(match_index)
            print(f"Task satisfied: {topic}")
            print("#Replies awaiting: ", len(self.awaiting_step_tasks))

        if len(self.awaiting_step_tasks) == 0:
            self.on_step_tasks_finished()


    def start_protocol(self):

        print("start protocol")

        self.qsignals.protocol_started.emit()

        self.rows_to_execute = self._get_flattened_rows(self.root_node)
        self.row_idx = 0

        self.start_step_execution()

    def start_step_execution(self):

        print("Start step execution")

        row = self.rows_to_execute[self.row_idx]

        # 1. UI Update
        self.qsignals.step_started.emit(row)
        print(f"Running Step: {row.id}")

        for col in self.columns:
            awaiting_task = col.handler.on_run_step(row)
            if awaiting_task is not None:
                self.awaiting_step_tasks.append(awaiting_task)

        if len(self.awaiting_step_tasks) == 0:
            self.on_step_tasks_finished()

    def on_step_tasks_finished(self):
        # 4. Duration Sleep
        # We can use the same condition variable for interruptible sleep

        row = self.rows_to_execute[self.row_idx]
        time.sleep(row.duration_s)
        self.qsignals.step_finished.emit(row)

        self.row_idx += 1

        if self.row_idx >= len(self.rows_to_execute):
            self.qsignals.protocol_finished.emit()

        else:
            self.start_step_execution()

    def stop(self):
        """
        Stops execution immediately.
        """
        pass
