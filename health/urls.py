from django.urls import path
from .views import health_check, simple_health_check

urlpatterns = [
    path('', health_check, name='health_check'),
    path('simple/', simple_health_check, name='simple_health_check'),
]