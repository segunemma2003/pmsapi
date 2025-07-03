from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .models import Property
from beds24_integration.services import Beds24Service

User = get_user_model()

@shared_task(bind=True, max_retries=3)
def enlist_to_beds24(self, property_id):
    """Automatically enlist property to Beds24 (no admin approval needed)"""
    try:
        property_obj = Property.objects.select_related('owner').get(id=property_id)
        beds24_service = Beds24Service()
        
        # Prepare property data for Beds24
        property_data = {
            'name': property_obj.title,
            'description': property_obj.description,
            'address': property_obj.address,
            'city': property_obj.city,
            'country': property_obj.country,
            'postal_code': property_obj.postal_code,
            'bedrooms': property_obj.bedrooms,
            'bathrooms': property_obj.bathrooms,
            'maxGuests': property_obj.max_guests,
            'basePrice': float(property_obj.price_per_night),
            'amenities': property_obj.amenities,
        }
        
        # Create property on Beds24
        result = beds24_service.create_property(property_data)
        
        if result['success']:
            property_obj.beds24_property_id = result['property_id']
            property_obj.beds24_sync_status = 'synced'
            property_obj.beds24_synced_at = timezone.now()
            property_obj.beds24_sync_data = result.get('data', {})
            property_obj.beds24_error_message = ''
            
            # Setup iCal integration
            ical_urls = beds24_service.get_property_ical_urls(result['property_id'])
            if ical_urls['success']:
                property_obj.ical_import_url = ical_urls['ical_urls']['import_url']
                property_obj.ical_export_url = ical_urls['ical_urls']['export_url']
            
            property_obj.save()
            
            # Clear caches
            cache.delete(f'property_detail_{property_id}')
            
            # Log activity
            from analytics.models import ActivityLog
            ActivityLog.objects.create(
                action='property_auto_enlisted_beds24',
                user=property_obj.owner,
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
            
            # Retry on failure
            if self.request.retries < self.max_retries:
                countdown = 2 ** self.request.retries * 60  # Exponential backoff
                raise self.retry(countdown=countdown)
            
            return {'success': False, 'error': result.get('error')}
            
    except Property.DoesNotExist:
        return {'success': False, 'error': 'Property not found'}
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}

@shared_task(bind=True, max_retries=2)
def update_beds24_visibility(self, property_id, is_visible):
    """Update property visibility on Beds24"""
    try:
        property_obj = Property.objects.get(id=property_id)
        
        if not property_obj.beds24_property_id:
            return {'success': False, 'error': 'Property not synced with Beds24'}
        
        beds24_service = Beds24Service()
        result = beds24_service.update_property_visibility(
            property_obj.beds24_property_id, 
            is_visible
        )
        
        if result['success']:
            return {'success': True, 'message': f'Beds24 visibility updated to {is_visible}'}
        else:
            if self.request.retries < self.max_retries:
                countdown = 2 ** self.request.retries * 60
                raise self.retry(countdown=countdown)
            return {'success': False, 'error': result['error']}
            
    except Property.DoesNotExist:
        return {'success': False, 'error': 'Property not found'}
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}