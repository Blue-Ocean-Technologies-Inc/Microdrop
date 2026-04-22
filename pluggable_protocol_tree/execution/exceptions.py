"""Execution-layer exceptions."""


class AbortError(Exception):
    """Raised inside ctx.wait_for() when the executor's stop_event fires.

    Hooks should let it propagate; the executor catches it at the bucket
    boundary, sets stop_event (idempotent), drains other in-flight hooks,
    and routes to the protocol_aborted or protocol_error terminal signal
    via _emit_terminal_signal().
    """
