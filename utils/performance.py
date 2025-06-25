import time
import functools
from django.core.cache import cache
from django.db import connection
from django.conf import settings

def cache_result(timeout=300, key_prefix=''):
    """Decorator to cache function results"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            result = cache.get(cache_key)
            if result is None:
                result = func(*args, **kwargs)
                cache.set(cache_key, result, timeout=timeout)
            
            return result
        return wrapper
    return decorator

def log_queries(func):
    """Decorator to log database queries for performance monitoring"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if settings.DEBUG:
            initial_queries = len(connection.queries)
            start_time = time.time()
            
            result = func(*args, **kwargs)
            
            end_time = time.time()
            execution_time = end_time - start_time
            query_count = len(connection.queries) - initial_queries
            
            print(f"Function: {func.__name__}")
            print(f"Execution time: {execution_time:.4f}s")
            print(f"Database queries: {query_count}")
            print("-" * 50)
            
            return result
        else:
            return func(*args, **kwargs)
    return wrapper