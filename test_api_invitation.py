import os
import django
import requests
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

def get_jwt_token():
    """Get JWT token for API testing"""
    # Get or create a test user
    user, created = User.objects.get_or_create(
        email='api_test_user@example.com',
        defaults={
            'username': 'api_test_user@example.com',
            'full_name': 'API Test User',
            'user_type': 'admin'
        }
    )
    
    if created:
        user.set_password('testpassword123')
        user.save()
    
    # Generate JWT token
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)

def test_invitation_api():
    """Test invitation creation via API"""
    print("=== Testing Invitation API ===")
    
    try:
        # Get JWT token
        token = get_jwt_token()
        print(f"✅ Got JWT token")
        
        # API endpoint
        url = 'http://localhost:8000/api/invitations/'
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'email': 'segunemma2003@gmail.com',
            'invitee_name': 'API Test Recipient',
            'invitation_type': 'owner',
            # 'personal_message': 'This is a test invitation from API'
        }
        
        print(f"📤 Sending API request to {url}")
        print(f"📤 Data: {json.dumps(data, indent=2)}")
        
        # Make API call
        response = requests.post(url, headers=headers, json=data)
        
        print(f"📥 Response status: {response.status_code}")
        print(f"📥 Response data: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 201:
            print("✅ API call successful")
            response_data = response.json()
            if 'task_id' in response_data:
                print(f"✅ Task ID returned: {response_data['task_id']}")
            else:
                print("⚠️ No task ID in response")
        else:
            print(f"❌ API call failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_invitation_api()