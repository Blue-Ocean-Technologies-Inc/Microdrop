"""ProtocolSession -- load a protocol JSON, build the engine, run it.

Wraps the (RowManager, ProtocolExecutor, optional Dramatiq routing)
trio so callers don't have to repeat the assembly code:

    from pluggable_protocol_tree.session import ProtocolSession

    with ProtocolSession.from_file('my_protocol.json',
                                   with_demo_hardware=True) as session:
        session.start()
        session.wait(timeout=30.0)

Column factories are resolved dynamically by walking the persistence-
recorded ``cls`` strings back to their ``make_*_column()`` factories
in the source module. Protocols stay portable across processes
without the caller having to mirror the builtins list -- as long as
the column's source package is importable.

For production use (real hardware), leave ``with_demo_hardware=False``
and have the hardware controller subscribe to ELECTRODES_STATE_CHANGE
externally. ``with_demo_hardware=True`` registers the in-process
demo responder and spins up a Dramatiq worker so the actuation
publish/wait_for handshake completes end-to-end without hardware
-- intended for demos, integration tests, and dry-runs.
"""

import importlib
import json
import logging
from typing import Callable, List, Optional

import dramatiq

from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models.row_manager import RowManager


logger = logging.getLogger(__name__)


class ColumnResolutionError(Exception):
    """Raised when a column class recorded in the protocol JSON can't
    be matched to a make_*_column factory in its source module."""


def resolve_columns(payload: dict) -> List[IColumn]:
    """Walk ``payload['columns']`` and instantiate each column from the
    recorded model class name.

    Convention: a column whose model lives in module ``M`` has a
    matching ``make_*_column`` factory in ``M`` that returns a
    ``Column`` with a model of that class. We iterate ``M``'s
    ``make_*`` functions, call each, and pick the one whose model is
    an instance of the recorded class.

    Raises ``ColumnResolutionError`` if any column can't be resolved.
    """
    columns: List[IColumn] = []
    for entry in payload.get("columns", []):
        cls_qualname = entry.get("cls")
        col_id = entry.get("id", "<unknown>")
        if not cls_qualname:
            raise ColumnResolutionError(
                f"column {col_id!r} has no 'cls' qualname in payload"
            )
        module_name, class_name = cls_qualname.rsplit(".", 1)
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise ColumnResolutionError(
                f"can't import {module_name!r} for column {col_id!r}: {e}"
            ) from e
        target_cls = getattr(module, class_name, None)
        if target_cls is None:
            raise ColumnResolutionError(
                f"module {module_name!r} has no class {class_name!r} "
                f"(needed for column {col_id!r})"
            )
        factory = _find_factory(module, target_cls)
        if factory is None:
            raise ColumnResolutionError(
                f"no make_*_column factory in {module_name!r} returns a "
                f"Column with model {class_name} (needed for column {col_id!r})"
            )
        columns.append(factory())
    return columns


def _purge_stale_subscribers(broker, router, topics) -> None:
    """For each topic, drop any subscribed actor whose name doesn't
    resolve in the current process's broker. Those are leftovers from
    earlier exited demo / GUI processes that registered actors which
    no longer exist; if left in place every publish fans out to them
    and the worker DLQs the message after a slow ActorNotFound walk."""
    for topic in topics:
        try:
            subs = router.message_router_data.get_subscribers_for_topic(topic)
        except Exception:
            continue
        for entry in subs:
            actor_name = entry[0] if isinstance(entry, tuple) else entry
            try:
                broker.get_actor(actor_name)
            except Exception:
                try:
                    router.message_router_data.remove_subscriber_from_topic(
                        topic=topic, subscribing_actor_name=actor_name,
                    )
                    logger.info("purged stale subscriber %s on %s",
                                actor_name, topic)
                except Exception:
                    logger.exception("failed to purge %s on %s",
                                     actor_name, topic)


def _find_factory(module, target_cls) -> Optional[Callable]:
    """Find a function in ``module`` that returns a Column whose model
    is an instance of ``target_cls``. Tries each ``make_*_column``
    candidate; returns the first match (None if none)."""
    for name in dir(module):
        if not name.startswith("make_"):
            continue
        fn = getattr(module, name)
        if not callable(fn):
            continue
        try:
            col = fn()
        except Exception:
            # Factory blew up at construction -- skip it; another
            # candidate in the same module may still match.
            continue
        model = getattr(col, "model", None)
        if model is not None and isinstance(model, target_cls):
            return fn
    return None


class ProtocolSession:
    """Bundle of {RowManager + ProtocolExecutor + Dramatiq routing}
    constructed from a saved protocol JSON file.

    Forwards the executor's control methods (``start``/``pause``/
    ``resume``/``stop``/``wait``) for convenience; use the ``executor``
    attribute directly for anything more exotic (signals, etc.).

    Use as a context manager so the in-process Dramatiq worker (if
    created via ``with_demo_hardware=True``) is stopped on exit even
    if the protocol crashes.
    """

    def __init__(self, manager: RowManager, executor: ProtocolExecutor,
                 *, router=None, worker=None):
        self.manager = manager
        self.executor = executor
        self._router = router
        self._worker = worker

    # --- factory ---

    @classmethod
    def from_file(cls, path: str, *,
                  columns: Optional[List[IColumn]] = None,
                  with_demo_hardware: bool = False) -> "ProtocolSession":
        """Load a protocol JSON and assemble the engine.

        ``path``: filesystem path to a .json file written by
            ``RowManager.to_json``.

        ``columns``: optional explicit list of column instances. When
            None (default), columns are resolved from the recorded
            ``cls`` qualnames -- works for any column whose source
            package is importable from the current process.

        ``with_demo_hardware``: when True, subscribe the in-process
            electrode_responder + executor_listener actors and start
            a Dramatiq worker so the publish/wait_for actuation
            handshake completes without real hardware. Best-effort:
            skips with a warning if Redis isn't reachable.
        """
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if columns is None:
            columns = resolve_columns(payload)
        manager = RowManager.from_json(payload, columns=columns)
        executor = ProtocolExecutor(row_manager=manager)
        router = worker = None
        if with_demo_hardware:
            router, worker = cls._setup_demo_hardware()
        return cls(manager, executor, router=router, worker=worker)

    @staticmethod
    def _setup_demo_hardware():
        """Subscribe the demo electrode_responder + executor_listener
        and start a Dramatiq worker. Also purges stale subscribers --
        actor names recorded in Redis whose actors aren't registered
        in this process -- so leftover GUI-demo subscriptions don't
        trigger an ActorNotFound storm that backpressures the queue.

        Best-effort -- returns ``(None, None)`` if setup fails
        (Redis down, etc.)."""
        try:
            from dramatiq import Worker
            from microdrop_utils.dramatiq_pub_sub_helpers import (
                MessageRouterActor,
            )
            from pluggable_protocol_tree.consts import (
                ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
            )
            from pluggable_protocol_tree.demos.electrode_responder import (
                DEMO_RESPONDER_ACTOR_NAME,
            )
            # Importing the listener module registers its dramatiq actor.
            from pluggable_protocol_tree.execution import (  # noqa: F401
                listener as _listener,
            )

            broker = dramatiq.get_broker()
            broker.flush_all()
            router = MessageRouterActor()
            wanted = (
                (ELECTRODES_STATE_CHANGE, DEMO_RESPONDER_ACTOR_NAME),
                (ELECTRODES_STATE_APPLIED,
                 "pluggable_protocol_tree_executor_listener"),
            )
            _purge_stale_subscribers(broker, router,
                                     {t for t, _ in wanted})
            for topic, actor in wanted:
                router.message_router_data.add_subscriber_to_topic(
                    topic=topic, subscribing_actor_name=actor,
                )
            worker = Worker(broker, worker_timeout=100)
            worker.start()
            return router, worker
        except Exception as e:
            logger.warning(
                "demo hardware setup failed (Redis not running?): %s -- "
                "the actuation handshake will time out at runtime", e,
            )
            return None, None

    # --- control forwarders ---

    def start(self) -> None:
        self.executor.start()

    def pause(self) -> None:
        self.executor.pause()

    def resume(self) -> None:
        self.executor.resume()

    def stop(self) -> None:
        self.executor.stop()

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self.executor.wait(timeout=timeout)

    # --- lifecycle ---

    def close(self) -> None:
        """Stop the in-process Dramatiq worker (if any). Idempotent."""
        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception:
                logger.exception("dramatiq worker stop failed")
            self._worker = None

    def __enter__(self) -> "ProtocolSession":
        return self

    def __exit__(self, *exc_info) -> bool:
        self.close()
        return False
