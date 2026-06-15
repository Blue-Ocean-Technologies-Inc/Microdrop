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

    def __init__(self, handler, hook_name, row, cause):
        self.handler = handler
        self.hook_name = hook_name
        self.row = row
        self.cause = cause
        # Column handlers carry their model (wired by Column.traits_init);
        # execution-only lifecycle handlers have none — fall back to the
        # handler class name, then a generic label.
        model = getattr(handler, "model", None)
        # The display label for the failing handler. Stored so consumers (the
        # protocol-error dialog) reuse it instead of re-deriving from the
        # handler — a single source of truth.
        self.col_label = (
            getattr(model, "col_name", "")
            or getattr(model, "col_id", "")
            or type(handler).__name__
            or "handler"
        )
        col_label = self.col_label
        if row is not None:
            dotted = ".".join(str(i + 1) for i in (getattr(row, "path", ()) or ()))
            name = getattr(row, "name", "") or ""
            where = f"Step {dotted} {name!r}".rstrip()
        else:
            where = "protocol"
        super().__init__(
            f"{where} — {col_label!r} failed during {hook_name}: {cause}"
        )
