from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Property
from beds24_integration.services import Beds24Service

User = get_user_model()

@shared_task
def submit_property_for_approval(property_id, submitter_id):
    """Submit property for approval"""
    try:
        property_obj = Property.objects.get(id=property_id)
        property_obj.status = 'pending_approval'
        property_obj.submitted_for_approval_at = timezone.now()
        property_obj.save()
        
        # Log activity
        from analytics.models import ActivityLog
        ActivityLog.objects.create(
            action='property_submitted_for_approval',
            user_id=submitter_id,
            resource_type='property',
            resource_id=property_id,
            details={'property_title': property_obj.title}
        )
        
        return {'success': True, 'message': 'Property submitted for approval'}
    except Property.DoesNotExist:
        return {'success': False, 'error': 'Property not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@shared_task
def enlist_to_beds24(property_id, admin_id):
    """Enlist property to Beds24"""
    try:
        property_obj = Property.objects.select_related('owner').get(id=property_id)
        beds24_service = Beds24Service()
        
        # Create property on Beds24
        result = beds24_service.create_property(property_obj)
        
        if result['success']:
            property_obj.beds24_property_id = result['property_id']
            property_obj.status = 'active'
            property_obj.beds24_sync_status = 'synced'
            property_obj.beds24_synced_at = timezone.now()
            property_obj.beds24_sync_data = result['data']
            property_obj.save()
            
            # Log activity
            from analytics.models import ActivityLog
            ActivityLog.objects.create(
                action='property_enlisted_beds24',
                user_id=admin_id,
                resource_type='property',
                resource_id=property_id,
                details={
                    'beds24_property_id': result['property_id'],
                    'property_title': property_obj.title
                }
            )
            
            return {'success': True, 'beds24_property_id': result['property_id']}
        else:
            property_obj.beds24_sync_status = 'error'
            property_obj.beds24_error_message = result.get('error', 'Unknown error')
            property_obj.save()
            
            return {'success': False, 'error': result.get('error')}
            
    except Property.DoesNotExist:
        return {'success': False, 'error': 'Property not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}