from celery import shared_task
from django.utils import timezone
from .models import Booking
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

@shared_task(bind=True, max_retries=3)
def sync_booking_to_beds24(self, booking_id, action='create'):
    """Sync approved booking to Beds24"""
    try:
        booking = Booking.objects.select_related('property', 'guest').get(id=booking_id)
        
        if booking.status != 'confirmed':
            return {'success': False, 'error': 'Only confirmed bookings can be synced'}
        
        from beds24_integration.services import Beds24Service
        beds24_service = Beds24Service()
        
        # Prepare booking data for Beds24
        booking_data = {
            'property_id': booking.property.beds24_property_id,
            'guest_name': booking.guest.full_name,
            'guest_email': booking.guest.email,
            'check_in': booking.check_in_date.isoformat(),
            'check_out': booking.check_out_date.isoformat(),
            'guests': booking.guests_count,
            'total_amount': float(booking.total_amount),
            'notes': booking.special_requests,
            'booking_reference': str(booking.id)
        }
        
        if action == 'create':
            # Create booking on Beds24
            result = beds24_service.create_booking(booking_data)
            
            if result['success']:
                booking.beds24_booking_id = result.get('booking_id')
                booking.beds24_synced_at = timezone.now()
                booking.beds24_sync_status = 'synced'
                booking.beds24_sync_error = ''
                booking.save()
                
                # Trigger iCal sync to update calendars
                from properties.tasks import auto_sync_all_properties
                auto_sync_all_properties.delay()
                
                return {'success': True, 'beds24_booking_id': result.get('booking_id')}
            else:
                booking.beds24_sync_status = 'failed'
                booking.beds24_sync_error = result.get('error', 'Unknown error')
                booking.save()
                
                # Retry on failure
                if self.request.retries < self.max_retries:
                    countdown = 2 ** self.request.retries * 60
                    raise self.retry(countdown=countdown)
                
                return {'success': False, 'error': result.get('error')}
        
        elif action == 'cancel':
            # Cancel booking on Beds24
            if booking.beds24_booking_id:
                result = beds24_service.cancel_booking(booking.beds24_booking_id)
                
                if result['success']:
                    booking.beds24_sync_status = 'cancelled'
                    booking.save()
                    
                    # Trigger iCal sync
                    from properties.tasks import auto_sync_all_properties
                    auto_sync_all_properties.delay()
                    
                    return {'success': True, 'message': 'Booking cancelled on Beds24'}
        
    except Booking.DoesNotExist:
        return {'success': False, 'error': 'Booking not found'}
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}
    
    
@shared_task
def sync_pending_bookings():
    """Sync any pending confirmed bookings that failed to sync"""
    try:
        pending_sync_bookings = Booking.objects.filter(
            status='confirmed',
            beds24_booking_id__isnull=True,
            property__beds24_property_id__isnull=False
        )
        
        synced_count = 0
        for booking in pending_sync_bookings:
            result = sync_booking_to_beds24.delay(str(booking.id), action='create')
            if result:
                synced_count += 1
        
        return {'success': True, 'synced_count': synced_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@shared_task
def sync_booking_statuses_from_beds24():
    """Check for booking status updates from Beds24"""
    try:
        from beds24_integration.services import Beds24Service
        beds24_service = Beds24Service()
        
        # Get confirmed bookings with Beds24 IDs
        beds24_bookings = Booking.objects.filter(
            status='confirmed',
            beds24_booking_id__isnull=False
        )
        
        updated_count = 0
        for booking in beds24_bookings:
            try:
                result = beds24_service.get_booking_details(booking.beds24_booking_id)
                if result['success']:
                    beds24_data = result['booking']
                    
                    # Check if booking was cancelled on Beds24
                    if beds24_data.get('status') == 3:  # Cancelled
                        booking.status = 'cancelled'
                        booking.save()
                        updated_count += 1
                        
            except Exception as e:
                continue  # Skip this booking and continue with others
        
        return {'success': True, 'updated_count': updated_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}
    


@shared_task(bind=True, max_retries=3)
def send_booking_request_emails(self, booking_id):
    """Send email notifications for new booking request"""
    try:
        booking = Booking.objects.select_related('property', 'guest', 'property__owner').get(id=booking_id)
        
        # Email to property owner
        owner_context = {
            'owner_name': booking.property.owner.full_name or booking.property.owner.email,
            'guest_name': booking.guest.full_name,
            'guest_email': booking.guest.email,
            'property_title': booking.property.title,
            'check_in': booking.check_in_date,
            'check_out': booking.check_out_date,
            'nights': booking.nights,
            'guests_count': booking.guests_count,
            'total_amount': booking.total_amount,
            'discount_applied': booking.discount_applied,
            'special_requests': booking.special_requests,
            'booking_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}",
            'approve_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}/approve",
            'reject_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}/reject"
        }
        
        # Send to owner
        owner_html = render_to_string('emails/booking_request_owner.html', owner_context)
        owner_text = render_to_string('emails/booking_request_owner.txt', owner_context)
        
        send_mail(
            subject=f'📅 New Booking Request for {booking.property.title}',
            message=owner_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.property.owner.email],
            html_message=owner_html,
            fail_silently=False
        )
        
        # Email to guest (confirmation of request)
        guest_context = {
            'guest_name': booking.guest.full_name or booking.guest.email,
            'property_title': booking.property.title,
            'owner_name': booking.property.owner.full_name,
            'check_in': booking.check_in_date,
            'check_out': booking.check_out_date,
            'nights': booking.nights,
            'guests_count': booking.guests_count,
            'total_amount': booking.total_amount,
            'original_price': booking.original_price,
            'discount_applied': booking.discount_applied,
            'special_requests': booking.special_requests,
            'booking_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}"
        }
        
        guest_html = render_to_string('emails/booking_request_guest.html', guest_context)
        guest_text = render_to_string('emails/booking_request_guest.txt', guest_context)
        
        send_mail(
            subject=f'📋 Booking Request Submitted - {booking.property.title}',
            message=guest_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=guest_html,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Booking request emails sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def send_booking_approval_emails(self, booking_id):
    """Send email notifications for booking approval"""
    try:
        booking = Booking.objects.select_related('property', 'guest', 'property__owner').get(id=booking_id)
        
        # Email to guest (approval notification)
        guest_context = {
            'guest_name': booking.guest.full_name or booking.guest.email,
            'property_title': booking.property.title,
            'owner_name': booking.property.owner.full_name,
            'owner_email': booking.property.owner.email,
            'property_address': booking.property.address,
            'check_in': booking.check_in_date,
            'check_out': booking.check_out_date,
            'nights': booking.nights,
            'guests_count': booking.guests_count,
            'total_amount': booking.total_amount,
            'booking_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}",
            'property_url': f"{settings.FRONTEND_URL}/properties/{booking.property.id}"
        }
        
        guest_html = render_to_string('emails/booking_approved.html', guest_context)
        guest_text = render_to_string('emails/booking_approved.txt', guest_context)
        
        send_mail(
            subject=f'🎉 Booking Approved - {booking.property.title}',
            message=guest_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=guest_html,
            fail_silently=False
        )
        
        # Email to owner (confirmation of approval)
        owner_context = {
            'owner_name': booking.property.owner.full_name or booking.property.owner.email,
            'guest_name': booking.guest.full_name,
            'guest_email': booking.guest.email,
            'property_title': booking.property.title,
            'check_in': booking.check_in_date,
            'check_out': booking.check_out_date,
            'nights': booking.nights,
            'guests_count': booking.guests_count,
            'total_amount': booking.total_amount,
            'booking_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}"
        }
        
        owner_html = render_to_string('emails/booking_approved_owner.html', owner_context)
        owner_text = render_to_string('emails/booking_approved_owner.txt', owner_context)
        
        send_mail(
            subject=f'✅ Booking Approved - {booking.property.title}',
            message=owner_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.property.owner.email],
            html_message=owner_html,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Booking approval emails sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def send_booking_rejection_emails(self, booking_id, rejection_reason=''):
    """Send email notifications for booking rejection"""
    try:
        booking = Booking.objects.select_related('property', 'guest', 'property__owner').get(id=booking_id)
        
        # Email to guest (rejection notification)
        guest_context = {
            'guest_name': booking.guest.full_name or booking.guest.email,
            'property_title': booking.property.title,
            'owner_name': booking.property.owner.full_name,
            'check_in': booking.check_in_date,
            'check_out': booking.check_out_date,
            'rejection_reason': rejection_reason,
            'property_url': f"{settings.FRONTEND_URL}/properties/{booking.property.id}",
            'search_url': f"{settings.FRONTEND_URL}/properties"
        }
        
        guest_html = render_to_string('emails/booking_rejected.html', guest_context)
        guest_text = render_to_string('emails/booking_rejected.txt', guest_context)
        
        send_mail(
            subject=f'❌ Booking Request Update - {booking.property.title}',
            message=guest_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=guest_html,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Booking rejection emails sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def send_booking_cancellation_notifications(self, booking_id, cancelled_by='user', reason=''):
    """Send email notifications for booking cancellation"""
    try:
        booking = Booking.objects.select_related('property', 'guest', 'property__owner').get(id=booking_id)
        
        # Email to guest
        guest_context = {
            'guest_name': booking.guest.full_name or booking.guest.email,
            'property_title': booking.property.title,
            'owner_name': booking.property.owner.full_name,
            'owner_email': booking.property.owner.email,
            'check_in': booking.check_in_date,
            'check_out': booking.check_out_date,
            'cancelled_by': cancelled_by,
            'cancellation_reason': reason,
            'was_cancelled_by_owner': cancelled_by == 'owner'
        }
        
        guest_html = render_to_string('emails/booking_cancelled_guest.html', guest_context)
        guest_text = render_to_string('emails/booking_cancelled_guest.txt', guest_context)
        
        send_mail(
            subject=f'🚫 Booking Cancelled - {booking.property.title}',
            message=guest_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=guest_html,
            fail_silently=False
        )
        
        # Email to owner (if cancelled by guest)
        if cancelled_by != 'owner':
            owner_context = {
                'owner_name': booking.property.owner.full_name or booking.property.owner.email,
                'guest_name': booking.guest.full_name,
                'guest_email': booking.guest.email,
                'property_title': booking.property.title,
                'check_in': booking.check_in_date,
                'check_out': booking.check_out_date,
                'cancellation_reason': reason,
                'cancelled_by': cancelled_by
            }
            
            owner_html = render_to_string('emails/booking_cancelled_owner.html', owner_context)
            owner_text = render_to_string('emails/booking_cancelled_owner.txt', owner_context)
            
            send_mail(
                subject=f'🚫 Booking Cancelled by Guest - {booking.property.title}',
                message=owner_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[booking.property.owner.email],
                html_message=owner_html,
                fail_silently=False
            )
        
        return {'success': True, 'message': 'Booking cancellation emails sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def send_booking_completion_notifications(self, booking_id):
    """Send email notifications for booking completion"""
    try:
        booking = Booking.objects.select_related('property', 'guest', 'property__owner').get(id=booking_id)
        
        # Email to guest (thank you + review request)
        guest_context = {
            'guest_name': booking.guest.full_name or booking.guest.email,
            'property_title': booking.property.title,
            'owner_name': booking.property.owner.full_name,
            'check_in': booking.check_in_date,
            'check_out': booking.check_out_date,
            'nights': booking.nights,
            'review_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}/review"
        }
        
        guest_html = render_to_string('emails/booking_completed_guest.html', guest_context)
        guest_text = render_to_string('emails/booking_completed_guest.txt', guest_context)
        
        send_mail(
            subject=f'✨ Thank you for your stay at {booking.property.title}',
            message=guest_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=guest_html,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Booking completion emails sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}
    

@shared_task(bind=True, max_retries=3)
def send_checkin_reminder_email(self, booking_id):
    """Send check-in reminder email (24 hours before check-in)"""
    try:
        booking = Booking.objects.select_related('property', 'guest', 'property__owner').get(id=booking_id)
        
        # Only send for confirmed bookings
        if booking.status != 'confirmed':
            return {'success': False, 'error': 'Booking is not confirmed'}
        
        # Email to guest
        context = {
            'guest_name': booking.guest.full_name or booking.guest.email,
            'property_title': booking.property.title,
            'property_address': booking.property.address,
            'owner_name': booking.property.owner.full_name,
            'owner_email': booking.property.owner.email,
            'check_in': booking.check_in_date,
            'booking_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}"
        }
        
        html_message = render_to_string('emails/booking_reminder_checkin.html', context)
        plain_message = render_to_string('emails/booking_reminder_checkin.txt', context)
        
        send_mail(
            subject=f'📅 Check-in Reminder - {booking.property.title}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Check-in reminder sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def send_checkout_reminder_email(self, booking_id):
    """Send check-out reminder email (24 hours before check-out)"""
    try:
        booking = Booking.objects.select_related('property', 'guest', 'property__owner').get(id=booking_id)
        
        # Only send for confirmed bookings
        if booking.status != 'confirmed':
            return {'success': False, 'error': 'Booking is not confirmed'}
        
        # Email to guest
        context = {
            'guest_name': booking.guest.full_name or booking.guest.email,
            'property_title': booking.property.title,
            'owner_name': booking.property.owner.full_name,
            'owner_email': booking.property.owner.email,
            'check_out': booking.check_out_date,
            'booking_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}",
            'review_url': f"{settings.FRONTEND_URL}/bookings/{booking.id}/review"
        }
        
        html_message = render_to_string('emails/booking_reminder_checkout.html', context)
        plain_message = render_to_string('emails/booking_reminder_checkout.txt', context)
        
        send_mail(
            subject=f'📅 Check-out Reminder - {booking.property.title}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Check-out reminder sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

@shared_task
def send_daily_booking_reminders():
    """Daily task to send check-in and check-out reminders"""
    from datetime import date, timedelta
    
    tomorrow = date.today() + timedelta(days=1)
    
    try:
        # Get bookings with check-in tomorrow
        checkin_bookings = Booking.objects.filter(
            status='confirmed',
            check_in_date=tomorrow
        )
        
        checkin_sent = 0
        for booking in checkin_bookings:
            send_checkin_reminder_email.delay(str(booking.id))
            checkin_sent += 1
        
        # Get bookings with check-out tomorrow
        checkout_bookings = Booking.objects.filter(
            status='confirmed',
            check_out_date=tomorrow
        )
        
        checkout_sent = 0
        for booking in checkout_bookings:
            send_checkout_reminder_email.delay(str(booking.id))
            checkout_sent += 1
        
        return {
            'success': True,
            'checkin_reminders_sent': checkin_sent,
            'checkout_reminders_sent': checkout_sent
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}