# Additional utility functions and settings for the backend

# settings.py - Add these settings
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', 'your-openai-api-key-here')

# Add logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'ai_extraction.log',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'properties.views': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# properties/utils.py - Additional utility functions
import re
from typing import Dict, List, Any

def extract_trust_level_discounts(text: str) -> Dict[str, int]:
    """Extract trust level discounts from text"""
    trust_data = {}
    
    # Look for trust level mentions and percentages
    trust_patterns = [
        r'bronze\s*(\w+\s+)?(\d+)%',
        r'silver\s*(\w+\s+)?(\d+)%',
        r'gold\s*(\w+\s+)?(\d+)%',
        r'platinum\s*(\w+\s+)?(\d+)%',
        r'diamond\s*(\w+\s+)?(\d+)%',
    ]
    
    level_names = ['bronze', 'silver', 'gold', 'platinum', 'diamond']
    
    for i, pattern in enumerate(trust_patterns):
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            for match in matches:
                try:
                    percent = int(match[1]) if match[1] else int(match[0])
                    if 0 <= percent <= 50:
                        trust_data[f'trust_level_{i + 1}_discount'] = percent
                except (ValueError, IndexError):
                    continue

    # Look for general percentage mentions that might relate to discounts
    if not trust_data:
        general_discount_pattern = r'(\d+)%\s*(discount|off|reduction)'
        general_matches = re.findall(general_discount_pattern, text, re.IGNORECASE)
        if general_matches:
            try:
                base_percent = int(general_matches[0][0])
                if base_percent > 0:
                    trust_data['trust_level_1_discount'] = max(1, round(base_percent * 0.4))
                    trust_data['trust_level_2_discount'] = max(2, round(base_percent * 0.6))
                    trust_data['trust_level_3_discount'] = max(3, round(base_percent * 0.8))
                    trust_data['trust_level_4_discount'] = max(4, base_percent)
                    trust_data['trust_level_5_discount'] = max(5, round(base_percent * 1.2))
            except (ValueError, IndexError):
                pass
    
    return trust_data

def validate_time_format(time_string: str) -> str:
    """Convert time to 24-hour HH:MM format"""
    if not time_string:
        return ''
    
    # Clean the input
    time_str = time_string.strip().lower()
    time_str = re.sub(r'[^\d:apm\s]', '', time_str)
    
    # Check if already in 24-hour format
    if re.match(r'^\d{2}:\d{2}$', time_str):
        return time_str
    
    # Handle 12-hour format with AM/PM
    match = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', time_str)
    if match:
        hour = int(match.group(1))
        minute = match.group(2)
        period = match.group(3)
        
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
            
        return f"{hour:02d}:{minute}"
    
    # Handle hour only with AM/PM
    match = re.match(r'^(\d{1,2})\s*(am|pm)$', time_str)
    if match:
        hour = int(match.group(1))
        period = match.group(2)
        
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
            
        return f"{hour:02d}:00"
    
    # Handle 24-hour format without colon
    match = re.match(r'^(\d{2})(\d{2})$', time_str)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    
    return ''

def normalize_amenities(amenities_list: List[str]) -> List[str]:
    """Normalize amenity names to standard format"""
    if not isinstance(amenities_list, list):
        return []
    
    valid_amenities = [
        'wifi', 'kitchen', 'tv', 'air_conditioning', 'parking', 'pool', 
        'washer', 'dryer', 'dishwasher', 'gym', 'hot_tub', 'balcony', 'garden'
    ]
    
    normalized = []
    
    for amenity in amenities_list:
        if not isinstance(amenity, str):
            continue
            
        amenity_lower = amenity.lower().strip()
        
        # Direct match
        if amenity_lower in valid_amenities:
            normalized.append(amenity_lower)
            continue
        
        # Fuzzy matching
        if 'wifi' in amenity_lower or 'internet' in amenity_lower:
            normalized.append('wifi')
        elif 'kitchen' in amenity_lower:
            normalized.append('kitchen')
        elif 'tv' in amenity_lower or 'television' in amenity_lower:
            normalized.append('tv')
        elif 'air' in amenity_lower and ('con' in amenity_lower or 'cool' in amenity_lower):
            normalized.append('air_conditioning')
        elif 'parking' in amenity_lower or 'garage' in amenity_lower:
            normalized.append('parking')
        elif 'pool' in amenity_lower or 'swimming' in amenity_lower:
            normalized.append('pool')
        elif 'washer' in amenity_lower or 'washing' in amenity_lower:
            normalized.append('washer')
        elif 'dryer' in amenity_lower:
            normalized.append('dryer')
        elif 'dishwasher' in amenity_lower:
            normalized.append('dishwasher')
        elif 'gym' in amenity_lower or 'fitness' in amenity_lower:
            normalized.append('gym')
        elif 'hot tub' in amenity_lower or 'jacuzzi' in amenity_lower:
            normalized.append('hot_tub')
        elif 'balcony' in amenity_lower or 'terrace' in amenity_lower:
            normalized.append('balcony')
        elif 'garden' in amenity_lower or 'yard' in amenity_lower:
            normalized.append('garden')
    
    return list(set(normalized))  # Remove duplicates

def extract_location_components(text: str) -> Dict[str, str]:
    """Extract location components from text"""
    location_data = {}
    
    # Address pattern (house number + street)
    address_match = re.search(r'(\d+\s+[A-Za-z\s]+(?:street|avenue|road|drive|lane|boulevard|way|estate|villa|close|place|court))', text, re.IGNORECASE)
    if address_match:
        full_address = address_match.group(1)
        location_data['address'] = full_address
        
        # Extract house number
        house_number_match = re.match(r'^(\d+)', full_address)
        if house_number_match:
            location_data['house_number'] = house_number_match.group(1)
            # Extract street (everything after house number)
            street = full_address[len(house_number_match.group(1)):].strip()
            if street:
                location_data['street'] = street
    
    # City extraction
    city_patterns = [
        r'(?:in|at|near|located in|city of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*(?:[A-Z]{2}|[A-Za-z]+)'
    ]
    
    for pattern in city_patterns:
        city_match = re.search(pattern, text)
        if city_match and not location_data.get('city'):
            location_data['city'] = city_match.group(1)
            break
    
    # Country extraction
    country_patterns = [
        r'(?:in|country|located in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        r',\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)$'
    ]
    
    for pattern in country_patterns:
        country_match = re.search(pattern, text)
        if country_match and not location_data.get('country'):
            potential_country = country_match.group(1)
            # Avoid extracting cities as countries
            if potential_country.lower() not in ['street', 'road', 'avenue', 'drive']:
                location_data['country'] = potential_country
                break
    
    return location_data

def validate_numeric_field(value: Any, field_name: str) -> Any:
    """Validate numeric fields with appropriate ranges"""
    if value is None:
        return None
    
    try:
        num_value = float(value)
        
        # Define reasonable ranges for different fields
        ranges = {
            'max_guests': (1, 50),
            'bedrooms': (0, 20),
            'bathrooms': (0.5, 20),
            'display_price': (1, 10000),
            'price_per_night': (1, 10000),
            'trust_level_1_discount': (0, 50),
            'trust_level_2_discount': (0, 50),
            'trust_level_3_discount': (0, 50),
            'trust_level_4_discount': (0, 50),
            'trust_level_5_discount': (0, 50),
        }
        
        if field_name in ranges:
            min_val, max_val = ranges[field_name]
            if min_val <= num_value <= max_val:
                # Return as int for whole numbers, float for decimals
                return int(num_value) if num_value == int(num_value) else num_value
        
        return None
    except (ValueError, TypeError):
        return None

# properties/middleware.py - Add rate limiting for AI calls
from django.core.cache import cache
from django.http import JsonResponse
import time

class AIRateLimitMiddleware:
    """Rate limiting middleware for AI API calls"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is an AI extraction request
        if request.path.startswith('/api/ai/') and request.method == 'POST':
            user_id = getattr(request.user, 'id', 'anonymous')
            cache_key = f'ai_rate_limit_{user_id}'
            
            # Get current request count
            current_count = cache.get(cache_key, 0)
            
            # Allow 30 requests per minute
            if current_count >= 30:
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please wait a moment before trying again.'
                }, status=429)
            
            # Increment counter
            cache.set(cache_key, current_count + 1, 60)  # 60 seconds
        
        response = self.get_response(request)
        return response

# Error handling decorator
from functools import wraps
from django.http import JsonResponse
import traceback

def handle_ai_errors(func):
    """Decorator to handle AI-related errors gracefully"""
    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        try:
            return func(self, request, *args, **kwargs)
        except openai.APIConnectionError:
            logger.error("OpenAI API connection error")
            return JsonResponse({
                'error': 'AI service temporarily unavailable. Please try again.',
                'fallback': True
            }, status=503)
        except openai.RateLimitError:
            logger.error("OpenAI rate limit exceeded")
            return JsonResponse({
                'error': 'AI service rate limit exceeded. Please wait a moment.',
                'fallback': True
            }, status=429)
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return JsonResponse({
                'error': 'AI service error. Please try again.',
                'fallback': True
            }, status=500)
        except Exception as e:
            logger.error(f"Unexpected error in AI extraction: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'error': 'An unexpected error occurred. Please try again.',
                'fallback': True
            }, status=500)
    return wrapper

# Apply the decorator to your AIPropertyExtractView methods
# Just add @handle_ai_errors above each method in the class
