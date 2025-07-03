from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from .models import ActivityLog, AdminAnalytics
from .serializers import ActivityLogSerializer, AdminAnalyticsSerializer
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta, datetime

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
    
    @action(detail=False, methods=['get'])
    def revenue_analytics(self, request):
        """Get revenue analytics with grouping"""
        user = request.user
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        group_by = request.GET.get('group_by', 'month')  # day, week, month
        
        # Default to last 12 months if no dates provided
        if not end_date:
            end_date = timezone.now().date()
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        if not start_date:
            start_date = end_date - timedelta(days=365)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        from bookings.models import Booking
        
        # Filter bookings based on user type
        if user.user_type == 'owner':
            bookings = Booking.objects.filter(
                property__owner=user,
                status__in=['confirmed', 'completed'],
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            )
        elif user.user_type == 'admin':
            bookings = Booking.objects.filter(
                status__in=['confirmed', 'completed'],
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            )
        else:
            return Response(
                {'error': 'Revenue analytics not available for regular users'},
                status=403
            )
        
        # Group data by specified period
        if group_by == 'day':
            date_format = '%Y-%m-%d'
            trunc_format = 'date'
        elif group_by == 'week':
            date_format = '%Y-W%U'
            trunc_format = 'week'
        else:  # month
            date_format = '%Y-%m'
            trunc_format = 'month'
        
        revenue_data = bookings.extra(
            select={'period': f"DATE_TRUNC('{trunc_format}', created_at)"}
        ).values('period').annotate(
            revenue=Sum('total_amount'),
            bookings_count=Count('id'),
            avg_booking_value=Avg('total_amount')
        ).order_by('period')
        
        # Format the response
        formatted_data = []
        for item in revenue_data:
            period_date = item['period']
            if isinstance(period_date, str):
                period_date = datetime.strptime(period_date, '%Y-%m-%d').date()
            
            formatted_data.append({
                'period': period_date.strftime(date_format),
                'revenue': float(item['revenue'] or 0),
                'bookings_count': item['bookings_count'],
                'avg_booking_value': float(item['avg_booking_value'] or 0)
            })
        
        # Calculate totals
        total_revenue = sum(item['revenue'] for item in formatted_data)
        total_bookings = sum(item['bookings_count'] for item in formatted_data)
        
        return Response({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'group_by': group_by,
            'total_revenue': total_revenue,
            'total_bookings': total_bookings,
            'average_booking_value': total_revenue / total_bookings if total_bookings > 0 else 0,
            'data': formatted_data
        })

    @action(detail=False, methods=['get'])
    def system_stats(self, request):
        """Get system-wide statistics (admin only)"""
        if request.user.user_type != 'admin':
            return Response(
                {'error': 'Admin access required'},
                status=403
            )
        
        cache_key = 'system_stats'
        stats = cache.get(cache_key)
        
        if stats is None:
            from django.contrib.auth import get_user_model
            from properties.models import Property
            from bookings.models import Booking
            from trust_levels.models import OwnerTrustedNetwork
            
            User = get_user_model()
            
            # User statistics
            total_users = User.objects.count()
            active_users = User.objects.filter(status='active').count()
            owners = User.objects.filter(user_type='owner').count()
            regular_users = User.objects.filter(user_type='user').count()
            
            # Property statistics
            total_properties = Property.objects.count()
            active_properties = Property.objects.filter(status='active').count()
            beds24_properties = Property.objects.filter(
                beds24_property_id__isnull=False
            ).count()
            
            # Booking statistics
            total_bookings = Booking.objects.count()
            confirmed_bookings = Booking.objects.filter(status='confirmed').count()
            completed_bookings = Booking.objects.filter(status='completed').count()
            
            # Revenue statistics
            total_revenue = Booking.objects.filter(
                status__in=['confirmed', 'completed']
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            
            # Trust network statistics
            total_networks = OwnerTrustedNetwork.objects.filter(status='active').count()
            avg_network_size = OwnerTrustedNetwork.objects.filter(
                status='active'
            ).values('owner').annotate(
                network_size=Count('trusted_user')
            ).aggregate(avg=Avg('network_size'))['avg'] or 0
            
            # Growth statistics (last 30 days)
            last_30_days = timezone.now() - timedelta(days=30)
            new_users = User.objects.filter(date_joined__gte=last_30_days).count()
            new_properties = Property.objects.filter(created_at__gte=last_30_days).count()
            new_bookings = Booking.objects.filter(created_at__gte=last_30_days).count()
            
            stats = {
                'users': {
                    'total': total_users,
                    'active': active_users,
                    'owners': owners,
                    'regular_users': regular_users,
                    'new_last_30_days': new_users
                },
                'properties': {
                    'total': total_properties,
                    'active': active_properties,
                    'beds24_connected': beds24_properties,
                    'new_last_30_days': new_properties
                },
                'bookings': {
                    'total': total_bookings,
                    'confirmed': confirmed_bookings,
                    'completed': completed_bookings,
                    'new_last_30_days': new_bookings
                },
                'revenue': {
                    'total': float(total_revenue),
                    'average_per_booking': float(total_revenue / total_bookings) if total_bookings > 0 else 0
                },
                'trust_networks': {
                    'total_connections': total_networks,
                    'average_network_size': float(avg_network_size)
                },
                'growth': {
                    'user_growth_rate': (new_users / total_users * 100) if total_users > 0 else 0,
                    'property_growth_rate': (new_properties / total_properties * 100) if total_properties > 0 else 0,
                    'booking_growth_rate': (new_bookings / total_bookings * 100) if total_bookings > 0 else 0
                }
            }
            
            # Cache for 10 minutes
            cache.set(cache_key, stats, timeout=600)
        
        return Response(stats)

    @action(detail=False, methods=['get'])
    def audit_logs(self, request):
        """Get audit logs (admin only)"""
        if request.user.user_type != 'admin':
            return Response(
                {'error': 'Admin access required'},
                status=403
            )
        
        limit = int(request.GET.get('limit', 50))
        action_filter = request.GET.get('action')
        user_filter = request.GET.get('user')
        resource_type_filter = request.GET.get('resource_type')
        
        logs = ActivityLog.objects.select_related('user').all()
        
        # Apply filters
        if action_filter:
            logs = logs.filter(action__icontains=action_filter)
        if user_filter:
            logs = logs.filter(user__email__icontains=user_filter)
        if resource_type_filter:
            logs = logs.filter(resource_type=resource_type_filter)
        
        # Limit and order
        logs = logs.order_by('-created_at')[:limit]
        
        serializer = ActivityLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def performance_metrics(self, request):
        """Get system performance metrics"""
        user = request.user
        
        # Cache key based on user type
        cache_key = f'performance_metrics_{user.user_type}_{user.id}'
        metrics = cache.get(cache_key)
        
        if metrics is None:
            from django.db import connection
            
            # Database performance
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM django_session")
                active_sessions = cursor.fetchone()[0]
            
            # Response time metrics (placeholder - would need real monitoring)
            avg_response_time = 150  # ms
            
            # User-specific metrics
            if user.user_type == 'owner':
                from properties.models import Property
                from bookings.models import Booking
                
                user_properties = Property.objects.filter(owner=user).count()
                user_bookings = Booking.objects.filter(property__owner=user).count()
                
                metrics = {
                    'user_type': 'owner',
                    'properties_count': user_properties,
                    'total_bookings': user_bookings,
                    'avg_response_time': avg_response_time,
                    'active_sessions': active_sessions
                }
            elif user.user_type == 'admin':
                from django.contrib.auth import get_user_model
                User = get_user_model()
                
                total_users = User.objects.count()
                active_users = User.objects.filter(
                    last_login__gte=timezone.now() - timedelta(days=30)
                ).count()
                
                metrics = {
                    'user_type': 'admin',
                    'total_users': total_users,
                    'active_users': active_users,
                    'avg_response_time': avg_response_time,
                    'active_sessions': active_sessions
                }
            else:
                from bookings.models import Booking
                user_bookings = Booking.objects.filter(guest=user).count()
                
                metrics = {
                    'user_type': 'user',
                    'my_bookings': user_bookings,
                    'avg_response_time': avg_response_time,
                    'active_sessions': active_sessions
                }
            
            # Cache for 5 minutes
            cache.set(cache_key, metrics, timeout=300)
        
        return Response(metrics)