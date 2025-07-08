import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')
django.setup()

from django.conf import settings
from django.template.loader import get_template
from django.template import TemplateDoesNotExist
import os

print("=== Django Configuration Debug ===")
print(f"BASE_DIR: {settings.BASE_DIR}")
print(f"DEBUG: {settings.DEBUG}")

print("\n=== Template Settings ===")
for i, template_config in enumerate(settings.TEMPLATES):
    print(f"Template Engine {i}:")
    print(f"  Backend: {template_config['BACKEND']}")
    print(f"  DIRS: {template_config['DIRS']}")
    print(f"  APP_DIRS: {template_config['APP_DIRS']}")

print("\n=== File System Check ===")
# Check if templates directory exists
templates_dir = os.path.join(settings.BASE_DIR, 'templates')
print(f"Templates directory: {templates_dir}")
print(f"Templates dir exists: {os.path.exists(templates_dir)}")

emails_dir = os.path.join(templates_dir, 'emails')
print(f"Emails directory: {emails_dir}")
print(f"Emails dir exists: {os.path.exists(emails_dir)}")

# List files in emails directory
if os.path.exists(emails_dir):
    files = os.listdir(emails_dir)
    print(f"Files in emails dir: {files}")
    
    # Check specific file
    target_file = os.path.join(emails_dir, 'invitation_new_user.html')
    print(f"Target file: {target_file}")
    print(f"Target file exists: {os.path.exists(target_file)}")
    
    if os.path.exists(target_file):
        print(f"File size: {os.path.getsize(target_file)} bytes")
        # Read first few lines
        with open(target_file, 'r') as f:
            content = f.read(200)
            print(f"File content preview: {content}")

print("\n=== Template Loading Test ===")
# Test different ways of loading the template
template_paths = [
    'emails/invitation_new_user.html',
    'invitation_new_user.html',
    './emails/invitation_new_user.html',
]

for path in template_paths:
    try:
        template = get_template(path)
        print(f"✅ Found template: {path}")
        print(f"   Template name: {template.template.name}")
        break
    except TemplateDoesNotExist as e:
        print(f"❌ Template not found: {path}")
        print(f"   Error: {e}")
        print(f"   Tried: {e.tried}")

print("\n=== Template Render Test ===")
try:
    from django.template.loader import render_to_string
    from django.utils import timezone
    
    context = {
        'invitee_name': 'Test User',
        'inviter_name': 'Test Inviter', 
        'invitation_type': 'user',
        'personal_message': 'Test message',
        'invitation_url': 'http://test.com',
        'expires_at': timezone.now(),
    }
    
    content = render_to_string('emails/invitation_new_user.html', context)
    print("✅ Template rendered successfully!")
    print(f"Rendered length: {len(content)} characters")
    
except Exception as e:
    print(f"❌ Template rendering failed: {e}")
    import traceback
    traceback.print_exc()