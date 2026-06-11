import asyncio
import functools
import html
import threading
from typing import Any, Callable, TypeVar, cast

from microdrop_application.dialogs.pyface_wrapper import (
    error, escape_html_multiline, format_traceback_detail,
)
from microdrop_style.colors import DIALOG_ERROR_TEXT_COLOR
from microdrop_utils.datetime_helpers import TimestampedMessage
from logger.logger_service import get_logger

logger = get_logger(__name__)

T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


def attempt_func_execution_with_error_dialog(func):
    """Wrap a QWidget instance method so any uncaught exception is surfaced
    to the user as a styled error dialog instead of crashing the widget.

    The dialog uses the pyface_wrapper.error layout:
      * ``message``    — one-line summary: humanised operation name +
                         exception type. Plain text.
      * ``informative`` — HTML body: bold op name + red exception type +
                          escaped exception message.
      * ``detail``     — full traceback, collapsible preformatted.

    Also logs the exception with full traceback so the error is captured
    even when the user dismisses the dialog.

    Intended for top-level user-triggered UI actions (file open / save /
    import / browse-reports / etc.). Do NOT use on executor callbacks —
    those handle errors via the executor's own signal chain.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as exc:
            op_name = func.__name__.replace("_", " ").strip().title()
            logger.error(f"{op_name} failed: {exc}", exc_info=True)
            detail = format_traceback_detail(exc)
            cause = escape_html_multiline(str(exc) or "(no message)")
            informative = (
                f"<p style='margin:0 0 6px 0;'>"
                f"<b>{html.escape(op_name)}</b> failed.</p>"
                f"<p style='margin:0;color:{DIALOG_ERROR_TEXT_COLOR};'>"
                f"<b>{html.escape(type(exc).__name__)}:</b> {cause}</p>"
            )
            try:
                error(
                    self,
                    message=f"{op_name} failed: {type(exc).__name__}",
                    title=f"{op_name} Error",
                    informative=informative,
                    detail=detail,
                )
            except Exception as dialog_err:
                logger.error(
                    f"failed to show error dialog for {op_name}: "
                    f"{dialog_err}", exc_info=True)
            return None
    return wrapper


def debounce(wait_seconds: float = 0.5) -> Callable[[F], F]:
    """
    Decorator that will postpone a function's execution until after
    wait_seconds have elapsed since the last time it was invoked.

    Args:
        wait_seconds: Time in seconds to wait before executing the function

    Returns:
        Decorated function that will be debounced
    """
    def decorator(fn: F) -> F:
        timer: threading.Timer | None = None
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> None:
            nonlocal timer

            def call_it() -> None:
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    # Log the error but don't let it propagate to avoid breaking the timer
                    logger.warning(f"Error in debounced function {fn}: {e}", exc_info=True)

            with lock:
                if timer is not None:
                    timer.cancel()
                timer = threading.Timer(wait_seconds, call_it)
                timer.daemon = True
                timer.start()

        return cast(F, wrapped)
    return decorator


def debounce_async(wait_seconds: float = 0.5) -> Callable[[F], F]:
    """
    Async debounce decorator: delays coroutine until wait_seconds
    have passed since last invocation.

    Args:
        wait_seconds: Time in seconds to wait before executing the coroutine

    Returns:
        Decorated coroutine that will be debounced
    """
    def decorator(fn: F) -> F:
        task: asyncio.Task[Any] | None = None
        lock = asyncio.Lock()

        @functools.wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> None:
            nonlocal task

            async def call_it() -> None:
                try:
                    await fn(*args, **kwargs)
                except Exception as e:
                    # Log the error but don't let it propagate to avoid breaking the timer
                    logger.warning(f"Error in debounced async function {fn}: {e}",
                                   exc_info=True)

            async with lock:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                async def waiter() -> None:
                    try:
                        await asyncio.sleep(wait_seconds)
                        await call_it()
                    except asyncio.CancelledError:
                        pass

                task = asyncio.create_task(waiter())

        return cast(F, wrapped)
    return decorator


def timestamped_value(property_name: str) -> Callable[[F], F]:
    '''
    Decorator that will only run the method if the body is more recent than the current value. Should be used on callbacks of the form
    
    def callback(self, body: TimestampedMessage, *args, **kwargs)

    Args:
        property_name: The class attribute that stores the TimestampedMessage to be compared with the body and updated

    Returns:
        Decorated function that will only run the method if the body is more recent than the current value

    To force an update, pass force_update=True as a keyword argument to the method when calling it. You still need to pass a TimestampedMessage as the first argument, but the timestamp will be ignored.
    '''
    def decorator(method: F) -> F:
        @functools.wraps(method)
        def wrapped(self, body: TimestampedMessage,  *args, **kwargs) -> None:
            if body.is_after(getattr(self, property_name)):
                setattr(self, property_name, body)
                return method(self, body) # Note that we don't pass any args or kwargs to the method since we specify the function signature
            elif kwargs.get('force_update', False):
                return method(self, body)
            else:
                logger.info(f"Skipping {property_name} update because it is older than the last update")
        return wrapped
    return decorator