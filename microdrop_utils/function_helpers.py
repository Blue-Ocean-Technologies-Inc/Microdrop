import inspect

def call_safely(func, *args, **maybe_kwargs):
    '''
    Call a function safely, by filtering out the kwargs that are not in the function signature.
    For example, if the function signature is:
    def func(a, b, c=None):
        pass
    Then the kwargs will be filtered to only include a, b, and c.
    If the function signature is:
    def func(a, b):
        pass
    Then the kwargs will be filtered to only include a and b.

    Can be called like:
    call_safely(func, 1, 2, c=3) # Same as func(1, 2, c=3)
    call_safely(func, 1, 2) # Same as func(1, 2)
    call_safely(func, 1, 2, c=3, d=4) # Same as func(1, 2, c=3)
    call_safely(func, 1, 2, d=4) # Same as func(1, 2)

    without func's signature having c or d, but if it does, it will work as expected.
    '''
    sig = inspect.signature(func)
    filtered = {k: v for k, v in maybe_kwargs.items() if k in sig.parameters}
    return func(*args, **filtered)