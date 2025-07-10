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
from django.utils import timezone
import uuid
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Optimized queryset with proper access control based on effective role"""
        user = self.request.user
        effective_role = user.get_effective_role()
        
        # Base queryset with optimizations
        base_queryset = Property.objects.select_related('owner').annotate(
            booking_count=Count('bookings')
        ).prefetch_related('images_set')
        
        if user.user_type == 'admin':
            # Admins see all properties
            return base_queryset.all()
        elif effective_role == 'owner':
            # When acting as owner, see only their own properties
            return base_queryset.filter(owner=user)
        else:
            # When acting as user, see only properties from owners in their trust network
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
    
    @action(detail=True, methods=['post'])
    def share_calendar(self, request, pk=None):
        """Share property availability calendar via email"""
        property_obj = self.get_object()
        
        # Only property owner can share calendar when acting as owner
        if property_obj.owner != request.user or request.user.get_effective_role() != 'owner':
            return Response(
                {'error': 'Only property owner can share calendar when acting as owner'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get request data
        recipient_emails = request.data.get('emails', [])
        message = request.data.get('message', '')
        include_pricing = request.data.get('include_pricing', False)
        date_range_days = request.data.get('date_range_days', 365)  # Default 1 year
        
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
        
        html_content = render_to_string('emails/share_calendar.html', context)
        text_content = render_to_string('emails/share_calendar.txt', context)
        
        sent_count = 0
        failed_emails = []
        
        for email in recipient_emails:
            try:
                send_mail(
                    subject=f"📅 {request.user.full_name} shared {property_obj.title}'s availability with you",
                    message=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    html_message=html_content,
                    fail_silently=False
                )
                sent_count += 1
            except Exception as e:
                failed_emails.append(email)
        
        # Log activity
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
        
        # Get bookings
        from bookings.models import Booking
        bookings = Booking.objects.filter(
            property=property_obj,
            status__in=['confirmed', 'pending'],
            check_out_date__gte=start_date,
            check_in_date__lte=end_date
        ).values('check_in_date', 'check_out_date', 'status')
        
        # Format availability data
        blocked_dates = []
        for booking in bookings:
            blocked_dates.append({
                'start': booking['check_in_date'].isoformat(),
                'end': booking['check_out_date'].isoformat(),
                'status': booking['status']
            })
        
        response_data = {
            'property': {
                'title': property_obj.title,
                'address': property_obj.address,
                'city': property_obj.city,
                'max_guests': property_obj.max_guests,
                'bedrooms': property_obj.bedrooms,
                'bathrooms': property_obj.bathrooms
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
        
        # Check for conflicting bookings (including ongoing bookings)
        from bookings.models import Booking
        today = timezone.now().date()
        
        conflicting_bookings = Booking.objects.filter(
            property=property_obj,
            check_in_date__lt=check_out,
            check_out_date__gt=check_in
        ).filter(
            Q(status='confirmed') |
            Q(status='confirmed', check_in_date__lte=today, check_out_date__gt=today)
        )
        
        if conflicting_bookings.exists():
            return Response({
                'available': False,
                'reason': 'Property is not available for selected dates',
                'conflicting_dates': list(conflicting_bookings.values(
                    'check_in_date', 'check_out_date'
                ))
            })
        
        # Check external calendars if configured
        if property_obj.ical_external_calendars:
            for calendar in property_obj.ical_external_calendars:
                if calendar.get('active', True):
                    try:
                        result = ICalService.check_availability_from_url(
                            calendar['url'],
                            check_in,
                            check_out
                        )
                        if not result['available']:
                            return Response({
                                'available': False,
                                'reason': f"Conflict with {calendar.get('name', 'external calendar')}"
                            })
                    except:
                        # If external check fails, continue
                        pass
        
        # Calculate pricing
        nights = (check_out - check_in).days
        base_price = property_obj.price_per_night * nights
        discounted_price = property_obj.get_display_price(request.user) * nights
        
        return Response({
            'available': True,
            'nights': nights,
            'base_price': float(base_price),
            'discounted_price': float(discounted_price),
            'savings': float(base_price - discounted_price),
            'price_per_night': float(property_obj.get_display_price(request.user))
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