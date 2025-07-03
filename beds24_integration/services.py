import requests
import json
from django.conf import settings
from django.core.cache import cache
from datetime import datetime, timedelta
import uuid

class Beds24Service:
    def __init__(self):
        self.base_url = settings.BEDS24_API_URL
        self.refresh_token = settings.BEDS24_REFRESH_TOKEN
        self.access_token = None
        self.token_expiry = None
    
    def get_access_token(self):
        """Get access token using refresh token with caching"""
        cache_key = 'beds24_access_token'
        cached_token = cache.get(cache_key)
        
        if cached_token:
            self.access_token = cached_token['token']
            self.token_expiry = cached_token['expiry']
            return self.access_token
        
        if not self.refresh_token:
            raise Exception('No Beds24 refresh token available')
        
        try:
            response = requests.post(
                f"{self.base_url}/auth/token",
                headers={
                    'accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                json={
                    'refreshToken': self.refresh_token,
                    'grantType': 'refresh_token'
                },
                timeout=30
            )
            response.raise_for_status()
            
            auth_data = response.json()
            self.access_token = auth_data['accessToken']
            expires_in = auth_data.get('expiresIn', 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)
            
            # Cache the token
            cache.set(cache_key, {
                'token': self.access_token,
                'expiry': self.token_expiry
            }, timeout=expires_in - 120)  # Cache for slightly less than expiry
            
            return self.access_token
            
        except requests.RequestException as e:
            raise Exception(f"Failed to authenticate with Beds24: {str(e)}")
    
    def create_subaccount(self, user):
        """Create Beds24 subaccount for property owner"""
        token = self.get_access_token()
        
        subaccount_data = {
            'name': user.full_name or user.email.split('@')[0],
            'email': user.email,
            'phone': user.phone or '',
            'address': '',
            'city': '',
            'country': '',
            'currency': 'USD',
            'timezone': 'UTC',
            'language': 'en'
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/subaccounts",
                headers={
                    'accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                json=subaccount_data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                'success': True,
                'ical_urls': {
                    'import_url': result.get('importUrl'),
                    'export_url': result.get('exportUrl'),
                    'sync_url': result.get('syncUrl')
                },
                'data': result
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to get iCal URLs: {str(e)}"
            }
    
    def sync_bookings_via_ical(self, beds24_property_id):
        """Trigger manual iCal sync for a property"""
        token = self.get_access_token()
        
        try:
            response = requests.post(
                f"{self.base_url}/properties/{beds24_property_id}/ical/sync",
                headers={
                    'accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                timeout=60
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
    
    def add_external_calendar(self, beds24_property_id, calendar_url, calendar_name):
        """Add external iCal calendar to property"""
        token = self.get_access_token()
        
        calendar_data = {
            'url': calendar_url,
            'name': calendar_name,
            'autoSync': True,
            'blockDates': True,
            'syncInterval': 3600  # 1 hour
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/properties/{beds24_property_id}/ical/external",
                headers={
                    'Content-Type': 'application/json',
                    'accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                json=calendar_data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                'success': True,
                'calendar_id': result.get('id'),
                'message': 'External calendar added successfully'
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to add external calendar: {str(e)}"
            }
    
    def get_property_availability(self, beds24_property_id, start_date, end_date):
        """Get property availability"""
        token = self.get_access_token()
        
        params = {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d'),
            'format': 'json'
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/properties/{beds24_property_id}/availability",
                headers={
                    'accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            return {
                'success': True,
                'availability': response.json()
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to get availability: {str(e)}"
            }
    
    def test_connection(self):
        """Test Beds24 API connection"""
        try:
            token = self.get_access_token()
            response = requests.get(
                f"{self.base_url}/user/profile",
                headers={
                    'accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                timeout=10
            )
            return response.status_code == 200
        except:
            return False


    def get_booking_status(self, booking_id):
        """Get booking status from Beds24"""
        token = self.get_access_token()
        
        try:
            response = requests.get(
                f"{self.base_url}/bookings/{booking_id}",
                headers={
                    'accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                'success': True,
                'status': result.get('status', 'unknown')
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to get booking status: {str(e)}"
            }