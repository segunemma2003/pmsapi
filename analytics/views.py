from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from .models import ActivityLog, AdminAnalytics
from .serializers import ActivityLogSerializer, AdminAnalyticsSerializer

class AnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def dashboard_metrics(self, request):
        """Get dashboard metrics for different user types"""
        user = request.user
        
        if user.user_type == 'admin':
            return self._get_admin_metrics()
        elif user.user_type == 'owner':
            return self._get_owner_metrics(user)
        else:
            return self._get_user_metrics(user)
    
    def _get_admin_metrics(self):
        """Get admin dashboard metrics"""
        cache_key = 'admin_dashboard_metrics'
        metrics = cache.get(cache_key)
        
        if metrics is None:
            from django.contrib.auth import get_user_model
            from properties.models import Property
            from bookings.models import Booking
            
            User = get_user_model()
            
            metrics = {
                'total_users': User.objects.count(),
                'total_owners': User.objects.filter(user_type='owner').count(),
                'total_properties': Property.objects.count(),
                'active_properties': Property.objects.filter(status='active').count(),
                'total_bookings': Booking.objects.count(),
                'pending_approvals': Property.objects.filter(status='pending_approval').count(),
                'recent_signups': User.objects.filter(
                    date_joined__gte=timezone.now() - timedelta(days=7)
                ).count(),
                'monthly_revenue': Booking.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=30),
                    status='confirmed'
                ).aggregate(total=Sum('total_amount'))['total'] or 0
            }
            
            cache.set(cache_key, metrics, timeout=300)  # 5 minutes
        
        return Response(metrics)
    
    def _get_owner_metrics(self, user):
        """Get owner dashboard metrics"""
        cache_key = f'owner_dashboard_metrics_{user.id}'
        metrics = cache.get(cache_key)
        
        if metrics is None:
            from properties.models import Property
            from bookings.models import Booking
            from trust_levels.models import OwnerTrustedNetwork
            
            # Get owner's properties
            properties = Property.objects.filter(owner=user)
            property_ids = list(properties.values_list('id', flat=True))
            
            # Get bookings for owner's properties
            bookings = Booking.objects.filter(property__in=property_ids)
            
            # Calculate metrics
            metrics = {
                'my_properties_count': properties.count(),
                'active_properties_count': properties.filter(status='active').count(),
                'total_bookings_count': bookings.count(),
                'upcoming_bookings_count': bookings.filter(
                    check_in_date__gte=timezone.now().date(),
                    status__in=['confirmed', 'pending']
                ).count(),
                'network_size': OwnerTrustedNetwork.objects.filter(
                    owner=user, status='active'
                ).count(),
                'monthly_revenue': bookings.filter(
                    created_at__gte=timezone.now() - timedelta(days=30),
                    status='confirmed'
                ).aggregate(total=Sum('total_amount'))['total'] or 0,
                'properties_by_status': {
                    'draft': properties.filter(status='draft').count(),
                    'pending_approval': properties.filter(status='pending_approval').count(),
                    'active': properties.filter(status='active').count(),
                }
            }
            
            cache.set(cache_key, metrics, timeout=300)  # 5 minutes
        
        return Response(metrics)
    
    def _get_user_metrics(self, user):
        """Get user dashboard metrics"""
        cache_key = f'user_dashboard_metrics_{user.id}'
        metrics = cache.get(cache_key)
        
        if metrics is None:
            from bookings.models import Booking
            from trust_levels.models import OwnerTrustedNetwork
            
            user_bookings = Booking.objects.filter(guest=user)
            
            metrics = {
                'total_bookings': user_bookings.count(),
                'upcoming_bookings': user_bookings.filter(
                    check_in_date__gte=timezone.now().date(),
                    status__in=['confirmed', 'pending']
                ).count(),
                'completed_bookings': user_bookings.filter(status='completed').count(),
                'trusted_networks_count': OwnerTrustedNetwork.objects.filter(
                    trusted_user=user, status='active'
                ).count(),
                'total_spent': user_bookings.filter(
                    status='completed'
                ).aggregate(total=Sum('total_amount'))['total'] or 0,
                'average_discount': user_bookings.filter(
                    discount_applied__gt=0
                ).aggregate(avg=models.Avg('discount_applied'))['avg'] or 0
            }
            
            cache.set(cache_key, metrics, timeout=300)  # 5 minutes
        
        return Response(metrics)
    
    @action(detail=False, methods=['get'])
    def recent_activity(self, request):
        """Get recent activity logs"""
        user = request.user
        limit = int(request.query_params.get('limit', 10))
        
        if user.user_type == 'admin':
            activities = ActivityLog.objects.select_related('user').order_by(
                '-created_at'
            )[:limit]
        elif user.user_type == 'owner':
            # Show activities related to owner's resources
            activities = ActivityLog.objects.select_related('user').filter(
                Q(user=user) | 
                Q(resource_type='property', resource_id__in=user.properties.values_list('id', flat=True)) |
                Q(resource_type='booking', resource_id__in=user.properties.values_list('bookings__id', flat=True))
            ).order_by('-created_at')[:limit]
        else:
            # Show user's own activities
            activities = ActivityLog.objects.select_related('user').filter(
                user=user
            ).order_by('-created_at')[:limit]
        
        serializer = ActivityLogSerializer(activities, many=True)
        return Response(serializer.data)