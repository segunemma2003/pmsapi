from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from .models import Invitation
from trust_levels.models import TrustedNetworkInvitation

@shared_task
def send_invitation_email(invitation_id, inviter_name):
    """Send invitation email"""
    try:
        invitation = Invitation.objects.select_related('invited_by').get(id=invitation_id)
        
        subject = f"🏠 You're invited to join OnlyIfYouKnow as a {invitation.invitation_type}!"
        
        # Get invitation URL
        base_url = settings.FRONTEND_URL
        invitation_url = f"{base_url}/invitation/respond?token={invitation.invitation_token}"
        
        context = {
            'invitee_name': invitation.invitee_name or 'there',
            'inviter_name': inviter_name,
            'invitation_type': invitation.invitation_type,
            'personal_message': invitation.personal_message,
            'invitation_url': invitation_url,
            'email': invitation.email
        }
        
        html_message = render_to_string('emails/invitation.html', context)
        plain_message = render_to_string('emails/invitation.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Email sent successfully'}
        
    except Invitation.DoesNotExist:
        return {'success': False, 'error': 'Invitation not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@shared_task
def send_trusted_network_invitation_email(invitation_id):
    """Send trusted network invitation email"""
    try:
        invitation = TrustedNetworkInvitation.objects.select_related('owner').get(id=invitation_id)
        
        subject = f"🏠 You're invited to {invitation.owner.full_name}'s trusted network!"
        
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
            'email': invitation.email
        }
        
        html_message = render_to_string('emails/network_invitation.html', context)
        plain_message = render_to_string('emails/network_invitation.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            html_message=html_message,
            fail_silently=False
        )
        
        return {'success': True, 'message': 'Network invitation email sent successfully'}
        
    except TrustedNetworkInvitation.DoesNotExist:
        return {'success': False, 'error': 'Network invitation not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}