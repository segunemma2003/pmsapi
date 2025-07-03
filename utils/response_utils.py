from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import time

class APIResponse:
    """Standardized API response helpers"""
    
    @staticmethod
    def success(data=None, message=None, status_code=status.HTTP_200_OK, extra=None):
        """Standard success response"""
        response_data = {'success': True}
        
        if message:
            response_data['message'] = message
        
        if data is not None:
            response_data['data'] = data
        
        if extra:
            response_data.update(extra)
        
        return Response(response_data, status=status_code)
    
    @staticmethod
    def error(message, status_code=status.HTTP_400_BAD_REQUEST, errors=None, extra=None):
        """Standard error response"""
        response_data = {
            'success': False,
            'error': message
        }
        
        if errors:
            response_data['errors'] = errors
        
        if extra:
            response_data.update(extra)
        
        return Response(response_data, status=status_code)
    
    @staticmethod
    def paginated(queryset, serializer_class, request, extra_context=None):
        """Paginated response with caching"""
        from django.core.paginator import Paginator
        
        page_size = min(int(request.GET.get('page_size', 20)), 100)
        page_number = int(request.GET.get('page', 1))
        
        # Generate cache key for this query
        cache_key = f"paginated_{request.user.id}_{request.path}_{page_number}_{page_size}"
        for key, value in request.GET.items():
            if key not in ['page', 'page_size']:
                cache_key += f"_{key}_{value}"
        
        cached_response = cache.get(cache_key)
        if cached_response:
            return Response(cached_response)
        
        paginator = Paginator(queryset, page_size)
        page = paginator.get_page(page_number)
        
        serializer = serializer_class(page.object_list, many=True, context={'request': request})
        
        response_data = {
            'success': True,
            'results': serializer.data,
            'pagination': {
                'count': paginator.count,
                'total_pages': paginator.num_pages,
                'current_page': page_number,
                'page_size': page_size,
                'has_next': page.has_next(),
                'has_previous': page.has_previous(),
            }
        }
        
        if extra_context:
            response_data.update(extra_context)
        
        # Cache for 2 minutes
        cache.set(cache_key, response_data, timeout=120)
        
        return Response(response_data)