import requests
import json
from django.conf import settings
from django.core.cache import cache
from datetime import datetime, timedelta
from icalendar import Calendar, Event
from django.utils import timezone
import uuid

class Beds24Service:
    def __init__(self):
        self.base_url = settings.BEDS24_API_URL
        self.refresh_token = settings.BEDS24_REFRESH_TOKEN
        self.access_token = None
        self.token_expiry = None
    
    def get_access_token(self):
        """Get access token using refresh token"""
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token
        
        # Check cache first
        cached_token = cache.get('beds24_access_token')
        if cached_token:
            self.access_token = cached_token['token']
            self.token_expiry = cached_token['expiry']
            return self.access_token
        
        if not self.refresh_token:
            raise Exception('No Beds24 refresh token available')
        
        try:
            response = requests.get(
                f"{self.base_url}/authentication/token",
                headers={
                    'accept': 'application/json',
                    'refreshToken': self.refresh_token
                },
                timeout=30
            )
            response.raise_for_status()
            
            auth_data = response.json()
            self.access_token = auth_data['token']
            self.token_expiry = datetime.now() + timedelta(seconds=auth_data['expiresIn'] - 60)
            
            # Cache the token
            cache.set('beds24_access_token', {
                'token': self.access_token,
                'expiry': self.token_expiry
            }, timeout=auth_data['expiresIn'] - 120)
            
            return self.access_token
            
        except requests.RequestException as e:
            raise Exception(f"Failed to authenticate with Beds24: {str(e)}")
    
    # ===== iCal INTEGRATION METHODS =====
    
    def get_property_ical_urls(self, beds24_property_id):
        """Get iCal URLs for a Beds24 property"""
        token = self.get_access_token()
        
        try:
            response = requests.get(
                f"{self.base_url}/properties/{beds24_property_id}/ical",
                headers={
                    'accept': 'application/json',
                    'token': token
                },
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                'success': True,
                'ical_urls': {
                    'import_url': result.get('importUrl'),  # URL to import bookings TO Beds24
                    'export_url': result.get('exportUrl'),  # URL to export bookings FROM Beds24
                    'sync_url': result.get('syncUrl')       # Bidirectional sync URL
                },
                'data': result
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to get iCal URLs: {str(e)}"
            }
    
    def update_property_ical_settings(self, beds24_property_id, ical_settings):
        """Update iCal sync settings for a property"""
        token = self.get_access_token()
        
        # Default iCal settings
        default_settings = {
            'icalImport': True,          # Allow importing from external calendars
            'icalExport': True,          # Allow exporting to external calendars
            'icalAutoBlock': True,       # Auto-block dates from imported bookings
            'icalSyncPeriod': 24,        # Sync every 24 hours
            'icalPastDays': 30,          # Include past 30 days
            'icalFutureDays': 365,       # Include next 365 days
            'icalTimeZone': 'UTC'        # Time zone for iCal events
        }
        
        # Merge with provided settings
        settings_data = {**default_settings, **ical_settings}
        
        try:
            response = requests.put(
                f"{self.base_url}/properties/{beds24_property_id}/ical",
                headers={
                    'Content-Type': 'application/json',
                    'accept': 'application/json',
                    'token': token
                },
                json=settings_data,
                timeout=30
            )
            response.raise_for_status()
            
            return {
                'success': True,
                'message': 'iCal settings updated successfully'
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to update iCal settings: {str(e)}"
            }
    
    def import_external_ical(self, beds24_property_id, ical_url, calendar_name="External Calendar"):
        """Import external iCal feed into Beds24 property"""
        token = self.get_access_token()
        
        import_data = {
            'icalUrl': ical_url,
            'calendarName': calendar_name,
            'autoSync': True,
            'blockDates': True,  # Block dates from external calendar
            'syncInterval': 3600  # Sync every hour
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/properties/{beds24_property_id}/ical/import",
                headers={
                    'Content-Type': 'application/json',
                    'accept': 'application/json',
                    'token': token
                },
                json=import_data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                'success': True,
                'import_id': result.get('importId'),
                'message': 'External iCal imported successfully'
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to import external iCal: {str(e)}"
            }
    
    def get_property_availability(self, beds24_property_id, start_date, end_date):
        """Get property availability as iCal format"""
        token = self.get_access_token()
        
        params = {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d'),
            'format': 'ical'
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/properties/{beds24_property_id}/availability",
                headers={
                    'accept': 'text/calendar',
                    'token': token
                },
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            return {
                'success': True,
                'ical_data': response.text,
                'content_type': response.headers.get('content-type')
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to get availability iCal: {str(e)}"
            }
    
    def sync_bookings_via_ical(self, beds24_property_id):
        """Trigger manual iCal sync for a property"""
        token = self.get_access_token()
        
        try:
            response = requests.post(
                f"{self.base_url}/properties/{beds24_property_id}/ical/sync",
                headers={
                    'accept': 'application/json',
                    'token': token
                },
                timeout=60  # Longer timeout for sync operations
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                'success': True,
                'sync_status': result.get('status'),
                'bookings_imported': result.get('bookingsImported', 0),
                'bookings_exported': result.get('bookingsExported', 0),
                'last_sync': result.get('lastSync')
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to sync iCal: {str(e)}"
            }