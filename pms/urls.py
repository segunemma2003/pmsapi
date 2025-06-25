from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from accounts.views import UserViewSet
from properties.views import PropertyViewSet
from bookings.views import BookingViewSet
from invitations.views import InvitationViewSet, TrustedNetworkInvitationViewSet
from trust_levels.views import TrustLevelDefinitionViewSet, OwnerTrustedNetworkViewSet
from analytics.views import AnalyticsViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'invitations', InvitationViewSet, basename='invitation')
router.register(r'network-invitations', TrustedNetworkInvitationViewSet, basename='network-invitation')
router.register(r'trust-levels', TrustLevelDefinitionViewSet, basename='trust-level')
router.register(r'trusted-networks', OwnerTrustedNetworkViewSet, basename='trusted-network')
router.register(r'analytics', AnalyticsViewSet, basename='analytics')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
]