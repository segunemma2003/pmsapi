from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db import connection
from django.core.cache import cache
from django.conf import settings
import redis

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Comprehensive health check endpoint"""
    health_status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'services': {}
    }
    
    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['services']['database'] = {'status': 'healthy'}
    except Exception as e:
        health_status['services']['database'] = {'status': 'unhealthy', 'error': str(e)}
        health_status['status'] = 'unhealthy'
    
    # Redis check
    try:
        cache.set('health_check', 'ok', timeout=10)
        cache.get('health_check')
        health_status['services']['redis'] = {'status': 'healthy'}
    except Exception as e:
        health_status['services']['redis'] = {'status': 'unhealthy', 'error': str(e)}
        health_status['status'] = 'unhealthy'
    
    # Beds24 API check (if configured)
    if settings.BEDS24_REFRESH_TOKEN:
        try:
            from beds24_integration.services import Beds24Service
            beds24_service = Beds24Service()
            if beds24_service.test_connection():
                health_status['services']['beds24'] = {'status': 'healthy'}
            else:
                health_status['services']['beds24'] = {'status': 'unhealthy'}
        except Exception as e:
            health_status['services']['beds24'] = {'status': 'unhealthy', 'error': str(e)}
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return Response(health_status, status=status_code)