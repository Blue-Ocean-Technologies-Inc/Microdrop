"""Execution-layer exceptions."""


class AbortError(Exception):
    """Raised inside ctx.wait_for() when the executor's stop_event fires.

    Hooks should let it propagate; the executor catches it at the bucket
    boundary, sets stop_event (idempotent), drains other in-flight hooks,
    and routes to the protocol_aborted or protocol_error terminal signal
    via _emit_terminal_signal().
    """


class StepExecutionError(Exception):
    """Wraps an exception raised by a column handler hook, annotating it
    with which step and column failed (and during which hook) so the
    protocol-error dialog can say *where* and *why* a run failed, not just
    surface the bare exception text.

    ``str(self)`` reads e.g.::

        Step 1.2 'Magnet engage' — 'Magnet' failed during on_step:
        Timed out after 10.0s waiting for 'dropbot/signals/magnet_applied' ...

    The original exception is preserved as ``self.cause`` and chained via
    ``raise ... from cause`` so the full traceback is still available.
    """

    def __init__(self, col, hook_name, row, cause):
        self.col = col
        self.hook_name = hook_name
        self.row = row
        self.cause = cause
        col_label = (
            getattr(getattr(col, "model", None), "col_name", "")
            or getattr(getattr(col, "model", None), "col_id", "")
            or "column"
        )
        if row is not None:
            dotted = ".".join(str(i + 1) for i in (getattr(row, "path", ()) or ()))
            name = getattr(row, "name", "") or ""
            where = f"Step {dotted} {name!r}".rstrip()
        else:
            where = "protocol"
        super().__init__(
            f"{where} — {col_label!r} failed during {hook_name}: {cause}"
        )
