from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
import logging
import traceback

@shared_task(bind=True, max_retries=3)
def send_trusted_network_invitation_email(self, invitation_id, user_exists=False):
    """Send trusted network invitation email with enhanced debugging"""
    try:
        print(f"=== TRUST NETWORK EMAIL TASK START === ID: {invitation_id}")
        
        # Step 1: Get invitation
        from trust_levels.models import TrustedNetworkInvitation
        invitation = TrustedNetworkInvitation.objects.select_related('owner').get(id=invitation_id)
        print(f"✅ Found invitation for {invitation.email}")
        
        if invitation.status != 'pending':
            return {'success': False, 'error': 'Invitation is not pending'}
        
        # Step 2: Prepare email content
        subject = f"🏠 You're invited to {invitation.owner.full_name}'s trusted network!"
        
        # Step 3: Build context
        base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        invitation_url = f"{base_url}/network-invitation/respond/token={invitation.invitation_token}"
        
        # Get trust level name
        trust_level_name = f"Level {invitation.trust_level}"
        try:
            from trust_levels.models import TrustLevelDefinition
            trust_level_def = TrustLevelDefinition.objects.get(
                owner=invitation.owner, 
                level=invitation.trust_level
            )
            trust_level_name = trust_level_def.name
        except TrustLevelDefinition.DoesNotExist:
            pass
        
        context = {
            'invitee_name': invitation.invitee_name or 'there',
            'owner_name': invitation.owner.full_name,
            'trust_level': invitation.trust_level,
            'trust_level_name': trust_level_name,
            'discount_percentage': invitation.discount_percentage,
            'personal_message': invitation.personal_message,
            'invitation_url': invitation_url,
            'email': invitation.email,
            'expires_at': invitation.expires_at,
            'user_exists': user_exists
        }
        
        print(f"✅ Context prepared: {list(context.keys())}")
        
        # Step 4: Use the existing network invitation templates
        html_template_name = 'emails/network_invitation.html'
        txt_template_name = 'emails/network_invitation.txt'
        
        # Check if templates exist and render them
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
            # Create a simple text template if it doesn't exist
            try:
                plain_message = render_to_string(txt_template_name, context)
                print(f"✅ Text template rendered, length: {len(plain_message)}")
            except:
                # Fallback to simple text message
                plain_message = f"""
🏠 TRUSTED NETWORK INVITATION - OnlyIfYouKnow

Hi {context['invitee_name']},

{context['owner_name']} has invited you to join their trusted network on OnlyIfYouKnow.

Trust Level: {context['trust_level_name']} ({context['discount_percentage']}% discount)

{context['personal_message'] if context['personal_message'] else ''}

Accept your invitation: {context['invitation_url']}

This invitation expires on {context['expires_at'].strftime('%B %d, %Y')}.

Best regards,
The OnlyIfYouKnow Team
"""
                print(f"✅ Fallback text template created, length: {len(plain_message)}")
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
            return {'success': True, 'message': 'Network invitation email sent successfully'}
            
        except Exception as email_error:
            print(f"❌ Email sending failed: {email_error}")
            print(f"❌ Email traceback: {traceback.format_exc()}")
            return {
                'success': False, 
                'error': f'Email sending failed: {str(email_error)}',
                'traceback': traceback.format_exc()
            }
        
    except TrustedNetworkInvitation.DoesNotExist:
        print(f"❌ Invitation {invitation_id} not found")
        return {'success': False, 'error': 'Invitation not found'}
    except Exception as e:
        print(f"❌ Unexpected error in trust network email task: {e}")
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