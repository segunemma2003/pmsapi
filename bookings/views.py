from bookings.tasks import send_booking_approval_emails, send_booking_rejection_emails, send_booking_request_emails
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta, date
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer

class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        effective_role = user.get_effective_role()
        
        if user.user_type == 'admin':
            return Booking.objects.select_related(
                'property', 'guest'
            ).prefetch_related('property__owner').all().order_by('-requested_at')
        elif effective_role == 'owner':
            # When acting as owner, see booking requests for their properties
            return Booking.objects.select_related(
                'property', 'guest'
            ).filter(property__owner=user).order_by('-requested_at')
        else:
            # When acting as user, see their own booking requests
            return Booking.objects.select_related(
                'property'
            ).filter(guest=user).order_by('-requested_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer
    
    def create(self, request, *args, **kwargs):
        """Create booking request (always starts as pending)"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Additional validation for availability
        property_obj = serializer.validated_data['property']
        check_in = serializer.validated_data['check_in_date']
        check_out = serializer.validated_data['check_out_date']
        
        
        if property_obj.owner == request.user:
            return Response({
                'error': 'You cannot book your own property'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if request.user.get_effective_role() == 'user':
            from trust_levels.models import OwnerTrustedNetwork
            has_access = OwnerTrustedNetwork.objects.filter(
                owner=property_obj.owner,
                trusted_user=request.user,
                status='active'
            ).exists()
            
            if not has_access:
                return Response({
                    'error': 'You do not have access to book this property'
                }, status=status.HTTP_403_FORBIDDEN)
                
        # Check for availability conflicts (only confirmed bookings block dates)
        today = timezone.now().date()
        conflicting_bookings = Booking.objects.filter(
            property=property_obj,
            check_in_date__lt=check_out,
            check_out_date__gt=check_in
        ).filter(
            Q(status='confirmed') |  # Confirmed bookings
            Q(status='confirmed', check_in_date__lte=today, check_out_date__gt=today)  # Ongoing bookings
        )
        
        
        if conflicting_bookings.exists():
            return Response({
                'error': 'Property is not available for selected dates',
                'conflicting_bookings': conflicting_bookings.count()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        
        if property_obj.ical_external_calendars:
            availability_result = self._check_ical_availability(
                property_obj, check_in, check_out
            )
            if not availability_result['available']:
                return Response({
                    'error': 'Property is not available on external calendar',
                    'details': availability_result.get('reason', 'External calendar conflict')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        # Check beds24 availability if property is synced
        if property_obj.beds24_property_id:
            availability_result = self._check_beds24_availability(
                property_obj, check_in, check_out
            )
            if not availability_result['available']:
                return Response({
                    'error': 'Property is not available on external calendar',
                    'details': availability_result.get('reason', '')
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create booking request (status = pending)
        booking = serializer.save(status='pending')
        
        # Notify property owner
        self._notify_owner_new_request(booking)
        send_booking_request_emails.delay(str(booking.id))
        
        # Log activity
        from analytics.models import ActivityLog
        ActivityLog.objects.create(
            action='booking_request_created',
            user=request.user,
            resource_type='booking',
            resource_id=str(booking.id),
            details={
                'property_id': str(property_obj.id),
                'property_title': property_obj.title,
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'guests': booking.guests_count,
                'total_amount': str(booking.total_amount)
            }
        )
        
        return Response({
            'message': 'Booking request submitted successfully',
            'booking': BookingSerializer(booking, context={'request': request}).data,
            'status': 'pending_approval'
        }, status=status.HTTP_201_CREATED)
        
        
    def _check_ical_availability(self, property_obj, check_in, check_out):
        """Check availability against external iCal calendars"""
        try:
            from beds24_integration.ical_service import ICalService
            
            # Check each external calendar
            for calendar in property_obj.ical_external_calendars:
                if calendar.get('active', True):
                    try:
                        result = ICalService.check_availability_from_url(
                            calendar['url'],
                            check_in,
                            check_out
                        )
                        if not result['available']:
                            return {
                                'available': False,
                                'reason': f"Conflict with {calendar.get('name', 'external calendar')}"
                            }
                    except Exception as e:
                        # If iCal check fails, return empty/allow booking
                        print(f"iCal availability check failed: {str(e)}")
                        continue
            
            return {'available': True}
            
        except Exception as e:
            # On any error, return empty/allow booking as requested
            print(f"iCal availability check error: {str(e)}")
            return {'available': True}
    
    @action(detail=True, methods=['post'])
    def approve_booking(self, request, pk=None):
        """Owner approves booking request"""
        booking = self.get_object()
        
        # Security check - only property owner can approve
        if booking.property.owner != request.user or request.user.get_effective_role() != 'owner':
            return Response(
                {'error': 'Only property owner can approve bookings'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not booking.can_be_approved():
            return Response(
                {'error': f'Booking cannot be approved. Current status: {booking.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Final availability check before approval
        today = timezone.now().date()
        conflicting_bookings = Booking.objects.filter(
            property=booking.property,
            check_in_date__lt=booking.check_out_date,
            check_out_date__gt=booking.check_in_date
        ).filter(
            Q(status='confirmed') |
            Q(status='confirmed', check_in_date__lte=today, check_out_date__gt=today)
        ).exclude(id=booking.id)
        
        if conflicting_bookings.exists():
            return Response({
                'error': 'Cannot approve - conflicting confirmed booking exists',
                'conflict_count': conflicting_bookings.count()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Approve booking
        booking.status = 'confirmed'
        booking.approved_at = timezone.now()
        booking.save()
        
        # Sync with Beds24 in background
        if booking.property.beds24_property_id:
            from .tasks import sync_booking_to_beds24
            sync_booking_to_beds24.delay(str(booking.id), action='create')
        
        # Notify guest of approval
        self._notify_guest_booking_approved(booking)
        send_booking_approval_emails.delay(str(booking.id))
        
        # Log activity
        from analytics.models import ActivityLog
        ActivityLog.objects.create(
            action='booking_approved',
            user=request.user,
            resource_type='booking',
            resource_id=str(booking.id),
            details={
                'booking_id': str(booking.id),
                'guest_name': booking.guest.full_name,
                'property_title': booking.property.title
            }
        )
        
        return Response({
            'message': 'Booking approved successfully',
            'booking': BookingSerializer(booking, context={'request': request}).data,
            'beds24_sync': 'queued' if booking.property.beds24_property_id else 'not_applicable'
        })
    
    @action(detail=True, methods=['post'])
    def reject_booking(self, request, pk=None):
        """Owner rejects booking request"""
        booking = self.get_object()
        
        # Security check
        if booking.property.owner != request.user or request.user.get_effective_role() != 'owner':
            return Response(
                {'error': 'Only property owner can reject bookings'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not booking.can_be_rejected():
            return Response(
                {'error': f'Booking cannot be rejected. Current status: {booking.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        rejection_reason = request.data.get('reason', '')
        
        # Reject booking
        booking.status = 'rejected'
        booking.rejected_at = timezone.now()
        booking.rejection_reason = rejection_reason
        booking.save()
        
        # Notify guest of rejection
        self._notify_guest_booking_rejected(booking, rejection_reason)
        send_booking_rejection_emails.delay(str(booking.id), rejection_reason)
        
        # Log activity
        from analytics.models import ActivityLog
        ActivityLog.objects.create(
            action='booking_rejected',
            user=request.user,
            resource_type='booking',
            resource_id=str(booking.id),
            details={
                'booking_id': str(booking.id),
                'guest_name': booking.guest.full_name,
                'property_title': booking.property.title,
                'reason': rejection_reason
            }
        )
        
        return Response({
            'message': 'Booking rejected',
            'booking': BookingSerializer(booking, context={'request': request}).data
        })
    
    @action(detail=False, methods=['get'])
    def pending_requests(self, request):
        """Get pending booking requests for owner"""
        if request.user.get_effective_role() != 'owner':
            return Response(
                {'error': 'Only owners can view pending requests'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        pending_bookings = Booking.objects.select_related(
            'property', 'guest'
        ).filter(
            property__owner=request.user,
            status='pending'
        ).order_by('-requested_at')
        
        serializer = BookingSerializer(pending_bookings, many=True, context={'request': request})
        
        return Response({
            'count': pending_bookings.count(),
            'results': serializer.data
        })
    
    
    def schedule_booking_reminders(self, booking):
        """Schedule reminder emails for confirmed booking"""
        from datetime import timedelta
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        import json
        
        if booking.status == 'confirmed':
            # Schedule check-in reminder (24 hours before)
            checkin_reminder_time = booking.check_in_date - timedelta(days=1)
            
            # Schedule check-out reminder (24 hours before)
            checkout_reminder_time = booking.check_out_date - timedelta(days=1)
            
            # You can implement this with django-celery-beat or simpler daily task
            # For now, the daily task will handle all reminders
            
    def _check_beds24_availability(self, property_obj, check_in, check_out):
        """Check availability on Beds24/external calendars"""
        try:
            from beds24_integration.services import Beds24Service
            beds24_service = Beds24Service()
            
            result = beds24_service.get_property_availability(
                property_obj.beds24_property_id,
                check_in,
                check_out
            )
            
            if result['success']:
                # Parse availability data
                availability = result['availability']
                # Implementation depends on Beds24 API response format
                # For now, assume it returns available: true/false
                return {'available': availability.get('available', True)}
            else:
                # If check fails, allow booking but log error
                return {'available': True, 'reason': 'Could not verify external availability'}
                
        except Exception as e:
            # Don't block booking if availability check fails
            return {'available': True, 'reason': f'Availability check error: {str(e)}'}
    
    def _notify_owner_new_request(self, booking):
        """Send notification to owner about new booking request"""
        from notifications.services import NotificationService
        
        NotificationService.create_notification(
            user=booking.property.owner,
            title="New Booking Request",
            message=f"You have a new booking request for {booking.property.title} from {booking.guest.full_name}",
            notification_type='booking_request',
            data={
                'booking_id': str(booking.id),
                'property_id': str(booking.property.id),
                'guest_name': booking.guest.full_name,
                'check_in': booking.check_in_date.isoformat(),
                'check_out': booking.check_out_date.isoformat(),
                'guests': booking.guests_count,
                'total_amount': str(booking.total_amount)
            }
        )
    
    def _notify_guest_booking_approved(self, booking):
        """Notify guest that booking was approved"""
        from notifications.services import NotificationService
        
        NotificationService.create_notification(
            user=booking.guest,
            title="Booking Approved! 🎉",
            message=f"Your booking for {booking.property.title} has been approved by the owner",
            notification_type='booking_confirmed',
            data={
                'booking_id': str(booking.id),
                'property_id': str(booking.property.id),
                'property_title': booking.property.title,
                'check_in': booking.check_in_date.isoformat(),
                'check_out': booking.check_out_date.isoformat()
            }
        )
    
    def _notify_guest_booking_rejected(self, booking, reason):
        """Notify guest that booking was rejected"""
        from notifications.services import NotificationService
        
        message = f"Your booking request for {booking.property.title} was not approved"
        if reason:
            message += f". Reason: {reason}"
        
        NotificationService.create_notification(
            user=booking.guest,
            title="Booking Request Update",
            message=message,
            notification_type='booking_cancelled',
            data={
                'booking_id': str(booking.id),
                'property_id': str(booking.property.id),
                'property_title': booking.property.title,
                'reason': reason
            }
        )
        
    @action(detail=False, methods=['get'])
    def owner_dashboard_stats(self, request):
        """Get booking statistics for property owner"""
        if request.user.user_type != 'owner':
            return Response(
                {'error': 'Only owners can view dashboard stats'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from django.db.models import Sum, Count, Avg
        from datetime import datetime, timedelta
        
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        
        # Get owner's bookings
        owner_bookings = Booking.objects.filter(property__owner=request.user)
        
        stats = {
            'pending_requests': owner_bookings.filter(status='pending').count(),
            'confirmed_bookings': owner_bookings.filter(status='confirmed').count(),
            'total_bookings_30_days': owner_bookings.filter(
                requested_at__gte=last_30_days
            ).count(),
            'total_revenue_confirmed': owner_bookings.filter(
                status__in=['confirmed', 'completed']
            ).aggregate(total=Sum('total_amount'))['total'] or 0,
            'average_booking_value': owner_bookings.filter(
                status__in=['confirmed', 'completed']
            ).aggregate(avg=Avg('total_amount'))['avg'] or 0,
            'approval_rate': 0,
            'upcoming_checkins': owner_bookings.filter(
                status='confirmed',
                check_in_date__gte=now.date(),
                check_in_date__lte=(now + timedelta(days=7)).date()
            ).count(),
            'current_guests': owner_bookings.filter(
                status='confirmed',
                check_in_date__lte=now.date(),
                check_out_date__gt=now.date()
            ).count()
        }
        
        # Calculate approval rate
        total_requests = owner_bookings.exclude(status='pending').count()
        if total_requests > 0:
            approved = owner_bookings.filter(status__in=['confirmed', 'completed']).count()
            stats['approval_rate'] = (approved / total_requests) * 100
        
        return Response(stats)
    
    @action(detail=True, methods=['post'])
    def complete_booking(self, request, pk=None):
        """Mark booking as completed (owner only, after guest checkout)"""
        booking = self.get_object()
        
        # Only property owner can mark as completed
        if booking.property.owner != request.user:
            return Response(
                {'error': 'Only property owner can mark booking as completed'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if booking can be completed
        if booking.status != 'confirmed':
            return Response(
                {'error': 'Only confirmed bookings can be marked as completed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if check-out date has passed
        if booking.check_out_date > timezone.now().date():
            return Response(
                {'error': 'Cannot complete booking before check-out date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Complete the booking
        booking.status = 'completed'
        booking.save()
        
        # Send completion notifications
        from .tasks import send_booking_completion_notifications
        send_booking_completion_notifications.delay(str(booking.id))
        
        # Log activity
        from analytics.models import ActivityLog
        ActivityLog.objects.create(
            action='booking_completed',
            user=request.user,
            resource_type='booking',
            resource_id=str(booking.id),
            details={
                'booking_id': str(booking.id),
                'guest_name': booking.guest.full_name,
                'property_title': booking.property.title
            }
        )
        
        return Response({
            'message': 'Booking marked as completed',
            'booking': BookingSerializer(booking, context={'request': request}).data
        })

    @action(detail=True, methods=['post'])
    def cancel_booking(self, request, pk=None):
        """Cancel a confirmed booking (guest or owner)"""
        booking = self.get_object()
        
        # Check permissions (guest or owner can cancel)
        can_cancel = (
            booking.guest == request.user or 
            booking.property.owner == request.user or 
            request.user.user_type == 'admin'
        )
        
        if not can_cancel:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if booking can be cancelled
        if booking.status not in ['pending', 'confirmed']:
            return Response(
                {'error': f'Cannot cancel booking with status: {booking.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get cancellation reason
        cancellation_reason = request.data.get('reason', '')
        cancellation_policy = request.data.get('policy_applied', False)  # For future use
        
        # Cancel the booking
        original_status = booking.status
        booking.status = 'cancelled'
        booking.booking_metadata.update({
            'cancelled_by': request.user.user_type,
            'cancelled_at': timezone.now().isoformat(),
            'cancellation_reason': cancellation_reason,
            'original_status': original_status
        })
        booking.save()
        
        # Cancel on Beds24 if it was synced
        if booking.beds24_booking_id:
            from .tasks import sync_booking_to_beds24
            sync_booking_to_beds24.delay(str(booking.id), action='cancel')
        
        # Send cancellation notifications
        from .tasks import send_booking_cancellation_notifications
        send_booking_cancellation_notifications.delay(
            str(booking.id), 
            cancelled_by=request.user.user_type,
            reason=cancellation_reason
        )
        
        # Log activity
        from analytics.models import ActivityLog
        ActivityLog.objects.create(
            action='booking_cancelled',
            user=request.user,
            resource_type='booking',
            resource_id=str(booking.id),
            details={
                'booking_id': str(booking.id),
                'cancelled_by': request.user.user_type,
                'reason': cancellation_reason,
                'original_status': original_status
            }
        )
        
        return Response({
            'message': 'Booking cancelled successfully',
            'booking': BookingSerializer(booking, context={'request': request}).data,
            'beds24_sync': 'queued' if booking.beds24_booking_id else 'not_applicable'
        })

    @action(detail=False, methods=['get'])
    def upcoming_checkins(self, request):
        """Get upcoming check-ins for owner (next 7 days)"""
        if request.user.user_type != 'owner':
            return Response(
                {'error': 'Only owners can view upcoming check-ins'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from datetime import date, timedelta
        
        today = date.today()
        next_week = today + timedelta(days=7)
        
        upcoming_bookings = Booking.objects.select_related(
            'property', 'guest'
        ).filter(
            property__owner=request.user,
            status='confirmed',
            check_in_date__gte=today,
            check_in_date__lte=next_week
        ).order_by('check_in_date')
        
        serializer = BookingSerializer(upcoming_bookings, many=True, context={'request': request})
        
        return Response({
            'count': upcoming_bookings.count(),
            'date_range': {
                'start': today.isoformat(),
                'end': next_week.isoformat()
            },
            'results': serializer.data
        })

    @action(detail=False, methods=['get'])
    def current_guests(self, request):
        """Get current guests (checked in, not yet checked out)"""
        if request.user.user_type != 'owner':
            return Response(
                {'error': 'Only owners can view current guests'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from datetime import date
        
        today = date.today()
        
        current_bookings = Booking.objects.select_related(
            'property', 'guest'
        ).filter(
            property__owner=request.user,
            status='confirmed',
            check_in_date__lte=today,
            check_out_date__gt=today
        ).order_by('check_out_date')
        
        serializer = BookingSerializer(current_bookings, many=True, context={'request': request})
        
        return Response({
            'count': current_bookings.count(),
            'results': serializer.data
        })
