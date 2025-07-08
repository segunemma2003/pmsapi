import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')
django.setup()

from celery import shared_task
from django.conf import settings
from django.template.loader import get_template
from django.template.exceptions import TemplateDoesNotExist

@shared_task
def test_celery_environment():
    """Test Celery worker environment"""
    try:
        result = {
            'base_dir': str(settings.BASE_DIR),
            'template_dirs': [str(d) for d in settings.TEMPLATES[0]['DIRS']],
            'debug': settings.DEBUG,
            'app_dirs': settings.TEMPLATES[0]['APP_DIRS'],
        }
        
        # Test template loading
        try:
            template = get_template('emails/invitation_new_user.html')
            result['template_found'] = True
            result['template_name'] = template.template.name
        except TemplateDoesNotExist as e:
            result['template_found'] = False
            result['template_error'] = str(e)
            result['tried_locations'] = getattr(e, 'tried', [])
        
        # Check if template files exist on filesystem
        import os
        template_path = os.path.join(settings.BASE_DIR, 'templates', 'emails', 'invitation_new_user.html')
        result['template_file_exists'] = os.path.exists(template_path)
        result['template_path'] = template_path
        
        if os.path.exists(template_path):
            result['template_file_size'] = os.path.getsize(template_path)
        
        return {'success': True, 'data': result}
        
    except Exception as e:
        import traceback
        return {
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }

if __name__ == '__main__':
    print("=== Testing Celery Worker Environment ===")
    result = test_celery_environment.delay()
    try:
        result_value = result.get(timeout=10)
        print(f"Celery environment test result:")
        
        if result_value['success']:
            data = result_value['data']
            print(f"  BASE_DIR: {data['base_dir']}")
            print(f"  Template dirs: {data['template_dirs']}")
            print(f"  DEBUG: {data['debug']}")
            print(f"  Template file exists: {data['template_file_exists']}")
            print(f"  Template path: {data['template_path']}")
            print(f"  Template found by Django: {data['template_found']}")
            
            if data['template_file_exists'] and data.get('template_file_size'):
                print(f"  Template file size: {data['template_file_size']} bytes")
            
            if not data['template_found']:
                print(f"  Template error: {data.get('template_error')}")
                print(f"  Tried locations: {data.get('tried_locations')}")
        else:
            print(f"  Error: {result_value['error']}")
            
    except Exception as e:
        print(f"Celery environment test failed: {e}")