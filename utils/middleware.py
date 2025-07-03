import time
import logging
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger('oifyk.performance')

class DatabaseRoutingMiddleware(MiddlewareMixin):
    """Route read operations to replica database when available"""
    
    def process_request(self, request):
        # Force read from primary for write operations
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            request._db_routing = 'default'
        else:
            # Use replica for read operations if available
            request._db_routing = 'replica' if 'replica' in settings.DATABASES else 'default'

class CacheHeadersMiddleware(MiddlewareMixin):
    """Add appropriate cache headers based on content type and user"""
    
    def process_response(self, request, response):
        # Don't cache authenticated API responses by default
        if request.path.startswith('/api/') and hasattr(request, 'user') and request.user.is_authenticated:
            # Cache public endpoints
            if request.path.startswith('/api/properties/') and request.method == 'GET':
                response['Cache-Control'] = 'private, max-age=300'  # 5 minutes
            elif request.path.startswith('/api/analytics/') and request.method == 'GET':
                response['Cache-Control'] = 'private, max-age=60'   # 1 minute
            else:
                response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
        
        # Cache static files aggressively
        elif request.path.startswith('/static/') or request.path.startswith('/media/'):
            response['Cache-Control'] = 'public, max-age=31536000'  # 1 year
        
        return response

class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """Monitor API performance and log slow requests"""
    
    def process_request(self, request):
        request._start_time = time.time()
        request._initial_db_queries = len(connection.queries)
    
    def process_response(self, request, response):
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            db_queries = len(connection.queries) - getattr(request, '_initial_db_queries', 0)
            
            # Log slow requests (>300ms for API endpoints)
            if request.path.startswith('/api/') and duration > 0.3:
                logger.warning(
                    f"Slow API request: {request.method} {request.path} "
                    f"took {duration:.3f}s with {db_queries} DB queries"
                )
            
            # Add performance headers in debug mode
            if settings.DEBUG:
                response['X-Response-Time'] = f"{duration:.3f}s"
                response['X-DB-Queries'] = str(db_queries)
        
        return response

class RateLimitMiddleware(MiddlewareMixin):
    """Simple rate limiting middleware"""
    
    def process_request(self, request):
        if not getattr(settings, 'FEATURES', {}).get('RATE_LIMITING', True):
            return None
        
        # Skip rate limiting for certain paths
        skip_paths = ['/health/', '/api/health/', '/admin/']
        if any(request.path.startswith(path) for path in skip_paths):
            return None
        
        # Get client IP
        ip = self.get_client_ip(request)
        
        # Different limits based on authentication
        if hasattr(request, 'user') and request.user.is_authenticated:
            if request.user.user_type == 'admin':
                limit, window = 5000, 3600  # 5000 requests per hour
            elif request.user.user_type == 'owner':
                limit, window = 2000, 3600  # 2000 requests per hour
            else:
                limit, window = 1000, 3600  # 1000 requests per hour
            
            cache_key = f"rate_limit_user_{request.user.id}"
        else:
            limit, window = 100, 3600  # 100 requests per hour for anonymous
            cache_key = f"rate_limit_ip_{ip}"
        
        # Check current count
        current_count = cache.get(cache_key, 0)
        
        if current_count >= limit:
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'limit': limit,
                'window': window,
                'retry_after': cache.ttl(cache_key)
            }, status=429)
        
        # Increment counter
        try:
            cache.add(cache_key, 0, timeout=window)
            cache.incr(cache_key)
        except ValueError:
            # Race condition, reset counter
            cache.set(cache_key, 1, timeout=window)
        
        return None
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
