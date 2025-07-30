from django.contrib import admin
from django.urls import path, include
from notifications.views import NotificationViewSet
from upload.views import delete_file, upload_file
from rest_framework.routers import DefaultRouter
from accounts.views import UserViewSet
from properties.views import PropertyViewSet
from bookings.views import BookingViewSet
from invitations.views import InvitationViewSet
from trust_levels.views import TrustedNetworkInvitationViewSet
from trust_levels.views import TrustLevelDefinitionViewSet, OwnerTrustedNetworkViewSet
from analytics.views import AnalyticsViewSet
from properties.views import AIPropertyExtractView,validate_address
from properties.openai_views import flexible_conversation_extract


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'invitations', InvitationViewSet, basename='invitation')
router.register(r'network-invitations', TrustedNetworkInvitationViewSet, basename='network-invitation')
router.register(r'trust-levels', TrustLevelDefinitionViewSet, basename='trust-level')
router.register(r'trusted-networks', OwnerTrustedNetworkViewSet, basename='trusted-network')
router.register(r'analytics', AnalyticsViewSet, basename='analytics')
router.register(r'notifications', NotificationViewSet, basename='notifications')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/health/', include('health.urls')),
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
    
    # File upload endpoints
    path('api/upload/', upload_file, name='upload-file'),
    path('api/upload/delete/', delete_file, name='delete-file'),
    
    # Custom property endpoints
    path('api/properties/<uuid:pk>/ical/', PropertyViewSet.as_view({'get': 'ical_export'}), name='property-ical'),
     path('api/ai/ai-extract/', AIPropertyExtractView.as_view(), name='ai-property-extract'),
        path('api/ai/flexible-conversation-extract/', flexible_conversation_extract, name='flexible_conversation_extract'),
    path('api/ai/enhanced-property-extraction/', views.AIPropertyExtractView.as_view(), name='enhanced_property_extraction'),
    path('api/validate-address/', validate_address, name='validate_address'),
]
