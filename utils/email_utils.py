from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from celery import shared_task
import logging

logger = logging.getLogger('oifyk.email')

class EmailService:
    """Centralized email service with templates and error handling"""
    
    @staticmethod
    def send_templated_email(template_name, context, recipient_list, subject=None, 
                           from_email=None, fail_silently=False):
        """Send email using templates with both HTML and text versions"""
        try:
            # Load templates
            html_template = f'emails/{template_name}.html'
            text_template = f'emails/{template_name}.txt'
            
            html_content = render_to_string(html_template, context)
            text_content = render_to_string(text_template, context)
            
            # Use subject from context or parameter
            email_subject = subject or context.get('subject', 'OnlyIfYouKnow Notification')
            email_from = from_email or settings.DEFAULT_FROM_EMAIL
            
            # Create email
            email = EmailMultiAlternatives(
                subject=email_subject,
                body=text_content,
                from_email=email_from,
                to=recipient_list
            )
            email.attach_alternative(html_content, "text/html")
            
            # Send email
            return email.send(fail_silently=fail_silently)
            
        except Exception as e:
            logger.error(f"Failed to send email {template_name}: {str(e)}")
            if not fail_silently:
                raise
            return False

@shared_task(bind=True, max_retries=3)
def send_email_async(self, template_name, context, recipient_list, subject=None):
    """Async email sending with retry logic"""
    try:
        return EmailService.send_templated_email(
            template_name, context, recipient_list, subject
        )
    except Exception as e:
        if self.request.retries < self.max_retries:
            # Exponential backoff: 1min, 2min, 4min
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(countdown=countdown, exc=e)
        logger.error(f"Failed to send email after {self.max_retries} retries: {str(e)}")
        return False

