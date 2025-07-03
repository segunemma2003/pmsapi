from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.core.cache import cache
from .models import Property, PropertyImage
from .serializers import PropertySerializer, PropertyCreateSerializer
from .filters import PropertyFilter
from django.db.models import Q, Count
from django.core.cache import cache
from django.http import HttpResponse
from beds24_integration.ical_service import ICalService
from .models import Property, PropertyImage
from .serializers import PropertySerializer, PropertyCreateSerializer
from .filters import PropertyFilter
import json
from datetime import datetime, timedelta

class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Optimized queryset with proper access control"""
        user = self.request.user
        
        # Base queryset with optimizations
        base_queryset = Property.objects.select_related('owner').annotate(
            booking_count=Count('bookings')
        ).prefetch_related('images_set')
        
        if user.user_type == 'admin':
            # Admins see all properties
            return base_queryset.all()
        elif user.user_type == 'owner':
            # Owners see their own properties
            return base_queryset.filter(owner=user)
        else:
            # Users see visible properties from owners who invited them
            cache_key = f'user_accessible_properties_{user.id}'
            property_ids = cache.get(cache_key)
            
            if property_ids is None:
                from trust_levels.models import OwnerTrustedNetwork
                trusted_owners = OwnerTrustedNetwork.objects.filter(
                    trusted_user=user,
                    status='active'
                ).values_list('owner_id', flat=True)
                
                property_ids = list(base_queryset.filter(
                    owner__in=trusted_owners,
                    status='active',
                    is_visible=True
                ).values_list('id', flat=True))
                
                cache.set(cache_key, property_ids, timeout=300)  # 5 minutes
            
            return base_queryset.filter(id__in=property_ids)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PropertyCreateSerializer
        return PropertySerializer
    
    @action(detail=True, methods=['patch'])
    def toggle_visibility(self, request, pk=None):
        """Toggle property visibility (owner only)"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user:
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        is_visible = request.data.get('is_visible')
        if is_visible is None:
            # Toggle current visibility
            property_obj.is_visible = not property_obj.is_visible
        else:
            property_obj.is_visible = bool(is_visible)
        
        property_obj.save()
        
        # Update Beds24 visibility if synced
        if property_obj.beds24_property_id:
            from .tasks import update_beds24_visibility
            update_beds24_visibility.delay(str(property_obj.id), property_obj.is_visible)
        
        # Clear cache
        cache.delete(f'property_detail_{property_obj.id}')
        
        return Response({
            'message': f'Property visibility updated to {property_obj.is_visible}',
            'is_visible': property_obj.is_visible
        })
    @action(detail=True, methods=['get'])
    def ical_export(self, request, pk=None):
        """Export property calendar as iCal"""
        property_obj = self.get_object()
        
        # Get date range from query params
        start_date = request.GET.get('start')
        end_date = request.GET.get('end')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = datetime.now().date()
            
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = start_date + timedelta(days=365)  # 1 year from start
        
        # Generate iCal content
        ical_content = ICalService.generate_property_calendar(property_obj, start_date, end_date)
        
        # Return as iCal file
        response = HttpResponse(ical_content, content_type='text/calendar; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{property_obj.title}_calendar.ics"'
        return response

    @action(detail=True, methods=['post'])
    def setup_ical_sync(self, request, pk=None):
        """Setup iCal sync settings for property"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user:
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update iCal settings
        property_obj.ical_sync_enabled = request.data.get('import_enabled', True)
        property_obj.ical_auto_block = request.data.get('auto_block', True)
        property_obj.ical_sync_interval = request.data.get('sync_interval', 3600)
        property_obj.ical_timezone = request.data.get('timezone', 'UTC')
        property_obj.save()
        
        return Response({
            'message': 'iCal sync settings updated successfully',
            'settings': {
                'import_enabled': property_obj.ical_sync_enabled,
                'auto_block': property_obj.ical_auto_block,
                'sync_interval': property_obj.ical_sync_interval,
                'timezone': property_obj.ical_timezone,
            }
        })

    @action(detail=True, methods=['post'])
    def add_external_calendar(self, request, pk=None):
        """Add external calendar URL for sync"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user:
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        calendar_url = request.data.get('calendar_url')
        calendar_name = request.data.get('calendar_name')
        
        if not calendar_url:
            return Response(
                {'error': 'Calendar URL is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate URL
        validation_result = ICalService.validate_ical_url(calendar_url)
        if not validation_result['valid']:
            return Response(
                {'error': f"Invalid calendar URL: {validation_result['error']}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Add to external calendars list
        external_calendars = property_obj.ical_external_calendars or []
        external_calendars.append({
            'url': calendar_url,
            'name': calendar_name or 'External Calendar',
            'added_at': datetime.now().isoformat(),
            'active': True
        })
        
        property_obj.ical_external_calendars = external_calendars
        property_obj.save()
        
        return Response({
            'message': 'External calendar added successfully',
            'calendar': {
                'url': calendar_url,
                'name': calendar_name,
                'events_found': validation_result.get('events_found', 0)
            }
        })

    @action(detail=True, methods=['post'])
    def sync_ical(self, request, pk=None):
        """Manually trigger iCal sync"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user:
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Trigger sync via Celery task if using Beds24
        if property_obj.beds24_property_id:
            from .tasks import auto_sync_all_properties
            auto_sync_all_properties.delay()
            
            property_obj.ical_last_sync = datetime.now()
            property_obj.ical_sync_status = 'running'
            property_obj.save()
            
            return Response({
                'message': 'Calendar sync started',
                'sync_status': 'running',
                'last_sync': property_obj.ical_last_sync
            })
        else:
            return Response(
                {'error': 'Property not connected to Beds24'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search properties with filters"""
        query = request.GET.get('search', '')
        city = request.GET.get('city')
        min_price = request.GET.get('min_price')
        max_price = request.GET.get('max_price')
        bedrooms = request.GET.get('bedrooms')
        max_guests = request.GET.get('max_guests')
        
        queryset = self.get_queryset()
        
        # Text search
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(city__icontains=query) |
                Q(address__icontains=query)
            )
        
        # Filters
        if city:
            queryset = queryset.filter(city__icontains=city)
        if min_price:
            queryset = queryset.filter(price_per_night__gte=min_price)
        if max_price:
            queryset = queryset.filter(price_per_night__lte=max_price)
        if bedrooms:
            queryset = queryset.filter(bedrooms__gte=bedrooms)
        if max_guests:
            queryset = queryset.filter(max_guests__gte=max_guests)
        
        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def check_availability(self, request, pk=None):
        """Check property availability for specific dates"""
        property_obj = self.get_object()
        
        check_in_date = request.data.get('check_in_date')
        check_out_date = request.data.get('check_out_date')
        guests_count = request.data.get('guests_count', 1)
        
        if not check_in_date or not check_out_date:
            return Response(
                {'error': 'Check-in and check-out dates are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d').date()
            check_out = datetime.strptime(check_out_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if check_in >= check_out:
            return Response(
                {'error': 'Check-out date must be after check-in date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if guests_count > property_obj.max_guests:
            return Response({
                'available': False,
                'reason': f'Property accommodates maximum {property_obj.max_guests} guests'
            })
        
        # Check for conflicting bookings
        from bookings.models import Booking
        conflicting_bookings = Booking.objects.filter(
            property=property_obj,
            status__in=['confirmed', 'pending'],
            check_in_date__lt=check_out,
            check_out_date__gt=check_in
        )
        
        if conflicting_bookings.exists():
            return Response({
                'available': False,
                'reason': 'Property is not available for selected dates'
            })
        
        # Calculate pricing
        nights = (check_out - check_in).days
        base_price = property_obj.price_per_night * nights
        discounted_price = property_obj.get_display_price(request.user) * nights
        
        return Response({
            'available': True,
            'nights': nights,
            'base_price': base_price,
            'discounted_price': discounted_price,
            'savings': base_price - discounted_price,
            'price_per_night': property_obj.get_display_price(request.user)
        })

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get property statistics"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from bookings.models import Booking
        from django.db.models import Sum, Avg, Count
        from datetime import datetime, timedelta
        
        now = datetime.now()
        last_30_days = now - timedelta(days=30)
        last_year = now - timedelta(days=365)
        
        bookings = Booking.objects.filter(property=property_obj)
        
        stats = {
            'total_bookings': bookings.count(),
            'confirmed_bookings': bookings.filter(status='confirmed').count(),
            'completed_bookings': bookings.filter(status='completed').count(),
            'total_revenue': bookings.filter(status__in=['confirmed', 'completed']).aggregate(
                total=Sum('total_amount')
            )['total'] or 0,
            'average_booking_value': bookings.filter(status__in=['confirmed', 'completed']).aggregate(
                avg=Avg('total_amount')
            )['avg'] or 0,
            'occupancy_rate_30_days': 0,  # Calculate based on available days
            'bookings_last_30_days': bookings.filter(
                created_at__gte=last_30_days
            ).count(),
            'revenue_last_30_days': bookings.filter(
                created_at__gte=last_30_days,
                status__in=['confirmed', 'completed']
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
            'average_rating': 0,  # Will be calculated when reviews are implemented
            'response_rate': 100,  # Placeholder
        }
        
        return Response(stats)