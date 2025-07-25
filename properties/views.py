# properties/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.core.cache import cache
from django.http import HttpResponse
from datetime import datetime, timedelta
from django.utils import timezone
import uuid
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import openai
from django.conf import settings

# Import models and components
from .models import Property, PropertyImage, SavedProperty
from accounts.models import User

# Import serializers
from .serializers import (
    PropertySerializer, PropertyCreateSerializer, PropertyListSerializer,
    SavedPropertySerializer
)
from .filters import PropertyFilter


class PropertyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing properties with comprehensive functionality.
    """
    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Optimized queryset with proper access control based on effective role"""
        user = self.request.user
        effective_role = getattr(user, 'get_effective_role', lambda: user.user_type)()
        
        # Base queryset with optimizations
        base_queryset = Property.objects.select_related('owner').annotate(
            booking_count=Count('bookings', distinct=True)
        ).prefetch_related('images_set')
        
        if user.user_type == 'admin':
            return base_queryset.all()
        elif effective_role == 'owner':
            return base_queryset.filter(owner=user)
        else:
            # Users see properties from their trust network
            cache_key = f'user_accessible_properties_{user.id}'
            property_ids = cache.get(cache_key)
            
            if property_ids is None:
                try:
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
                except ImportError:
                    # Trust levels not available, show no properties
                    property_ids = []
                
                cache.set(cache_key, property_ids, timeout=300)  # 5 minutes
            
            return base_queryset.filter(id__in=property_ids)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return PropertyCreateSerializer
        elif self.action == 'list' or self.action == 'search':
            return PropertyListSerializer
        return PropertySerializer
    
    def list(self, request, *args, **kwargs):
        """List properties with advanced filtering"""
        return super().list(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """Create property"""
        return super().create(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        """Get property details"""
        return super().retrieve(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Update property"""
        property_obj = self.get_object()
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        """Partially update property"""
        property_obj = self.get_object()
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().partial_update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete property"""
        property_obj = self.get_object()
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only delete your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)
    
    @action(detail=True, methods=['patch'])
    def toggle_visibility(self, request, pk=None):
        """Toggle property visibility (owner only)"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        is_visible = request.data.get('is_visible')
        if is_visible is None:
            property_obj.is_visible = not property_obj.is_visible
        else:
            property_obj.is_visible = bool(is_visible)
        
        property_obj.save()
        
        # Update Beds24 visibility if synced
        if property_obj.beds24_property_id:
            try:
                from .tasks import update_beds24_visibility
                update_beds24_visibility.delay(str(property_obj.id), property_obj.is_visible)
            except ImportError:
                pass
        
        # Clear cache
        cache.delete(f'property_detail_{property_obj.id}')
        cache.delete(f'user_accessible_properties_{request.user.id}')
        
        return Response({
            'message': f'Property visibility updated to {property_obj.is_visible}',
            'is_visible': property_obj.is_visible
        })
    
    @action(detail=True, methods=['post'])
    def share_calendar(self, request, pk=None):
        """Share property availability calendar via email"""
        property_obj = self.get_object()
        
        # Only property owner can share calendar
        if property_obj.owner != request.user:
            return Response(
                {'error': 'Only property owner can share calendar'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get request data
        recipient_emails = request.data.get('emails', [])
        message = request.data.get('message', '')
        include_pricing = request.data.get('include_pricing', False)
        date_range_days = request.data.get('date_range_days', 365)
        
        if not recipient_emails:
            return Response(
                {'error': 'At least one recipient email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate unique calendar share token
        share_token = str(uuid.uuid4())
        
        # Store share token in cache with property info
        cache_key = f'calendar_share_{share_token}'
        cache.set(cache_key, {
            'property_id': str(property_obj.id),
            'include_pricing': include_pricing,
            'shared_by': str(request.user.id),
            'shared_at': datetime.now().isoformat()
        }, timeout=86400 * 30)  # 30 days
        
        # Generate calendar share URL
        calendar_url = f"{settings.FRONTEND_URL}/calendar/view/{share_token}"
        
        # Send emails to recipients
        context = {
            'property_title': property_obj.title,
            'property_address': property_obj.address,
            'owner_name': request.user.full_name,
            'personal_message': message,
            'calendar_url': calendar_url,
            'include_pricing': include_pricing,
            'date_range_days': date_range_days
        }
        
        sent_count = 0
        failed_emails = []
        
        for email in recipient_emails:
            try:
                send_mail(
                    subject=f"📅 {request.user.full_name} shared {property_obj.title}'s availability with you",
                    message=f"View calendar: {calendar_url}\n\n{message}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False
                )
                sent_count += 1
            except Exception as e:
                failed_emails.append(email)
        
        # Log activity if analytics available
        try:
            from analytics.models import ActivityLog
            ActivityLog.objects.create(
                action='calendar_shared',
                user=request.user,
                resource_type='property',
                resource_id=str(property_obj.id),
                details={
                    'recipients': recipient_emails,
                    'sent_count': sent_count,
                    'failed_count': len(failed_emails),
                    'include_pricing': include_pricing
                }
            )
        except ImportError:
            pass
        
        return Response({
            'message': f'Calendar shared with {sent_count} recipients',
            'sent_count': sent_count,
            'failed_emails': failed_emails,
            'share_url': calendar_url
        })
    
    @action(detail=False, methods=['get'])
    def view_shared_calendar(self, request):
        """View shared calendar (no authentication required)"""
        share_token = request.GET.get('token')
        
        if not share_token:
            return Response(
                {'error': 'Share token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get share info from cache
        cache_key = f'calendar_share_{share_token}'
        share_info = cache.get(cache_key)
        
        if not share_info:
            return Response(
                {'error': 'Invalid or expired share token'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get property
        try:
            property_obj = Property.objects.get(id=share_info['property_id'])
        except Property.DoesNotExist:
            return Response(
                {'error': 'Property not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get availability for next year
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=365)
        
        # Get bookings if available
        blocked_dates = []
        try:
            from bookings.models import Booking
            bookings = Booking.objects.filter(
                property=property_obj,
                status__in=['confirmed', 'pending'],
                check_out_date__gte=start_date,
                check_in_date__lte=end_date
            ).values('check_in_date', 'check_out_date', 'status')
            
            for booking in bookings:
                blocked_dates.append({
                    'start': booking['check_in_date'].isoformat(),
                    'end': booking['check_out_date'].isoformat(),
                    'status': booking['status']
                })
        except ImportError:
            pass
        
        response_data = {
            'property': {
                'title': property_obj.title,
                'address': property_obj.address,
                'city': property_obj.city,
                'max_guests': property_obj.max_guests,
                'bedrooms': property_obj.bedrooms,
                'bathrooms': float(property_obj.bathrooms)
            },
            'blocked_dates': blocked_dates,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            }
        }
        
        # Include pricing if allowed
        if share_info.get('include_pricing'):
            response_data['property']['price_per_night'] = float(property_obj.price_per_night)
        
        return Response(response_data)
    
    @action(detail=False, methods=['get'])
    def by_owner(self, request):
        """Get properties by specific owner"""
        owner_id = request.GET.get('owner_id')
        
        if not owner_id:
            return Response(
                {'error': 'owner_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if owner exists
        try:
            owner = User.objects.get(id=owner_id, user_type='owner')
        except User.DoesNotExist:
            return Response(
                {'error': 'Owner not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        user = request.user
        effective_role = getattr(user, 'get_effective_role', lambda: user.user_type)()
        
        # Build queryset based on permissions
        if user.user_type == 'admin':
            properties = Property.objects.filter(owner=owner)
        elif user.id == owner.id:
            properties = Property.objects.filter(owner=owner)
        elif effective_role == 'user':
            try:
                from trust_levels.models import OwnerTrustedNetwork
                has_access = OwnerTrustedNetwork.objects.filter(
                    owner=owner,
                    trusted_user=user,
                    status='active'
                ).exists()
                
                if not has_access:
                    return Response(
                        {'error': 'You do not have access to this owner\'s properties'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                properties = Property.objects.filter(
                    owner=owner,
                    status='active',
                    is_visible=True
                )
            except ImportError:
                return Response(
                    {'error': 'Access control not available'},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            return Response(
                {'error': 'You do not have permission to view these properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Apply optimizations and additional filters
        properties = properties.select_related('owner').annotate(
            booking_count=Count('bookings', distinct=True)
        ).prefetch_related('images_set')
        
        status_filter = request.GET.get('status')
        if status_filter:
            properties = properties.filter(status=status_filter)
        
        is_featured = request.GET.get('is_featured')
        if is_featured is not None:
            properties = properties.filter(is_featured=is_featured.lower() == 'true')
        
        properties = properties.order_by('-created_at')
        
        # Paginate results
        page = self.paginate_queryset(properties)
        if page is not None:
            serializer = PropertyListSerializer(page, many=True, context={'request': request})
            response_data = self.get_paginated_response(serializer.data)
            
            response_data.data['owner'] = {
                'id': str(owner.id),
                'full_name': owner.full_name,
                'email': owner.email,
                'properties_count': properties.count()
            }
            
            return response_data
        
        serializer = PropertyListSerializer(properties, many=True, context={'request': request})
        return Response({
            'owner': {
                'id': str(owner.id),
                'full_name': owner.full_name,
                'email': owner.email,
                'properties_count': properties.count()
            },
            'properties': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def owner_list(self, request):
        """Get list of property owners (for filtering)"""
        user = request.user
        effective_role = getattr(user, 'get_effective_role', lambda: user.user_type)()
        
        if user.user_type == 'admin':
            owners = User.objects.filter(
                user_type='owner',
                properties__isnull=False
            ).distinct().annotate(
                property_count=Count('properties')
            ).values('id', 'full_name', 'email', 'property_count')
        
        elif effective_role == 'user':
            try:
                from trust_levels.models import OwnerTrustedNetwork
                connected_owners = OwnerTrustedNetwork.objects.filter(
                    trusted_user=user,
                    status='active'
                ).values_list('owner_id', flat=True)
                
                owners = User.objects.filter(
                    id__in=connected_owners,
                    properties__isnull=False
                ).distinct().annotate(
                    property_count=Count('properties', filter=Q(
                        properties__status='active',
                        properties__is_visible=True
                    ))
                ).values('id', 'full_name', 'email', 'property_count')
            except ImportError:
                owners = []
        
        elif user.user_type == 'owner':
            owners = User.objects.filter(
                id=user.id
            ).annotate(
                property_count=Count('properties')
            ).values('id', 'full_name', 'email', 'property_count')
        
        else:
            owners = []
        
        return Response({
            'count': len(owners),
            'owners': list(owners)
        })
    
    @action(detail=True, methods=['get'])
    def ical_export(self, request, pk=None):
        """Export property calendar as iCal"""
        property_obj = self.get_object()
        
        start_date = request.GET.get('start')
        end_date = request.GET.get('end')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = datetime.now().date()
            
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = start_date + timedelta(days=365)
        
        # Generate basic iCal content
        ical_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Your Company//Property Calendar//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:{property_obj.title} Calendar
X-WR-TIMEZONE:UTC
BEGIN:VTIMEZONE
TZID:UTC
BEGIN:STANDARD
DTSTART:19700101T000000Z
TZOFFSETFROM:+0000
TZOFFSETTO:+0000
TZNAME:UTC
END:STANDARD
END:VTIMEZONE
END:VCALENDAR"""
        
        response = HttpResponse(ical_content, content_type='text/calendar; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{property_obj.title}_calendar.ics"'
        return response

    @action(detail=True, methods=['post'])
    def setup_ical_sync(self, request, pk=None):
        """Setup iCal sync settings for property"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
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
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
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
        
        # Basic URL validation
        if not calendar_url.startswith(('http://', 'https://')):
            return Response(
                {'error': 'Invalid calendar URL format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
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
                'events_found': 0
            }
        })

    @action(detail=True, methods=['post'])
    def sync_ical(self, request, pk=None):
        """Manually trigger iCal sync"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if property_obj.beds24_property_id:
            try:
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
            except ImportError:
                return Response(
                    {'error': 'Sync service not available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
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
            try:
                queryset = queryset.filter(price_per_night__gte=float(min_price))
            except ValueError:
                pass
        if max_price:
            try:
                queryset = queryset.filter(price_per_night__lte=float(max_price))
            except ValueError:
                pass
        if bedrooms:
            try:
                queryset = queryset.filter(bedrooms__gte=int(bedrooms))
            except ValueError:
                pass
        if max_guests:
            try:
                queryset = queryset.filter(max_guests__gte=int(max_guests))
            except ValueError:
                pass
        
        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PropertyListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = PropertyListSerializer(queryset, many=True, context={'request': request})
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
        try:
            from bookings.models import Booking
            conflicting_bookings = Booking.objects.filter(
                property=property_obj,
                check_in_date__lt=check_out,
                check_out_date__gt=check_in,
                status__in=['confirmed', 'pending']
            )
            
            if conflicting_bookings.exists():
                return Response({
                    'available': False,
                    'reason': 'Property is not available for selected dates',
                    'conflicting_dates': list(conflicting_bookings.values(
                        'check_in_date', 'check_out_date'
                    ))
                })
        except ImportError:
            pass
        
        # Calculate pricing
        nights = (check_out - check_in).days
        base_price = property_obj.price_per_night * nights
        
        try:
            discounted_price = property_obj.get_display_price(request.user, nights, guests_count)
        except:
            discounted_price = base_price
        
        return Response({
            'available': True,
            'nights': nights,
            'base_price': float(base_price),
            'discounted_price': float(discounted_price),
            'savings': float(base_price - discounted_price),
            'price_per_night': float(discounted_price / nights if nights > 0 else discounted_price)
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
        
        try:
            from bookings.models import Booking
            from django.db.models import Sum, Avg
            from datetime import timedelta
            
            now = datetime.now()
            last_30_days = now - timedelta(days=30)
            
            bookings = Booking.objects.filter(property=property_obj)
            
            stats = {
                'total_bookings': bookings.count(),
                'confirmed_bookings': bookings.filter(status='confirmed').count(),
                'completed_bookings': bookings.filter(status='completed').count(),
                'total_revenue': float(bookings.filter(
                    status__in=['confirmed', 'completed']
                ).aggregate(total=Sum('total_amount'))['total'] or 0),
                'average_booking_value': float(bookings.filter(
                    status__in=['confirmed', 'completed']
                ).aggregate(avg=Avg('total_amount'))['avg'] or 0),
                'bookings_last_30_days': bookings.filter(
                    created_at__gte=last_30_days
                ).count(),
                'revenue_last_30_days': float(bookings.filter(
                    created_at__gte=last_30_days,
                    status__in=['confirmed', 'completed']
                ).aggregate(total=Sum('total_amount'))['total'] or 0),
            }
        except ImportError:
            stats = {
                'total_bookings': 0,
                'confirmed_bookings': 0,
                'completed_bookings': 0,
                'total_revenue': 0,
                'average_booking_value': 0,
                'bookings_last_30_days': 0,
                'revenue_last_30_days': 0,
            }
        
        return Response(stats)
    
    @action(detail=True, methods=['post'])
    def save_property(self, request, pk=None):
        """Save/bookmark a property for later reference"""
        property_obj = self.get_object()
        
        if property_obj.owner == request.user:
            return Response(
                {'error': 'You cannot save your own property'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user has access to this property
        user = request.user
        effective_role = getattr(user, 'get_effective_role', lambda: user.user_type)()
        
        if effective_role == 'user':
            try:
                from trust_levels.models import OwnerTrustedNetwork
                has_access = OwnerTrustedNetwork.objects.filter(
                    owner=property_obj.owner,
                    trusted_user=user,
                    status='active'
                ).exists()
                
                if not has_access:
                    return Response(
                        {'error': 'You must have access through trust network to save this property'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except ImportError:
                return Response(
                    {'error': 'Access control not available'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        saved_property, created = SavedProperty.objects.get_or_create(
            user=request.user,
            property=property_obj,
            defaults={'notes': request.data.get('notes', '')}
        )
        
        if not created:
            return Response(
                {'error': 'Property is already saved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cache.delete(f'user_accessible_properties_{request.user.id}')
        
        return Response({
            'message': 'Property saved successfully',
            'saved': True,
            'saved_property': {
                'id': str(saved_property.id),
                'property_id': str(property_obj.id),
                'saved_at': saved_property.saved_at,
                'notes': saved_property.notes
            }
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'])
    def unsave_property(self, request, pk=None):
        """Remove property from saved list"""
        property_obj = self.get_object()
        
        try:
            saved_property = SavedProperty.objects.get(
                user=request.user,
                property=property_obj
            )
            saved_property.delete()
            
            cache.delete(f'user_accessible_properties_{request.user.id}')
            
            return Response({
                'message': 'Property removed from saved list',
                'property_id': str(property_obj.id)
            }, status=status.HTTP_200_OK)
            
        except SavedProperty.DoesNotExist:
            return Response(
                {'error': 'Property is not in your saved list'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def saved_properties(self, request):
        """Get all properties saved by the current user"""
        user = request.user
        
        saved_properties = SavedProperty.objects.filter(
            user=user
        ).select_related('property__owner').prefetch_related('property__images_set')
        
        # Apply filters
        city = request.GET.get('city')
        if city:
            saved_properties = saved_properties.filter(property__city__icontains=city)
        
        min_price = request.GET.get('min_price')
        if min_price:
            try:
                saved_properties = saved_properties.filter(property__price_per_night__gte=float(min_price))
            except ValueError:
                pass
        
        max_price = request.GET.get('max_price')
        if max_price:
            try:
                saved_properties = saved_properties.filter(property__price_per_night__lte=float(max_price))
            except ValueError:
                pass
        
        bedrooms = request.GET.get('bedrooms')
        if bedrooms:
            try:
                saved_properties = saved_properties.filter(property__bedrooms__gte=int(bedrooms))
            except ValueError:
                pass
        
        saved_properties = saved_properties.order_by('-saved_at')
        
        # Paginate results
        page = self.paginate_queryset(saved_properties)
        
        def format_saved_property(saved_property):
            property_obj = saved_property.property
            
            images = []
            for image in property_obj.images_set.all():
                images.append({
                    'id': str(image.id),
                    'image_url': image.image_url,
                    'is_primary': image.is_primary,
                    'order': image.order
                })
            
            try:
                display_price = float(property_obj.get_display_price(user))
            except:
                display_price = float(property_obj.price_per_night)
            
            return {
                'id': str(property_obj.id),
                'title': property_obj.title,
                'description': property_obj.description,
                'city': property_obj.city,
                'display_price': display_price,
                'bedrooms': property_obj.bedrooms,
                'bathrooms': float(property_obj.bathrooms),
                'max_guests': property_obj.max_guests,
                'images': images,
                'owner_name': property_obj.owner.full_name,
                'is_saved': True,
                'saved_info': {
                    'saved_id': str(saved_property.id),
                    'saved_at': saved_property.saved_at,
                    'notes': saved_property.notes
                }
            }
        
        if page is not None:
            results = [format_saved_property(sp) for sp in page]
            response_data = self.get_paginated_response(results)
            response_data.data['total_saved'] = saved_properties.count()
            return response_data
        
        results = [format_saved_property(sp) for sp in saved_properties]
        
        return Response({
            'total_saved': len(results),
            'count': len(results),
            'page': 1,
            'total_pages': 1,
            'results': results
        })
    
    @action(detail=True, methods=['post', 'patch'])
    def manage_images(self, request, pk=None):
        """Add, update, or reorder property images"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        action_type = request.data.get('action')
        
        if action_type == 'add':
            image_url = request.data.get('image_url')
            caption = request.data.get('caption', '')
            room_type = request.data.get('room_type', '')
            is_primary = request.data.get('is_primary', False)
            
            if not image_url:
                return Response(
                    {'error': 'image_url is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # If setting as primary, unset other primary images
            if is_primary:
                PropertyImage.objects.filter(property=property_obj, is_primary=True).update(is_primary=False)
            
            # Get next order
            last_image = PropertyImage.objects.filter(property=property_obj).order_by('-order').first()
            order = (last_image.order + 1) if last_image else 0
            
            image = PropertyImage.objects.create(
                property=property_obj,
                image_url=image_url,
                caption=caption,
                room_type=room_type,
                is_primary=is_primary,
                order=order
            )
            
            return Response({
                'message': 'Image added successfully',
                'image': {
                    'id': str(image.id),
                    'image_url': image.image_url,
                    'caption': image.caption,
                    'room_type': image.room_type,
                    'is_primary': image.is_primary,
                    'order': image.order
                }
            }, status=status.HTTP_201_CREATED)
        
        elif action_type == 'reorder':
            image_orders = request.data.get('image_orders', [])
            
            for item in image_orders:
                try:
                    image = PropertyImage.objects.get(
                        id=item['id'],
                        property=property_obj
                    )
                    image.order = item['order']
                    image.save()
                except PropertyImage.DoesNotExist:
                    continue
            
            return Response({'message': 'Images reordered successfully'})
        
        elif action_type == 'set_primary':
            image_id = request.data.get('image_id')
            
            try:
                # Unset all primary images
                PropertyImage.objects.filter(property=property_obj).update(is_primary=False)
                
                # Set new primary
                image = PropertyImage.objects.get(id=image_id, property=property_obj)
                image.is_primary = True
                image.save()
                
                return Response({'message': 'Primary image updated successfully'})
            except PropertyImage.DoesNotExist:
                return Response(
                    {'error': 'Image not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        else:
            return Response(
                {'error': 'Invalid action. Use: add, reorder, or set_primary'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['delete'])
    def delete_image(self, request, pk=None):
        """Delete a property image"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        image_id = request.data.get('image_id')
        
        try:
            image = PropertyImage.objects.get(id=image_id, property=property_obj)
            was_primary = image.is_primary
            image.delete()
            
            # If deleted image was primary, set first remaining image as primary
            if was_primary:
                first_image = PropertyImage.objects.filter(property=property_obj).order_by('order').first()
                if first_image:
                    first_image.is_primary = True
                    first_image.save()
            
            return Response({'message': 'Image deleted successfully'})
        except PropertyImage.DoesNotExist:
            return Response(
                {'error': 'Image not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def availability_calendar(self, request, pk=None):
        """Get property availability calendar for a date range"""
        property_obj = self.get_object()
        
        # Parse date parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if not start_date:
            start_date = datetime.now().date()
        else:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid start_date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if not end_date:
            end_date = start_date + timedelta(days=90)  # Default 3 months
        else:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid end_date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if end_date <= start_date:
            return Response(
                {'error': 'end_date must be after start_date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get bookings for the date range
        calendar_data = []
        current_date = start_date
        
        try:
            from bookings.models import Booking
            bookings = Booking.objects.filter(
                property=property_obj,
                check_in_date__lte=end_date,
                check_out_date__gte=start_date,
                status__in=['confirmed', 'pending']
            )
            
            # Create a set of booked dates
            booked_dates = set()
            for booking in bookings:
                booking_start = max(booking.check_in_date, start_date)
                booking_end = min(booking.check_out_date, end_date)
                
                current = booking_start
                while current < booking_end:
                    booked_dates.add(current)
                    current += timedelta(days=1)
        except ImportError:
            booked_dates = set()
        
        # Build calendar data
        while current_date <= end_date:
            is_available = current_date not in booked_dates
            
            # Check if it's in the past
            if current_date < datetime.now().date():
                is_available = False
                status_reason = 'past'
            elif current_date in booked_dates:
                status_reason = 'booked'
            else:
                status_reason = 'available'
            
            calendar_data.append({
                'date': current_date.isoformat(),
                'available': is_available,
                'status': status_reason,
                'price': float(property_obj.get_display_price(request.user, 1, 1)) if is_available else None,
                'minimum_stay': property_obj.minimum_stay
            })
            
            current_date += timedelta(days=1)
        
        return Response({
            'property_id': str(property_obj.id),
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'calendar': calendar_data,
            'summary': {
                'total_days': len(calendar_data),
                'available_days': len([d for d in calendar_data if d['available']]),
                'booked_days': len([d for d in calendar_data if d['status'] == 'booked'])
            }
        })
    
    @action(detail=False, methods=['get'])
    def featured_properties(self, request):
        """Get featured properties"""
        queryset = self.get_queryset().filter(is_featured=True, is_visible=True, status='active')
        
        # Limit to a reasonable number for featured properties
        limit = request.GET.get('limit', 10)
        try:
            limit = int(limit)
            if limit > 50:  # Max limit
                limit = 50
        except ValueError:
            limit = 10
        
        queryset = queryset.order_by('-created_at')[:limit]
        
        serializer = PropertyListSerializer(queryset, many=True, context={'request': request})
        return Response({
            'count': len(serializer.data),
            'featured_properties': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def nearby_properties(self, request):
        """Get properties near a specific location"""
        latitude = request.GET.get('latitude')
        longitude = request.GET.get('longitude')
        radius = request.GET.get('radius', 10)  # Default 10km radius
        
        if not latitude or not longitude:
            return Response(
                {'error': 'latitude and longitude parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
            radius = float(radius)
        except ValueError:
            return Response(
                {'error': 'Invalid coordinate or radius values'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Basic distance calculation (simplified)
        # In production, you'd want to use PostGIS or similar for proper geo queries
        queryset = self.get_queryset().filter(
            latitude__isnull=False,
            longitude__isnull=False,
            status='active',
            is_visible=True
        )
        
        # Filter by approximate distance (basic calculation)
        # This is a simplified approach - use proper geo libraries for production
        lat_range = radius / 111.0  # Rough conversion km to degrees
        lon_range = radius / (111.0 * abs(latitude))
        
        queryset = queryset.filter(
            latitude__gte=latitude - lat_range,
            latitude__lte=latitude + lat_range,
            longitude__gte=longitude - lon_range,
            longitude__lte=longitude + lon_range
        )
        
        # Limit results
        limit = request.GET.get('limit', 20)
        try:
            limit = int(limit)
            if limit > 50:
                limit = 50
        except ValueError:
            limit = 20
        
        queryset = queryset[:limit]
        
        serializer = PropertyListSerializer(queryset, many=True, context={'request': request})
        return Response({
            'search_center': {
                'latitude': latitude,
                'longitude': longitude,
                'radius_km': radius
            },
            'count': len(serializer.data),
            'properties': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update property status (owner/admin only)"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        new_status = request.data.get('status')
        if not new_status:
            return Response(
                {'error': 'status field is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate status
        valid_statuses = [choice[0] for choice in Property.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Choose from: {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = property_obj.status
        property_obj.status = new_status
        property_obj.save()
        
        # Clear cache
        cache.delete(f'property_detail_{property_obj.id}')
        cache.delete(f'user_accessible_properties_{request.user.id}')
        
        # Log activity if analytics available
        try:
            from analytics.models import ActivityLog
            ActivityLog.objects.create(
                action='property_status_changed',
                user=request.user,
                resource_type='property',
                resource_id=str(property_obj.id),
                details={
                    'old_status': old_status,
                    'new_status': new_status,
                    'property_title': property_obj.title
                }
            )
        except ImportError:
            pass
        
        return Response({
            'message': f'Property status updated from {old_status} to {new_status}',
            'old_status': old_status,
            'new_status': new_status
        })
    
    @action(detail=True, methods=['get'])
    def booking_history(self, request, pk=None):
        """Get booking history for a property (owner/admin only)"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user and request.user.user_type != 'admin':
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            from bookings.models import Booking
            bookings = Booking.objects.filter(
                property=property_obj
            ).select_related('guest').order_by('-created_at')
            
            # Apply status filter if provided
            status_filter = request.GET.get('status')
            if status_filter:
                bookings = bookings.filter(status=status_filter)
            
            # Apply date range filter
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            
            if start_date:
                try:
                    start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                    bookings = bookings.filter(check_in_date__gte=start_date)
                except ValueError:
                    pass
            
            if end_date:
                try:
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                    bookings = bookings.filter(check_out_date__lte=end_date)
                except ValueError:
                    pass
            
            # Paginate results
            page = self.paginate_queryset(bookings)
            
            def format_booking(booking):
                return {
                    'id': str(booking.id),
                    'guest_name': booking.guest.full_name,
                    'guest_email': booking.guest.email,
                    'check_in_date': booking.check_in_date,
                    'check_out_date': booking.check_out_date,
                    'guests_count': booking.guests_count,
                    'total_amount': float(booking.total_amount),
                    'status': booking.status,
                    'created_at': booking.created_at,
                    'nights': (booking.check_out_date - booking.check_in_date).days
                }
            
            if page is not None:
                results = [format_booking(booking) for booking in page]
                return self.get_paginated_response(results)
            
            results = [format_booking(booking) for booking in bookings]
            return Response({
                'count': len(results),
                'bookings': results
            })
            
        except ImportError:
            return Response({
                'count': 0,
                'bookings': [],
                'message': 'Booking system not available'
            })
            
            


class AIPropertyExtractView(APIView):
    def post(self, request):
        user_text = request.data.get("text", "")
        if not user_text:
            return Response({"error": "No text provided."}, status=status.HTTP_400_BAD_REQUEST)

        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        prompt = f"""
You are a helpful assistant for a property onboarding platform.
A user has described their property as follows:

\"\"\"{user_text}\"\"\"

1. Extract as much structured information as possible (property type, location, bedrooms, bathrooms, beds, amenities, features, etc.) as a JSON object.
2. Generate 3 creative property titles and 3 matching descriptions based on the user's text.
3. List any important fields that are missing and should be asked for.

Respond in this JSON format:
{{
  "extracted": {{
    "property_type": ...,
    "location": ...,
    "bedrooms": ...,
    "bathrooms": ...,
    "beds": ...,
    "amenities": [...],
    "features": [...],
    "other": ...
  }},
  "titles": ["...", "...", "..."],
  "descriptions": ["...", "...", "..."],
  "missing_fields": ["..."]
}}
"""

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.7,
            )
            import json
            ai_content = response.choices[0].message.content
            try:
                result = json.loads(ai_content)
            except Exception:
                import re
                match = re.search(r'({.*})', ai_content, re.DOTALL)
                if match:
                    result = json.loads(match.group(1))
                else:
                    return Response({"error": "AI response could not be parsed."}, status=500)
            return Response(result)
        except Exception as e:
            return Response({"error": str(e)}, status=500)