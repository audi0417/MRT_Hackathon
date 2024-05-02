import time
from functools import wraps

import requests

def timed_cache(seconds=60, maxsize=128):
    def decorator(func):
        cached_results = {}
        cached_timestamps = {}

        @wraps(func)
        def wrapped(*args, **kwargs):
            key = (*args, *sorted(kwargs.items()))
            now = time.time()

            if key in cached_results:
                if now - cached_timestamps[key] < seconds:
                    return cached_results[key]
                else:
                    cached_results.pop(key)
                    cached_timestamps.pop(key)

            result = func(*args, **kwargs)
            cached_results[key] = result
            cached_timestamps[key] = now

            if len(cached_results) > maxsize:
                oldest_key = min(cached_timestamps, key=cached_timestamps.get)
                cached_results.pop(oldest_key)
                cached_timestamps.pop(oldest_key)

            return result

        return wrapped

    return decorator


