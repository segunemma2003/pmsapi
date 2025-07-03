from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from .models import Invitation

User = get_user_model()

@shared_task(bind=True, max_retries=3)
def send_invitation_email(self, invitation_id, inviter_name, is_existing_user=False):
    """Send invitation email with SendGrid"""
    try:
        invitation = Invitation.objects.select_related('invited_by').get(id=invitation_id)
        
        if invitation.status != 'pending':
            return {'success': False, 'error': 'Invitation is not pending'}
        
        # Different subject and content for existing vs new users
        if is_existing_user:
            subject = f"🏠 You're invited to become a {invitation.invitation_type.title()} on OnlyIfYouKnow!"
            template_prefix = 'invitation_existing_user'
        else:
            subject = f"🏠 You're invited to join OnlyIfYouKnow as a {invitation.invitation_type.title()}!"
            template_prefix = 'invitation_new_user'
        
        # Get invitation URL
        base_url = settings.FRONTEND_URL
        invitation_url = f"{base_url}/invitation/accept?token={invitation.invitation_token}"
        
        context = {
            'invitee_name': invitation.invitee_name or 'there',
            'inviter_name': inviter_name,
            'invitation_type': invitation.invitation_type,
            'personal_message': invitation.personal_message,
            'invitation_url': invitation_url,
            'email': invitation.email,
            'expires_at': invitation.expires_at,
            'is_existing_user': is_existing_user
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
        
        return {'success': True, 'message': 'Invitation email sent successfully'}
        
    except Invitation.DoesNotExist:
        return {'success': False, 'error': 'Invitation not found'}
    except Exception as e:
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

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

@shared_task(bind=True, max_retries=3)
def process_invitation_acceptance(self, invitation_token, user_id):
    """Process invitation acceptance and create onboarding token"""
    try:
        from .models import OnboardingToken
        
        # Get the invitation
        invitation = Invitation.objects.get(invitation_token=invitation_token)
        
        if invitation.status != 'pending':
            return {'success': False, 'error': 'Invitation is not pending'}
        
        # Create onboarding token
        onboarding_token = OnboardingToken.objects.create(
            invitation=invitation,
            email=invitation.email,
            user_type=invitation.invitation_type,
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        # Mark invitation as accepted
        invitation.status = 'accepted'
        invitation.accepted_by_id = user_id
        invitation.accepted_at = timezone.now()
        invitation.save()
        
        return {
            'success': True,
            'onboarding_token': str(onboarding_token.token),
            'user_type': invitation.invitation_type
        }
        
    except Invitation.DoesNotExist:
        return {'success': False, 'error': 'Invitation not found'}
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}