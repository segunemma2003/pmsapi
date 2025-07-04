from django.core.cache import cache
from django.conf import settings
import hashlib
import json
from functools import wraps

def cache_key_generator(*args, **kwargs):
    """Generate consistent cache keys"""
    key_parts = []
    for arg in args:
        if hasattr(arg, 'id'):
            key_parts.append(f"{arg.__class__.__name__}_{arg.id}")
        else:
            key_parts.append(str(arg))
    
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}_{v}")
    
    key = "_".join(key_parts)
    if len(key) > 200:  # Redis key length limit
        key = hashlib.md5(key.encode()).hexdigest()[:32]
    
    return key

def cache_result(timeout=None, key_prefix='', vary_on_user=True):
    """Advanced caching decorator"""
    def decorator(func):
        @wraps(func)
        def wrapper(request=None, *args, **kwargs):
            # Determine cache timeout
            cache_timeout = timeout or getattr(settings, 'CACHE_TIMEOUTS', {}).get('DEFAULT', 300)
            
            # Build cache key
            key_parts = [key_prefix or func.__name__]
            
            if vary_on_user and request and hasattr(request, 'user') and request.user.is_authenticated:
                key_parts.append(f"user_{request.user.id}")
            
            key_parts.extend([str(arg) for arg in args])
            key_parts.extend([f"{k}_{v}" for k, v in sorted(kwargs.items())])
            
            cache_key = cache_key_generator(*key_parts)
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(request, *args, **kwargs) if request else func(*args, **kwargs)
            cache.set(cache_key, result, timeout=cache_timeout)
            
            return result
        return wrapper
    return decorator

def invalidate_cache_pattern(pattern):
    """Invalidate cache keys matching pattern (Redis only)"""
    try:
        from django_redis import get_redis_connection
        redis_conn = get_redis_connection("default")
        keys = redis_conn.keys(f"*{pattern}*")
        if keys:
            redis_conn.delete(*keys)
        return len(keys)
    except ImportError:
        # Fallback for non-Redis cache backends
        return 0

class CacheManager:
    """Centralized cache management"""
    
    @staticmethod
    def get_user_cache_keys(user_id):
        """Get all cache keys related to a user"""
        return [
            f'user_profile_{user_id}',
            f'user_accessible_properties_{user_id}',
            f'user_trust_networks_{user_id}',
            f'user_dashboard_metrics_{user_id}',
        ]
    
    @staticmethod
    def clear_user_cache(user_id):
        """Clear all cache entries for a user"""
        keys = CacheManager.get_user_cache_keys(user_id)
        cache.delete_many(keys)
        
        # Also clear any trust discount caches
        invalidate_cache_pattern(f'trust_discount_*_{user_id}')
        invalidate_cache_pattern(f'trust_discount_{user_id}_*')
    
    @staticmethod
    def get_property_cache_keys(property_id):
        """Get all cache keys related to a property"""
        return [
            f'property_detail_{property_id}',
            f'property_availability_{property_id}',
        ]
    
    @staticmethod
    def clear_property_cache(property_id):
        """Clear all cache entries for a property"""
        keys = CacheManager.get_property_cache_keys(property_id)
        cache.delete_many(keys)
        
        # Clear user-specific property caches
        invalidate_cache_pattern(f'property_detail_{property_id}_*')
    
    @staticmethod
    def warm_cache():
        """Warm up frequently accessed cache entries"""
        from django.contrib.auth import get_user_model
        from properties.models import Property
        from trust_levels.models import OwnerTrustedNetwork
        
        User = get_user_model()
        
        # Cache active users
        active_users = User.objects.filter(status='active').select_related()
        for user in active_users[:100]:  # Limit to first 100
            cache.set(f'user_profile_{user.id}', user, timeout=3600)
        
        # Cache trust network sizes for owners
        owners = User.objects.filter(user_type='owner', status='active')
        for owner in owners:
            network_size = OwnerTrustedNetwork.objects.filter(
                owner=owner, status='active'
            ).count()
            cache.set(f'trust_network_size_{owner.id}', network_size, timeout=300)
        
        # Cache featured properties
        featured_properties = Property.objects.filter(
            is_featured=True, status='active'
        ).select_related('owner')[:20]
        
        for prop in featured_properties:
            cache.set(f'property_detail_{prop.id}', prop, timeout=1800)
