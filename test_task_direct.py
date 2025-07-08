import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')
django.setup()

from invitations.models import Invitation
from invitations.tasks import send_invitation_email

print("=== Testing Task Function Directly (No Celery) ===")
try:
    # Get the invitation
    invitation = Invitation.objects.filter(email='segunemma2003@gmail.com').first()
    if not invitation:
        print("No invitation found")
        exit()
    
    print(f"Found invitation: {invitation.id}")
    
    # Call the function directly (not via Celery)
    # Remove the @shared_task decorator temporarily or call the underlying function
    result = send_invitation_email(
        str(invitation.id),
        invitation.invited_by.full_name or invitation.invited_by.email,
        False
    )
    
    print(f"Direct function result: {result}")
    
except Exception as e:
    print(f"Direct function error: {e}")
    import traceback
    traceback.print_exc()