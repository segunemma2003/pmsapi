from .models import Notification

class NotificationService:
    """Service for creating notifications"""
    
    @staticmethod
    def create_notification(user, title, message, notification_type, data=None):
        """Create a new notification"""
        return Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            data=data or {}
        )
    
    @staticmethod
    def notify_booking_request(booking):
        """Notify property owner of new booking request"""
        return NotificationService.create_notification(
            user=booking.property.owner,
            title="New Booking Request",
            message=f"You have a new booking request for {booking.property.title}",
            notification_type='booking_request',
            data={
                'booking_id': str(booking.id),
                'property_id': str(booking.property.id),
                'guest_name': booking.guest.full_name,
                'check_in': booking.check_in_date.isoformat(),
                'check_out': booking.check_out_date.isoformat()
            }
        )
    
    @staticmethod
    def notify_booking_confirmed(booking):
        """Notify guest that booking is confirmed"""
        return NotificationService.create_notification(
            user=booking.guest,
            title="Booking Confirmed",
            message=f"Your booking for {booking.property.title} has been confirmed!",
            notification_type='booking_confirmed',
            data={
                'booking_id': str(booking.id),
                'property_id': str(booking.property.id),
                'property_title': booking.property.title,
                'check_in': booking.check_in_date.isoformat(),
                'check_out': booking.check_out_date.isoformat()
            }
        )
    
    @staticmethod
    def notify_trust_invitation(invitation):
        """Notify user of trust network invitation"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(email=invitation.email)
            return NotificationService.create_notification(
                user=user,
                title="Trust Network Invitation",
                message=f"{invitation.owner.full_name} invited you to their trusted network",
                notification_type='trust_invitation',
                data={
                    'invitation_id': str(invitation.id),
                    'owner_name': invitation.owner.full_name,
                    'trust_level': invitation.trust_level,
                    'discount_percentage': float(invitation.discount_percentage)
                }
            )
        except User.DoesNotExist:
            # User doesn't exist yet, skip notification
            pass