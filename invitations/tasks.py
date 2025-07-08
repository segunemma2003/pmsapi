from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from .models import Invitation
import logging
import traceback

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def send_invitation_email(self, invitation_id, inviter_name, is_existing_user=False):
    """Send invitation email with SendGrid - Enhanced Debugging"""
    try:
        print(f"=== EMAIL TASK START === ID: {invitation_id}")
        
        # Step 1: Get invitation
        invitation = Invitation.objects.select_related('invited_by').get(id=invitation_id)
        print(f"✅ Found invitation for {invitation.email}")
        
        if invitation.status != 'pending':
            return {'success': False, 'error': 'Invitation is not pending'}
        
        # Step 2: Prepare email content
        if is_existing_user:
            subject = f"🏠 You're invited to become a {invitation.invitation_type.title()} on OnlyIfYouKnow!"
            template_prefix = 'invitation_existing_user'
        else:
            subject = f"🏠 You're invited to join OnlyIfYouKnow as a {invitation.invitation_type.title()}!"
            template_prefix = 'invitation_new_user'
        
        print(f"✅ Using template prefix: {template_prefix}")
        
        # Step 3: Build context
        base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        invitation_url = f"{base_url}/invitation/respond?token={invitation.invitation_token}"
        
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
        
        print(f"✅ Context prepared: {list(context.keys())}")
        
        # Step 4: Render templates with specific error handling
        html_template_name = f'emails/{template_prefix}.html'
        txt_template_name = f'emails/{template_prefix}.txt'
        
        print(f"Rendering HTML template: {html_template_name}")
        try:
            html_message = render_to_string(html_template_name, context)
            print(f"✅ HTML template rendered, length: {len(html_message)}")
        except Exception as html_error:
            print(f"❌ HTML template failed: {html_error}")
            print(f"❌ HTML template traceback: {traceback.format_exc()}")
            return {
                'success': False, 
                'error': f'HTML template failed: {str(html_error)}',
                'template': html_template_name,
                'traceback': traceback.format_exc()
            }
        
        print(f"Rendering text template: {txt_template_name}")
        try:
            plain_message = render_to_string(txt_template_name, context)
            print(f"✅ Text template rendered, length: {len(plain_message)}")
        except Exception as txt_error:
            print(f"❌ Text template failed: {txt_error}")
            print(f"❌ Text template traceback: {traceback.format_exc()}")
            return {
                'success': False, 
                'error': f'Text template failed: {str(txt_error)}',
                'template': txt_template_name,
                'traceback': traceback.format_exc()
            }
        
        # Step 5: Send email
        print(f"Sending email from {settings.DEFAULT_FROM_EMAIL} to {invitation.email}")
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[invitation.email],
                html_message=html_message,
                fail_silently=False
            )
            
            print("✅ Email sent successfully!")
            return {'success': True, 'message': 'Invitation email sent successfully'}
            
        except Exception as email_error:
            print(f"❌ Email sending failed: {email_error}")
            print(f"❌ Email traceback: {traceback.format_exc()}")
            return {
                'success': False, 
                'error': f'Email sending failed: {str(email_error)}',
                'traceback': traceback.format_exc()
            }
        
    except Invitation.DoesNotExist:
        print(f"❌ Invitation {invitation_id} not found")
        return {'success': False, 'error': 'Invitation not found'}
    except Exception as e:
        print(f"❌ Unexpected error in email task: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries
            print(f"Retrying in {countdown} seconds...")
            raise self.retry(countdown=countdown, exc=e)
        
        return {
            'success': False, 
            'error': f'Task failed after retries: {str(e)}',
            'traceback': traceback.format_exc()
        }

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