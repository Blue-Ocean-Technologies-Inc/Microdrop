"""Dramatiq listener actor + active-step pointer.

The actor itself receives every message published on any topic the
plugin's start() method aggregated from contributed handlers'
wait_for_topics. It routes payloads into the active step's mailbox via
``route_to_active_step`` — the same function tests can call directly to
bypass Dramatiq.

Only one protocol runs at a time, so a single module-level pointer is
enough. set/clear are guarded by a lock so the listener thread and the
executor's main loop don't see a torn read on the pointer transition
between steps.
"""

import threading
from typing import Optional

import dramatiq

from pluggable_protocol_tree.execution.step_context import StepContext


_active_step_ctx: Optional[StepContext] = None
_active_lock = threading.Lock()


def set_active_step(step_ctx: StepContext) -> None:
    """Called by the executor at the start of each step (before any
    hook runs)."""
    global _active_step_ctx
    with _active_lock:
        _active_step_ctx = step_ctx


def clear_active_step() -> None:
    """Called by the executor at the end of each step. Subsequent
    incoming messages on what *was* the step's topics are dropped
    silently until the next set_active_step()."""
    global _active_step_ctx
    with _active_lock:
        _active_step_ctx = None


def get_active_step() -> Optional[StepContext]:
    """For tests + the dramatiq actor."""
    with _active_lock:
        return _active_step_ctx


def route_to_active_step(topic: str, payload) -> None:
    """Deposit a payload into the active step's mailbox for ``topic``.
    Drops silently if no protocol is running, or if the active step
    didn't pre-open a mailbox for ``topic``.

    Direct entry point for both the dramatiq actor and unit tests.
    """
    ctx = get_active_step()
    if ctx is None:
        return
    ctx.deposit(topic, payload)


@dramatiq.actor(actor_name="pluggable_protocol_tree_executor_listener",
                queue_name="default")
def executor_listener(message: str, topic: str, timestamp: float = None) -> None:
    """Receives every message routed by message_router_actor on any
    topic the plugin aggregated from contributed handlers'
    wait_for_topics. Signature mirrors the project's message-router
    contract: ``(message, topic, timestamp)`` — see
    DramatiqControllerBase._listener_actor_default for reference.

    The payload is whatever ``publish_message(message=..., topic=...)``
    sent, after str()-conversion via TimestampedMessage. Handlers that
    publish JSON-encoded dicts json.loads() the result on the
    receiving side.
    """
    route_to_active_step(topic, message)
