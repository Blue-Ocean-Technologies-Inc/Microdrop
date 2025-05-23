import asyncio
import functools
import time
from typing import Any, Callable, TypeVar, cast

T = TypeVar('T')

def debounce(wait_seconds: float = 0.5):
    """
    A decorator that debounces a function, ensuring it is only called once within
    the specified wait time period. If called multiple times, only the last call
    will be executed after the wait period.
    
    Args:
        wait_seconds (float): The time in seconds to wait before executing the
            function. Defaults to 0.5 seconds.
    
    Returns:
        Callable: The debounced function.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        last_called: float = 0
        timer: asyncio.TimerHandle | None = None
        
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            nonlocal last_called, timer
            
            current_time = time.time()
            if current_time - last_called < wait_seconds:
                # Cancel the previous timer if it exists
                if timer is not None:
                    timer.cancel()
                
                try:
                    # Use get_running_loop() which is more explicit about requirements
                    loop = asyncio.get_running_loop()
                    timer = loop.call_later(
                        wait_seconds,
                        lambda: asyncio.create_task(func(*args, **kwargs))
                    )
                except RuntimeError:
                    # If no event loop is running, fall back to synchronous execution
                    return await func(*args, **kwargs)
                return cast(T, None)
            
            last_called = current_time
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            nonlocal last_called, timer
            
            current_time = time.time()
            if current_time - last_called < wait_seconds:
                # Cancel the previous timer if it exists
                if timer is not None:
                    timer.cancel()
                
                try:
                    # Use get_running_loop() which is more explicit about requirements
                    loop = asyncio.get_running_loop()
                    timer = loop.call_later(
                        wait_seconds,
                        lambda: func(*args, **kwargs)
                    )
                except RuntimeError:
                    # If no event loop is running, execute immediately
                    return func(*args, **kwargs)
                return cast(T, None)
            
            last_called = current_time
            return func(*args, **kwargs)
        
        # Return the appropriate wrapper based on whether the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
