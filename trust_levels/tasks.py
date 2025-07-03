from django.conf import settings
from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import send_mail

@shared_task(bind=True, max_retries=3)
def send_trusted_network_invitation_email(self, invitation_id, user_exists=False):
    """Send trusted network invitation email"""
    try:
        from trust_levels.models import TrustedNetworkInvitation
        invitation = TrustedNetworkInvitation.objects.select_related('owner').get(id=invitation_id)
        
        subject = f"🏠 You're invited to {invitation.owner.full_name}'s trusted network!"
        
        # Different template for existing vs new users
        if user_exists:
            template_prefix = 'network_invitation_existing_user'
        else:
            template_prefix = 'network_invitation_new_user'
        
        # Get invitation URL
        base_url = settings.FRONTEND_URL
        invitation_url = f"{base_url}/network-invitation/respond?token={invitation.invitation_token}"
        
        context = {
            'invitee_name': invitation.invitee_name or 'there',
            'owner_name': invitation.owner.full_name,
            'trust_level': invitation.trust_level,
            'discount_percentage': invitation.discount_percentage,
            'personal_message': invitation.personal_message,
            'invitation_url': invitation_url,
            'email': invitation.email,
            'user_exists': user_exists
        }
        
        html_message = render_to_string(f'emails/{template_prefix}.html', context)
        plain_message = render_to_string(f'emails/{template_prefix}.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Network invitation email sent successfully'}
        
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}