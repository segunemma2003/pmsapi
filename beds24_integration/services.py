import requests
import json
from django.conf import settings
from django.core.cache import cache
from datetime import datetime, timedelta

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
            }, timeout=auth_data['expiresIn'] - 120)  # Cache for 2 minutes less than expiry
            
            return self.access_token
            
        except requests.RequestException as e:
            raise Exception(f"Failed to authenticate with Beds24: {str(e)}")
    
    def create_subaccount(self, user):
        """Create Beds24 subaccount for owner"""
        token = self.get_access_token()
        
        subaccount_data = {
            'name': user.full_name or user.email,
            'email': user.email,
            'currency': 'USD',
            'language': 'en',
            'timezone': 'UTC'
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/subaccounts",
                headers={
                    'Content-Type': 'application/json',
                    'accept': 'application/json',
                    'token': token
                },
                json=subaccount_data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                'success': True,
                'subaccount_id': str(result['id']),
                'data': result
            }
            
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to create Beds24 subaccount: {str(e)}"
            }
    
    def create_property(self, property_obj):
        """Create property on Beds24"""
        token = self.get_access_token()
        
        property_data = {
            'name': property_obj.title,
            'propertyType': self._map_property_type('house'),
            'currency': 'USD',
            'country': property_obj.country or 'USA',
            'state': property_obj.state,
            'city': property_obj.city,
            'address': property_obj.address,
            'postalCode': property_obj.postal_code,
            'latitude': float(property_obj.latitude) if property_obj.latitude else None,
            'longitude': float(property_obj.longitude) if property_obj.longitude else None,
            'description': property_obj.description,
            'maxOccupancy': property_obj.max_guests,
            'roomTypes': [{
                'name': f"{property_obj.title} - Main Unit",
                'qty': 1,
                'minPrice': float(property_obj.price_per_night),
                'maxOccupancy': property_obj.max_guests,
                'bedrooms': property_obj.bedrooms,
                'bathrooms': property_obj.bathrooms
            }]
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/properties",
                headers={
                    'Content-Type': 'application/json',
                    'accept': 'application/json',
                    'token': token
                },
                json=[property_data],  # Beds24 expects an array
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                created_property = result[0]
                return {
                    'success': True,
                    'property_id': str(created_property['id']),
                    'data': created_property
                }
            else:
                raise Exception('Unexpected response format from Beds24')
                
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f"Failed to create property on Beds24: {str(e)}"
            }
    
    def _map_property_type(self, property_type):
        """Map property type to Beds24 format"""
        mapping = {
            'house': 'house',
            'apartment': 'apartment',
            'villa': 'villa',
            'hotel': 'hotel',
            'hostel': 'hostel',
            'bnb': 'b&b',
            'bed_and_breakfast': 'b&b'
        }
        return mapping.get(property_type.lower(), 'house')
    
    def test_connection(self):
        """Test connection to Beds24 API"""
        try:
            token = self.get_access_token()
            response = requests.get(
                f"{self.base_url}/properties?limit=1",
                headers={
                    'accept': 'application/json',
                    'token': token
                },
                timeout=30
            )
            return response.status_code == 200
        except Exception:
            return False