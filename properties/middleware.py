from django.core.cache import cache
from django.http import JsonResponse
import time
import logging

logger = logging.getLogger(__name__)

class AIRateLimitMiddleware:
    """Rate limiting middleware for AI API calls"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is an AI extraction request
        if request.path.startswith('/api/ai/') and request.method == 'POST':
            user_id = getattr(request.user, 'id', 'anonymous') if hasattr(request, 'user') else 'anonymous'
            cache_key = f'ai_rate_limit_{user_id}'
            
            # Get current request count
            current_count = cache.get(cache_key, 0)
            
            # Allow 30 requests per minute
            if current_count >= 30:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please wait a moment before trying again.'
                }, status=429)
            
            # Increment counter
            cache.set(cache_key, current_count + 1, 60)  # 60 seconds
        
        response = self.get_response(request)
        return response
