from django.db import models
from django.core.cache import cache

class OptimizedQuerySet(models.QuerySet):
    """Custom QuerySet with built-in optimizations"""
    
    def with_cache(self, cache_key, timeout=300):
        """Cache the queryset results"""
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        result = list(self)
        cache.set(cache_key, result, timeout=timeout)
        return result
    
    def prefetch_for_api(self):
        """Common prefetch patterns for API responses"""
        if hasattr(self.model, 'owner'):
            self = self.select_related('owner')
        
        if hasattr(self.model, 'property'):
            self = self.select_related('property', 'property__owner')
        
        if hasattr(self.model, 'guest'):
            self = self.select_related('guest')
        
        return self
    
    def active_only(self):
        """Filter for active records"""
        if hasattr(self.model, 'status'):
            return self.filter(status='active')
        return self

class OptimizedManager(models.Manager):
    """Custom manager with optimizations"""
    
    def get_queryset(self):
        return OptimizedQuerySet(self.model, using=self._db)
    
    def active(self):
        return self.get_queryset().active_only()
    
    def with_related(self):
        return self.get_queryset().prefetch_for_api()