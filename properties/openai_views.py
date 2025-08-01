# Backend API Updates for Enhanced Flexible Chat Interface

"""
This file contains the backend API endpoints that need to be implemented
to support the enhanced flexible chat interface for property onboarding.
"""

import os
import json
from typing import Dict, Any, Optional
try:
    import googlemaps
except ImportError:
    googlemaps = None
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    openai = None
    OpenAI = None
    OPENAI_AVAILABLE = False
    print("Warning: openai package not available. AI features will not work.")

# Initialize Google Maps client
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
gmaps = None
if GOOGLE_MAPS_API_KEY and googlemaps:
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = None
if OPENAI_API_KEY and OPENAI_AVAILABLE:
    client = OpenAI(api_key=OPENAI_API_KEY)

def validate_trust_level_discounts(extracted_data):
    """
    Validate and normalize trust level discounts from extracted data.
    """
    trust_fields = [
        'trust_level_1_discount', 'trust_level_2_discount', 
        'trust_level_3_discount', 'trust_level_4_discount', 
        'trust_level_5_discount'
    ]
    
    validated_discounts = {}
    for field in trust_fields:
        value = extracted_data.get(field, 0)
        try:
            # Convert to float and validate range
            discount = float(value)
            if 0 <= discount <= 100:
                validated_discounts[field] = discount
            else:
                validated_discounts[field] = 0  # Default to 0 if invalid
        except (ValueError, TypeError):
            validated_discounts[field] = 0  # Default to 0 if invalid
    
    return validated_discounts

@csrf_exempt
@require_http_methods(["POST"])
def flexible_conversation_extract(request):
    """
    Enhanced AI extraction endpoint for flexible conversation flow.
    This replaces the existing ai-extract endpoint with more dynamic responses.
    """
    try:
        data = json.loads(request.body)
        
        # Extract parameters
        current_response = data.get('current_response', '')
        question_context = data.get('question_context', '')
        previous_data = data.get('previous_data', {})
        conversation_history = data.get('conversation_history', [])
        current_completion_percentage = data.get('current_completion_percentage', 0)
        missing_fields_detail = data.get('missing_fields_detail', [])
        conversation_style = data.get('conversation_style', 'dynamic_friendly')
        response_tone = data.get('response_tone', 'enthusiastic_helpful')
        
        # Build the prompt for OpenAI
        system_prompt = f"""You are a friendly, enthusiastic AI property assistant helping users create property listings. 
        
Your conversation style should be:
- {conversation_style}: Natural, engaging, and conversational
- {response_tone}: Helpful, encouraging, and positive

Current completion: {current_completion_percentage}%
Missing fields: {', '.join([field['name'] for field in missing_fields_detail])}

Previous conversation:
{chr(10).join([f"User: {msg}" for msg in conversation_history[-3:]])}

Current user response: "{current_response}"

Your task:
1. Extract any property information from the user's response
2. Provide a natural, conversational response that acknowledges what they said
3. Ask for missing information in a friendly way
4. Use emojis and be enthusiastic

Property fields to extract:
- Basic: title, description, property_type, place_type
- Location: address, city, state, country, postal_code, neighborhood
- Space: max_guests, bedrooms, beds, bathrooms, square_feet
- Pricing: price_per_night, cleaning_fee, security_deposit
- Trust discounts: trust_level_1_discount, trust_level_2_discount, trust_level_3_discount, trust_level_4_discount, trust_level_5_discount
- Features: amenities, safety_features, accessibility_features
- Rules: house_rules, smoking_allowed, pets_allowed, events_allowed, children_welcome
- Booking: booking_type, minimum_stay, maximum_stay

Example conversation flow:
User: "It's a small house just outside town. Nothing fancy but it's warm and quiet."
Assistant: "That sounds lovely! 🏡 A warm and quiet house just outside of town is a great option. Um, actually we need some more details about your property! Could you please tell me the other information about your property? For example, the location, the number of bedrooms and bathrooms and amenities, your neighborhoods etc."

Respond in this format:
{{
    "extracted": {{"field_name": "value"}},
    "question": "Your conversational response here",
    "next_action": "continue_conversation|transition_to_guided|complete",
    "reasoning": "Why you chose this response"
}}"""

        # Check if OpenAI client is available
        if not client:
            return JsonResponse({
                "success": False,
                "error": "AI service is not configured. Please contact support."
            })
            
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": current_response}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        # Parse the response
        ai_response = response.choices[0].message.content
        try:
            parsed_response = json.loads(ai_response)
            
            # Validate and process trust level discounts if present
            if 'extracted' in parsed_response:
                trust_discounts = validate_trust_level_discounts(parsed_response['extracted'])
                parsed_response['extracted'].update(trust_discounts)
                
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            parsed_response = {
                "extracted": {},
                "question": ai_response,
                "next_action": "continue_conversation",
                "reasoning": "AI provided conversational response"
            }
        
        return JsonResponse({
            "success": True,
            "extracted": parsed_response.get("extracted", {}),
            "question": parsed_response.get("question", ""),
            "next_action": parsed_response.get("next_action", "continue_conversation"),
            "reasoning": parsed_response.get("reasoning", ""),
            "confidence": 0.9
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def validate_address(request):
    """
    Address validation endpoint using Google Maps API.
    Validates addresses and returns structured location data.
    """
    try:
        data = json.loads(request.body)
        address = data.get('address', '')
        
        if not address:
            return JsonResponse({
                "success": False,
                "isValid": False,
                "error": "Address is required"
            })
        
        # Check if Google Maps client is available
        if not gmaps:
            return JsonResponse({
                "success": False,
                "isValid": False,
                "error": "Address validation service is not configured. Please contact support."
            })
        
        # Use Google Maps Geocoding API
        geocode_result = gmaps.geocode(address)
        
        if not geocode_result:
            return JsonResponse({
                "success": False,
                "isValid": False,
                "error": "Address not found"
            })
        
        # Extract location data
        location = geocode_result[0]
        geometry = location.get('geometry', {})
        address_components = location.get('address_components', [])
        
        # Parse address components
        location_data = {
            "address": location.get('formatted_address', address),
            "house_number": "",
            "street": "",
            "city": "",
            "state": "",
            "country": "",
            "postal_code": "",
            "neighborhood": "",
            "latitude": geometry.get('location', {}).get('lat', 0),
            "longitude": geometry.get('location', {}).get('lng', 0)
        }
        
        # Extract specific components
        for component in address_components:
            types = component.get('types', [])
            value = component.get('long_name', '')
            
            if 'street_number' in types:
                location_data['house_number'] = value
            elif 'route' in types:
                location_data['street'] = value
            elif 'locality' in types or 'sublocality' in types:
                location_data['city'] = value
            elif 'administrative_area_level_1' in types:
                location_data['state'] = value
            elif 'country' in types:
                location_data['country'] = value
            elif 'postal_code' in types:
                location_data['postal_code'] = value
            elif 'neighborhood' in types or 'sublocality_level_1' in types:
                location_data['neighborhood'] = value
        
        # Validate that we have essential components
        essential_fields = ['city', 'state', 'country']
        missing_essential = [field for field in essential_fields if not location_data[field]]
        
        if missing_essential:
            return JsonResponse({
                "success": False,
                "isValid": False,
                "error": f"Address is incomplete. Missing: {', '.join(missing_essential)}"
            })
        
        return JsonResponse({
            "success": True,
            "isValid": True,
            "locationData": location_data
        })
        
    except Exception as e:
        return JsonResponse({
            "success": False,
            "isValid": False,
            "error": f"Validation failed: {str(e)}"
        }, status=500)