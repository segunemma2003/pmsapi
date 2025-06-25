from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Property, PropertyICalSync
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
    
    
@shared_task
def sync_property_ical(property_id):
    """Sync property iCal with Beds24"""
    try:
        property_obj = Property.objects.get(id=property_id)
        
        if not property_obj.beds24_property_id:
            return {'success': False, 'error': 'Property not synced with Beds24'}
        
        # Create sync record
        sync_record = PropertyICalSync.objects.create(
            property=property_obj,
            sync_type='bidirectional',
            sync_status='running'
        )
        
        from beds24_integration.services import Beds24Service
        beds24_service = Beds24Service()
        
        # Trigger sync
        result = beds24_service.sync_bookings_via_ical(property_obj.beds24_property_id)
        
        if result['success']:
            sync_record.sync_status = 'completed'
            sync_record.bookings_imported = result.get('bookings_imported', 0)
            sync_record.bookings_exported = result.get('bookings_exported', 0)
            sync_record.completed_at = timezone.now()
            
            # Update property sync status
            property_obj.ical_last_sync = timezone.now()
            property_obj.ical_sync_status = 'success'
            property_obj.save()
            
        else:
            sync_record.sync_status = 'failed'
            sync_record.error_message = result.get('error', 'Unknown error')
            sync_record.completed_at = timezone.now()
            
            property_obj.ical_sync_status = 'error'
            property_obj.save()
        
        sync_record.save()
        
        return {
            'success': result['success'],
            'sync_id': str(sync_record.id),
            'bookings_imported': result.get('bookings_imported', 0),
            'bookings_exported': result.get('bookings_exported', 0)
        }
        
    except Property.DoesNotExist:
        return {'success': False, 'error': 'Property not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@shared_task
def import_external_ical(property_id, ical_url, calendar_name):
    """Import external iCal calendar"""
    try:
        property_obj = Property.objects.get(id=property_id)
        
        # Fetch iCal data
        import requests
        response = requests.get(ical_url, timeout=30)
        response.raise_for_status()
        
        # Parse iCal data
        from beds24_integration.ical_service import ICalService
        result = ICalService.parse_external_calendar(response.text)
        
        if result['success']:
            # Process bookings and create blocked dates
            # This would depend on your business logic
            
            return {
                'success': True,
                'bookings_processed': result['count'],
                'calendar_name': calendar_name
            }
        else:
            return {
                'success': False,
                'error': result['error']
            }
            
    except Property.DoesNotExist:
        return {'success': False, 'error': 'Property not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@shared_task
def auto_sync_all_properties():
    """Auto-sync all properties with iCal enabled"""
    properties = Property.objects.filter(
        ical_sync_enabled=True,
        beds24_property_id__isnull=False
    )
    
    results = []
    for property_obj in properties:
        # Check if enough time has passed since last sync
        if property_obj.ical_last_sync:
            time_since_sync = timezone.now() - property_obj.ical_last_sync
            if time_since_sync.total_seconds() < property_obj.ical_sync_interval:
                continue
        
        # Trigger sync
        result = sync_property_ical.delay(str(property_obj.id))
        results.append({
            'property_id': str(property_obj.id),
            'task_id': result.id
        })
    
    return {
        'properties_synced': len(results),
        'results': results
    }