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

from openai import OpenAI
import re
from typing import Dict, List, Any

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
            
            


# Enhanced properties/views.py - AI Extraction Section

import json
import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from openai import OpenAI
from django.conf import settings

class AIPropertyExtractView(APIView):
    """
    Enhanced AI extraction that supports conversational property onboarding
    with better extraction and conversational title/description generation
    """
    
    def post(self, request):
        action = request.data.get("action", "extract")
        
        if action == "extract":
            return self._extract_property_data(request)
        elif action == "generate_question":
            return self._generate_follow_up_question(request)
        elif action == "progressive_extract":
            return self._progressive_extraction(request)
        elif action == "generate_titles":
            return self._generate_conversational_titles(request)
        elif action == "generate_descriptions":
            return self._generate_conversational_descriptions(request)
        else:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)
    
    def _extract_property_data(self, request):
        """Enhanced extraction with better AI prompting"""
        user_text = request.data.get("text", "")
        if not user_text:
            return Response({"error": "No text provided."}, status=status.HTTP_400_BAD_REQUEST)

        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        prompt = f"""
You are an expert property listing assistant. Extract comprehensive information from this property description:

\"\"\"{user_text}\"\"\"

Extract ALL possible information and respond in this exact JSON format:
{{
  "extracted": {{
    "property_type": "apartment|house|villa|cabin|loft|other",
    "place_type": "entire_place|private_room|shared_room", 
    "city": "city name",
    "country": "country name",
    "address": "full address if mentioned",
    "neighborhood": "neighborhood/area name",
    "bedrooms": number,
    "bathrooms": number,
    "beds": number,
    "max_guests": number,
    "square_feet": number,
    "amenities": ["wifi", "kitchen", "tv", "air_conditioning", "parking", "pool", "washer", "dryer", "dishwasher", "gym", "hot_tub", "balcony", "garden"],
    "display_price": number,
    "price_per_night": number,
    "smoking_allowed": true/false,
    "pets_allowed": true/false,
    "events_allowed": true/false,
    "children_welcome": true/false,
    "instant_book_enabled": true/false,
    "minimum_stay": number,
    "maximum_stay": number,
    "check_in_time_start": "HH:MM",
    "check_out_time": "HH:MM",
    "trust_level_1_discount": number,
    "trust_level_2_discount": number,
    "trust_level_3_discount": number,
    "trust_level_4_discount": number,
    "trust_level_5_discount": number,
    "title": "suggested title",
    "description": "enhanced description"
  }},
  "titles": ["3 creative property titles"],
  "descriptions": ["3 detailed descriptions"],
  "confidence_score": 0.0-1.0,
  "insights": {{
    "hosting_style": "hands-on|relaxed|professional|friendly",
    "property_vibe": "cozy|modern|luxury|rustic|artistic|family-friendly",
    "target_guests": "business|leisure|families|couples|solo",
    "unique_features": ["list of special features"],
    "location_highlights": ["nearby attractions or benefits"]
  }}
}}

EXTRACTION RULES:
1. Use ONLY exact values from allowed lists for property_type, place_type, amenities
2. For trust level discounts, extract any percentage mentions (Bronze 5%, Silver 10%, etc.)
3. Set confidence_score based on information completeness
4. Extract pricing even if mentioned casually ("around $100", "about 150 per night")
5. Infer boolean values from context ("no smoking" = smoking_allowed: false)
6. Extract location details carefully (distinguish city from neighborhood)
7. For times, convert to 24-hour format (3pm = "15:00")
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.3,
            )
            
            ai_content = response.choices[0].message.content
            result = self._parse_ai_response(ai_content)
            result = self._validate_and_enhance_extraction(result)
            
            return Response(result)
            
        except Exception as e:
            return Response({"error": str(e)}, status=500)
    
    def _progressive_extraction(self, request):
        """Enhanced progressive extraction with better context understanding"""
        current_response = request.data.get("current_response", "")
        question_context = request.data.get("question_context", "")
        previous_data = request.data.get("previous_data", {})
        conversation_history = request.data.get("conversation_history", [])
        current_completion = request.data.get("current_completion_percentage", 0)
        
        if not current_response:
            return Response({"error": "Current response required"}, status=status.HTTP_400_BAD_REQUEST)
        
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Build conversation context
        conversation_context = ""
        if conversation_history:
            conversation_context = "\n".join([
                f"Q: {entry.get('question', 'N/A')}\nA: {entry.get('response', '')}" 
                for entry in conversation_history[-3:]
            ])
        
        prompt = f"""
You are extracting property information progressively from an ongoing conversation.

CONVERSATION CONTEXT:
{conversation_context}

CURRENT QUESTION CONTEXT: {question_context}
USER'S CURRENT RESPONSE: {current_response}

PREVIOUSLY EXTRACTED DATA: {json.dumps(previous_data, indent=2)}
CURRENT COMPLETION: {current_completion}%

Extract ONLY NEW or UPDATED information from the current response. Be very careful to:

1. Extract trust level discount percentages (Bronze 2%, Silver 5%, Gold 8%, Platinum 12%, Diamond 15%)
2. Identify property features, amenities, and policies mentioned
3. Extract location details (city, country, neighborhood, address)
4. Pick up pricing hints, capacity details, room information
5. Understand hosting preferences and house rules
6. Detect any timing information (check-in/out times)

Respond in this JSON format:
{{
  "extracted": {{
    "property_type": "apartment|house|villa|cabin|loft|other",
    "place_type": "entire_place|private_room|shared_room",
    "city": "city name",
    "country": "country name",
    "address": "full address",
    "neighborhood": "area name",
    "bedrooms": number,
    "bathrooms": number,
    "max_guests": number,
    "amenities": ["list from: wifi, kitchen, tv, air_conditioning, parking, pool, washer, dryer, dishwasher, gym, hot_tub, balcony, garden"],
    "display_price": number,
    "price_per_night": number,
    "smoking_allowed": true/false,
    "pets_allowed": true/false,
    "events_allowed": true/false,
    "children_welcome": true/false,
    "instant_book_enabled": true/false,
    "trust_level_1_discount": number,
    "trust_level_2_discount": number,
    "trust_level_3_discount": number,
    "trust_level_4_discount": number,
    "trust_level_5_discount": number,
    "check_in_time_start": "HH:MM",
    "check_out_time": "HH:MM",
    "title": "title suggestion",
    "description": "description snippet"
  }},
  "insights": {{
    "hosting_style": "hands-on|relaxed|professional|friendly",
    "property_vibe": "cozy|modern|luxury|rustic|artistic|family-friendly",
    "guest_focus": "business|leisure|families|couples|solo",
    "extracted_confidence": 0.0-1.0
  }},
  "next_question_hint": "What aspect to explore next based on what's missing"
}}

ONLY include fields where you found NEW information. Leave out fields with no new data.
Use exact values from allowed lists. Convert times to 24-hour format.
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.4,
            )
            
            ai_content = response.choices[0].message.content
            result = self._parse_ai_response(ai_content)
            
            if "extracted" in result:
                result["extracted"] = self._validate_extracted_fields(result["extracted"])
            
            return Response(result)
            
        except Exception as e:
            return Response({"error": str(e)}, status=500)
    
    def _generate_conversational_titles(self, request):
        """Generate engaging, conversational property titles"""
        property_data = request.data.get("property_data", {})
        conversation_context = request.data.get("conversation_context", "")
        style = request.data.get("style", "conversational")
        
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        property_context = self._build_property_context(property_data)
        
        prompt = f"""
Create 3 engaging property titles for this listing:

PROPERTY DETAILS:
{property_context}

CONVERSATION CONTEXT:
{conversation_context}

Generate 3 distinct title styles:
1. DESCRIPTIVE & LOCATION-FOCUSED: Highlight location and key features
2. EXPERIENCE-FOCUSED: Emphasize the guest experience and feeling
3. UNIQUE & CREATIVE: Creative, memorable, and distinctive

REQUIREMENTS:
- Each title should be 4-12 words
- Include the property type and location hint if available
- Make them engaging and clickable
- Avoid generic phrases like "Beautiful Property"
- Include unique selling points mentioned in conversation
- Match the tone: warm, welcoming, and authentic

Examples of GOOD titles:
- "Cozy Downtown Loft with Rooftop Views"
- "Charming Victorian Home Near Golden Gate"
- "Modern Retreat with Pool & Mountain Views"
- "Artist's Haven in Historic Arts District"

Return as JSON:
{{
  "titles": ["title 1", "title 2", "title 3"],
  "explanations": ["why this title works", "reasoning for title 2", "reasoning for title 3"]
}}
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7,
            )
            
            ai_content = response.choices[0].message.content
            result = self._parse_ai_response(ai_content)
            
            if "titles" not in result or not result["titles"]:
                property_type = property_data.get('property_type', 'Property').title()
                city = property_data.get('city', 'Great Location')
                guests = property_data.get('max_guests', 'Guests')
                
                result["titles"] = [
                    f"Beautiful {property_type} in {city}",
                    f"Comfortable Stay for {guests} Guests",
                    f"Perfect {property_type} Experience"
                ]
            
            return Response({
                "titles": result.get("titles", [])[:3],
                "explanations": result.get("explanations", [])
            })
            
        except Exception as e:
            property_type = property_data.get('property_type', 'Property').title()
            city = property_data.get('city', 'Great Location')
            guests = property_data.get('max_guests', 'Guests')
            
            fallback_titles = [
                f"Beautiful {property_type} in {city}",
                f"Comfortable Stay for {guests} Guests",
                f"Perfect {property_type} Experience"
            ]
            return Response({
                "titles": fallback_titles,
                "error": "AI generation failed, using fallback titles"
            })
    
    def _generate_conversational_descriptions(self, request):
        """Generate engaging, detailed property descriptions"""
        property_data = request.data.get("property_data", {})
        conversation_context = request.data.get("conversation_context", "")
        style = request.data.get("style", "engaging")
        
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        property_context = self._build_property_context(property_data)
        
        prompt = f"""
Create 3 engaging property descriptions for this listing:

PROPERTY DETAILS:
{property_context}

CONVERSATION CONTEXT:
{conversation_context}

Generate 3 distinct description styles:

1. WARM & PERSONAL: Write as if the host is personally welcoming guests
2. FEATURE-FOCUSED: Highlight amenities, location, and practical benefits
3. EXPERIENCE-DRIVEN: Paint a picture of the guest experience and lifestyle

REQUIREMENTS:
- Each description should be 150-300 words
- Include specific details mentioned in conversation
- Make guests visualize themselves staying there
- Mention key amenities and unique features
- Include location benefits if available
- End with a welcoming invitation
- Use active, engaging language
- Avoid generic real estate language

STRUCTURE for each description:
- Opening hook (what makes this special)
- Space details (rooms, capacity, layout)
- Amenities and features
- Location benefits
- Guest experience highlights
- Warm closing invitation

Return as JSON:
{{
  "descriptions": ["description 1", "description 2", "description 3"],
  "styles": ["warm_personal", "feature_focused", "experience_driven"]
}}
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.8,
            )
            
            ai_content = response.choices[0].message.content
            result = self._parse_ai_response(ai_content)
            
            if "descriptions" not in result or not result["descriptions"]:
                result["descriptions"] = self._generate_fallback_descriptions(property_data)
            
            return Response({
                "descriptions": result.get("descriptions", [])[:3],
                "styles": result.get("styles", ["warm_personal", "feature_focused", "experience_driven"])
            })
            
        except Exception as e:
            fallback_descriptions = self._generate_fallback_descriptions(property_data)
            return Response({
                "descriptions": fallback_descriptions,
                "error": "AI generation failed, using fallback descriptions"
            })
    
    def _generate_follow_up_question(self, request):
        """Enhanced question generation with better context awareness"""
        conversation_history = request.data.get("conversation_history", [])
        current_step = request.data.get("current_step", 1)
        extracted_so_far = request.data.get("extracted_data", {})
        completion_percentage = request.data.get("completion_percentage", 0)
        
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Build context from conversation
        context = ""
        if conversation_history:
            context = "\n".join([
                f"Q: {entry.get('question', 'N/A')}\nA: {entry.get('response', '')}" 
                for entry in conversation_history[-3:]
            ])
        
        extracted_context = json.dumps(extracted_so_far, indent=2) if extracted_so_far else "No data extracted yet"
        
        prompt = f"""
Generate the next engaging question for a property onboarding conversation.

CONVERSATION HISTORY:
{context}

EXTRACTED DATA SO FAR:
{extracted_context}

COMPLETION PERCENTAGE: {completion_percentage}%
CURRENT STEP: {current_step}

CONTEXT:
- If completion < 40%: Focus on basic property details, location, size
- If completion 40-70%: Explore amenities, unique features, guest experience
- If completion > 70%: Ask about pricing, policies, hosting preferences

Generate ONE conversational question that:
1. Builds on what they've already shared
2. Explores missing important information
3. Feels natural and engaging
4. Encourages detailed responses
5. Shows genuine interest in their property

Return just the question text, nothing else. Make it warm and conversational.
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.8,
            )
            
            question = response.choices[0].message.content.strip()
            question = re.sub(r'^["\']|["\']$', '', question)
            
            return Response({"question": question})
            
        except Exception as e:
            if completion_percentage < 40:
                fallback = "What makes your property special? Tell me about the space and what guests will love about it!"
            elif completion_percentage < 70:
                fallback = "What amenities and features does your property offer that will make guests' stay memorable?"
            else:
                fallback = "What's your hosting style like, and what policies do you want to set for guests?"
            
            return Response({"question": fallback})
    
    def _build_property_context(self, property_data):
        """Build comprehensive context from property data"""
        context_parts = []
        
        if property_data.get("property_type"):
            context_parts.append(f"Property Type: {property_data['property_type'].title()}")
        
        if property_data.get("place_type"):
            place_type_map = {
                "entire_place": "Entire place",
                "private_room": "Private room", 
                "shared_room": "Shared room"
            }
            context_parts.append(f"Space Type: {place_type_map.get(property_data['place_type'], property_data['place_type'])}")
        
        # Location
        location_parts = []
        if property_data.get("neighborhood"):
            location_parts.append(property_data["neighborhood"])
        if property_data.get("city"):
            location_parts.append(property_data["city"])
        if property_data.get("country"):
            location_parts.append(property_data["country"])
        
        if location_parts:
            context_parts.append(f"Location: {', '.join(location_parts)}")
        
        # Capacity and rooms
        if property_data.get("max_guests"):
            context_parts.append(f"Capacity: {property_data['max_guests']} guests")
        
        rooms = []
        if property_data.get("bedrooms"):
            rooms.append(f"{property_data['bedrooms']} bedroom(s)")
        if property_data.get("bathrooms"):
            rooms.append(f"{property_data['bathrooms']} bathroom(s)")
        
        if rooms:
            context_parts.append(f"Rooms: {', '.join(rooms)}")
        
        # Amenities
        if property_data.get("amenities"):
            amenity_labels = {
                'wifi': 'WiFi', 'kitchen': 'Kitchen', 'tv': 'TV', 
                'air_conditioning': 'AC', 'parking': 'Parking', 'pool': 'Pool',
                'washer': 'Washer', 'dryer': 'Dryer', 'dishwasher': 'Dishwasher',
                'gym': 'Gym', 'hot_tub': 'Hot Tub', 'balcony': 'Balcony', 'garden': 'Garden'
            }
            amenity_names = [amenity_labels.get(a, a.title()) for a in property_data["amenities"]]
            context_parts.append(f"Amenities: {', '.join(amenity_names)}")
        
        # Pricing
        if property_data.get("display_price"):
            context_parts.append(f"Price: ${property_data['display_price']}/night")
        
        # House rules
        rules = []
        if property_data.get("smoking_allowed") is not None:
            rules.append("Smoking allowed" if property_data["smoking_allowed"] else "No smoking")
        if property_data.get("pets_allowed") is not None:
            rules.append("Pet-friendly" if property_data["pets_allowed"] else "No pets")
        if property_data.get("events_allowed") is not None:
            rules.append("Events welcome" if property_data["events_allowed"] else "No events")
        if property_data.get("children_welcome") is not None:
            rules.append("Child-friendly" if property_data["children_welcome"] else "Adults only")
        
        if rules:
            context_parts.append(f"House Rules: {', '.join(rules)}")
        
        # Trust level discounts
        trust_discounts = []
        for i in range(1, 6):
            discount_key = f"trust_level_{i}_discount"
            if property_data.get(discount_key):
                level_names = {1: "Bronze", 2: "Silver", 3: "Gold", 4: "Platinum", 5: "Diamond"}
                trust_discounts.append(f"{level_names[i]}: {property_data[discount_key]}%")
        
        if trust_discounts:
            context_parts.append(f"Trust Level Discounts: {', '.join(trust_discounts)}")
        
        return "\n".join(context_parts) if context_parts else "Limited property information available"
    
    def _generate_fallback_descriptions(self, property_data):
        """Generate basic fallback descriptions when AI fails"""
        property_type = property_data.get("property_type", "property").title()
        city = property_data.get("city", "a great location")
        guests = property_data.get("max_guests", "guests")
        
        return [
            f"Welcome to our beautiful {property_type.lower()} in {city}! This comfortable space accommodates up to {guests} guests and offers everything you need for a perfect stay. We've thoughtfully designed the space with your comfort in mind, providing all essential amenities for a memorable experience. Come and enjoy the charm of our {property_type.lower()} - we can't wait to host you!",
            
            f"This well-appointed {property_type.lower()} in {city} features comfortable accommodations for {guests} guests. The space includes modern amenities and thoughtful touches to ensure your stay is both comfortable and convenient. Located in {city}, you'll have easy access to local attractions while enjoying a peaceful retreat. Book now for an excellent stay experience!",
            
            f"Discover the perfect getaway at our {property_type.lower()} in {city}! Designed for comfort and relaxation, this space welcomes up to {guests} guests in a warm, inviting atmosphere. Whether you're here for business or leisure, you'll find everything you need for a wonderful stay. We look forward to sharing our special place with you and helping create lasting memories!"
        ]
    
    def _validate_and_enhance_extraction(self, result):
        """Enhanced validation with better error handling"""
        if "extracted" in result:
            result["extracted"] = self._validate_extracted_fields(result["extracted"])
        
        required_keys = ["extracted", "titles", "descriptions", "confidence_score"]
        for key in required_keys:
            if key not in result:
                if key == "extracted":
                    result[key] = {}
                elif key in ["titles", "descriptions"]:
                    result[key] = []
                elif key == "confidence_score":
                    result[key] = 0.5
        
        if "insights" not in result:
            result["insights"] = {
                "hosting_style": "friendly",
                "property_vibe": "comfortable",
                "target_guests": "leisure"
            }
        
        return result
    
    def _validate_extracted_fields(self, extracted):
        """Enhanced field validation with trust level support"""
        validated = {}
        
        # Validate property type
        valid_property_types = ['apartment', 'house', 'villa', 'cabin', 'loft', 'other']
        if extracted.get('property_type') in valid_property_types:
            validated['property_type'] = extracted['property_type']
        
        # Validate place type
        valid_place_types = ['entire_place', 'private_room', 'shared_room']
        if extracted.get('place_type') in valid_place_types:
            validated['place_type'] = extracted['place_type']
        
        # Validate numeric fields
        numeric_fields = [
            'bedrooms', 'bathrooms', 'beds', 'max_guests', 'display_price', 
            'price_per_night', 'square_feet', 'minimum_stay', 'maximum_stay',
            'trust_level_1_discount', 'trust_level_2_discount', 'trust_level_3_discount',
            'trust_level_4_discount', 'trust_level_5_discount'
        ]
        
        for field in numeric_fields:
            if field in extracted:
                try:
                    value = float(extracted[field])
                    if value >= 0:
                        # Special validation for trust level discounts
                        if 'trust_level' in field and 'discount' in field:
                            validated[field] = min(50, max(0, int(value)))  # 0-50% range
                        else:
                            validated[field] = int(value) if value == int(value) else value
                except (ValueError, TypeError):
                    pass
        
        # Validate boolean fields
        boolean_fields = [
            'smoking_allowed', 'pets_allowed', 'events_allowed', 
            'children_welcome', 'instant_book_enabled'
        ]
        for field in boolean_fields:
            if field in extracted and isinstance(extracted[field], bool):
                validated[field] = extracted[field]
        
        # Validate string fields
        string_fields = [
            'city', 'country', 'address', 'neighborhood', 'title', 
            'description', 'check_in_time_start', 'check_out_time'
        ]
        for field in string_fields:
            if field in extracted and isinstance(extracted[field], str) and extracted[field].strip():
                validated[field] = extracted[field].strip()
        
        # Validate amenities
        valid_amenities = [
            'wifi', 'kitchen', 'tv', 'air_conditioning', 'parking', 'pool', 
            'washer', 'dryer', 'dishwasher', 'gym', 'hot_tub', 'balcony', 'garden'
        ]
        if 'amenities' in extracted and isinstance(extracted['amenities'], list):
            validated['amenities'] = [
                amenity for amenity in extracted['amenities'] 
                if amenity in valid_amenities
            ]
        
        return validated
    
    def _parse_ai_response(self, ai_content):
        """Enhanced AI response parsing with multiple fallback strategies"""
        try:
            return json.loads(ai_content)
        except json.JSONDecodeError:
            try:
                # Try to extract JSON from markdown code blocks
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', ai_content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                
                # Try to find any JSON object
                json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                    
            except json.JSONDecodeError:
                pass
            
            # Final fallback
            return {
                "extracted": {},
                "titles": ["Beautiful Property", "Comfortable Stay", "Perfect Location"],
                "descriptions": ["A wonderful place to stay with great amenities."],
                "confidence_score": 0.1,
                "error": "Could not parse AI response"
            }
