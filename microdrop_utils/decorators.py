import asyncio
import functools
import threading
from typing import Any, Callable, TypeVar, cast

T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


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
                    print(f"Error in debounced function: {e}")

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
                    print(f"Error in debounced async function: {e}")

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
