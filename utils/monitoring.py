import logging
import time
from django.db import connection
from django.core.cache import cache
from functools import wraps

logger = logging.getLogger('oifyk.monitoring')

class PerformanceMonitor:
    """Performance monitoring utilities"""
    
    @staticmethod
    def log_slow_query(func):
        """Decorator to log slow database operations"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            initial_queries = len(connection.queries)
            
            result = func(*args, **kwargs)
            
            end_time = time.time()
            duration = end_time - start_time
            query_count = len(connection.queries) - initial_queries
            
            if duration > 0.1:  # Log operations taking more than 100ms
                logger.warning(
                    f"Slow operation: {func.__name__} took {duration:.3f}s "
                    f"with {query_count} DB queries"
                )
            
            return result
        return wrapper
    
    @staticmethod
    def track_cache_performance():
        """Track cache hit/miss rates"""
        cache_stats = {
            'hits': cache.get('cache_hits', 0),
            'misses': cache.get('cache_misses', 0),
            'sets': cache.get('cache_sets', 0)
        }
        
        total_requests = cache_stats['hits'] + cache_stats['misses']
        if total_requests > 0:
            hit_rate = (cache_stats['hits'] / total_requests) * 100
            logger.info(f"Cache hit rate: {hit_rate:.2f}%")
        
        return cache_stats
    
    @staticmethod
    def increment_cache_stat(stat_type):
        """Increment cache statistics"""
        try:
            cache.add(f'cache_{stat_type}', 0, timeout=3600)
            cache.incr(f'cache_{stat_type}')
        except ValueError:
            cache.set(f'cache_{stat_type}', 1, timeout=3600)


# Custom cache backend wrapper for monitoring
class MonitoredCacheWrapper:
    """Wrapper around cache to add monitoring"""
    
    def __init__(self, cache_backend):
        self.cache = cache_backend
        self.monitor = PerformanceMonitor()
    
    def get(self, key, default=None, version=None):
        result = self.cache.get(key, default, version)
        if result is None or result == default:
            self.monitor.increment_cache_stat('misses')
        else:
            self.monitor.increment_cache_stat('hits')
        return result
    
    def set(self, key, value, timeout=None, version=None):
        self.monitor.increment_cache_stat('sets')
        return self.cache.set(key, value, timeout, version)
    
    def __getattr__(self, name):
        return getattr(self.cache, name)


# Health check utilities
class HealthChecker:
    """System health monitoring"""
    
    @staticmethod
    def check_database():
        """Check database connectivity"""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return {'status': 'healthy', 'response_time': 0}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}
    
    @staticmethod
    def check_cache():
        """Check cache connectivity"""
        try:
            test_key = 'health_check_test'
            cache.set(test_key, 'test_value', timeout=10)
            value = cache.get(test_key)
            cache.delete(test_key)
            
            if value == 'test_value':
                return {'status': 'healthy'}
            else:
                return {'status': 'unhealthy', 'error': 'Cache not working properly'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}
    
    @staticmethod
    def check_beds24_connection():
        """Check Beds24 API connectivity"""
        try:
            from beds24_integration.services import Beds24Service
            beds24_service = Beds24Service()
            if beds24_service.test_connection():
                return {'status': 'healthy'}
            else:
                return {'status': 'unhealthy', 'error': 'Cannot connect to Beds24 API'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}
    
    @staticmethod
    def get_system_health():
        """Get overall system health"""
        checks = {
            'database': HealthChecker.check_database(),
            'cache': HealthChecker.check_cache(),
            'beds24': HealthChecker.check_beds24_connection()
        }
        
        overall_status = 'healthy'
        for check in checks.values():
            if check['status'] != 'healthy':
                overall_status = 'unhealthy'
                break
        
        return {
            'status': overall_status,
            'timestamp': time.time(),
            'checks': checks
        }