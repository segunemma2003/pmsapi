from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .models import Property
from beds24_integration.services import Beds24Service
import logging

logger = logging.getLogger(__name__)

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
    

@shared_task(bind=True, max_retries=2)
def auto_sync_all_properties(self):
    """Auto sync all properties with Beds24"""
    try:
        from .models import Property
        
        properties = Property.objects.filter(
            beds24_property_id__isnull=False,
            ical_sync_enabled=True,
            status='active'
        )
        
        synced_count = 0
        for property_obj in properties:
            try:
                # Trigger iCal sync
                beds24_service = Beds24Service()
                result = beds24_service.sync_bookings_via_ical(property_obj.beds24_property_id)
                
                if result['success']:
                    synced_count += 1
                    property_obj.ical_last_sync = timezone.now()
                    property_obj.ical_sync_status = 'completed'
                    property_obj.save()
                    
            except Exception as e:
                property_obj.ical_sync_status = 'failed'
                property_obj.beds24_error_message = str(e)
                property_obj.save()
        
        return {'success': True, 'synced_count': synced_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@shared_task(bind=True, max_retries=2)
def sync_booking_status_from_beds24(self):
    """Sync booking statuses from Beds24"""
    try:
        from bookings.models import Booking
        
        # Get bookings that might need status updates
        bookings = Booking.objects.filter(
            status__in=['pending', 'confirmed'],
            property__beds24_property_id__isnull=False
        )
        
        updated_count = 0
        beds24_service = Beds24Service()
        
        for booking in bookings:
            try:
                # Check booking status on Beds24
                result = beds24_service.get_booking_status(booking.id)
                if result['success'] and result['status'] != booking.status:
                    booking.status = result['status']
                    booking.save()
                    updated_count += 1
            except (ConnectionError, TimeoutError) as e:
                # Log network-related errors but continue with other bookings
                logger.warning(f"Network error syncing booking {booking.id}: {str(e)}")
                continue
            except Exception as e:
                # Log unexpected errors but continue processing
                logger.error(f"Unexpected error syncing booking {booking.id}: {str(e)}")
                continue
        
        return {'success': True, 'updated_count': updated_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@shared_task
def cleanup_availability_cache():
    """Clean up expired availability cache entries"""
    try:
        from django.core.cache import cache
        from django_redis import get_redis_connection
        
        redis_conn = get_redis_connection("default")
        
        # Find and delete expired availability cache keys
        pattern = "property_availability_*"
        keys = redis_conn.keys(pattern)
        
        deleted_count = 0
        for key in keys:
            # Check if key is expired or older than 1 day
            ttl = redis_conn.ttl(key)
            if ttl <= 0 or ttl > 86400:  # 24 hours
                redis_conn.delete(key)
                deleted_count += 1
        
        return {'success': True, 'deleted_count': deleted_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}