import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')
django.setup()

from invitations.models import Invitation
from invitations.tasks import send_invitation_email
from django.contrib.auth import get_user_model
from celery import current_app

User = get_user_model()

print("=== Celery Configuration ===")
print(f"Broker: {current_app.conf.broker_url}")
print(f"Task routes: {current_app.conf.task_routes}")

print("\n=== Creating Test Invitation ===")
try:
    # Get or create a test user (the inviter)
    user, created = User.objects.get_or_create(
        email='test_inviter@example.com',
        defaults={
            'username': 'test_inviter@example.com',
            'full_name': 'Test Inviter',
            'user_type': 'admin'
        }
    )
    print(f"Test user (inviter): {user.email} ({'created' if created else 'existing'})")
    
    # Create a test invitation
    invitation, created = Invitation.objects.get_or_create(
        email='segunemma2003@gmail.com',
        invited_by=user,
        defaults={
            'invitee_name': 'Segun Emma',
            'invitation_type': 'user',
            'personal_message': 'This is a test invitation'
        }
    )
    print(f"Test invitation: {invitation.id} ({'created' if created else 'existing'})")
    print(f"Invitation email: {invitation.email}")
    print(f"Invitation status: {invitation.status}")
    
    print("\n=== Testing Email Task ===")
    # Test with real UUID
    result = send_invitation_email.delay(
        str(invitation.id),
        user.full_name or user.email,
        False
    )
    print(f"Task ID: {result.id}")
    print(f"Task state: {result.state}")
    
    # Wait for result
    try:
        result_value = result.get(timeout=30)
        print(f"Task result: {result_value}")
    except Exception as e:
        print(f"Task failed: {e}")
        import traceback
        traceback.print_exc()
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()