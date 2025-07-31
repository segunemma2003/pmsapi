"""
NLP Utilities for Enhanced Property Extraction
This module provides advanced NLP capabilities for better information extraction.
"""

import re
import spacy
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from transformers import pipeline
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer

# Import city/country validation libraries
try:
    import pycountry
    PYCOUNTRY_AVAILABLE = True
except ImportError:
    PYCOUNTRY_AVAILABLE = False
    print("Warning: pycountry not available. Install with: pip install pycountry")

try:
    from geonamescache import GeonamesCache
    GEONAMES_AVAILABLE = True
except ImportError:
    GEONAMES_AVAILABLE = False
    print("Warning: geonamescache not available. Install with: pip install geonamescache")

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    print("Warning: geopy not available. Install with: pip install geopy")

# Download required NLTK data
try:
    nltk.data.find('vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')

@dataclass
class ExtractedEntity:
    """Represents an extracted entity from user input."""
    text: str
    label: str
    confidence: float
    start: int
    end: int

@dataclass
class UserIntent:
    """Represents the user's intent."""
    intent: str
    confidence: float
    entities: List[str]

@dataclass
class SentimentAnalysis:
    """Represents sentiment analysis results."""
    sentiment: str  # 'positive', 'negative', 'neutral'
    confidence: float
    compound_score: float

class NLPProcessor:
    """Advanced NLP processor for property information extraction."""
    
    def __init__(self):
        """Initialize NLP models and processors."""
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            # Fallback if model not available
            self.nlp = None
            print("Warning: spaCy model not available. Using fallback extraction.")
        
        # Initialize sentiment analyzer
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        
        # Initialize geocoding libraries
        if GEONAMES_AVAILABLE:
            self.geonames = GeonamesCache()
            self.cities = self.geonames.get_cities()
            self.countries = self.geonames.get_countries()
        else:
            self.geonames = None
            self.cities = {}
            self.countries = {}
        
        if GEOPY_AVAILABLE:
            self.geolocator = Nominatim(user_agent="trustify_property_assistant")
        else:
            self.geolocator = None
        
        # Fallback lists for when libraries are not available
        self.FALLBACK_CITIES = {
            'new york', 'los angeles', 'chicago', 'houston', 'phoenix', 'philadelphia', 'san antonio', 
            'san diego', 'dallas', 'san jose', 'austin', 'jacksonville', 'fort worth', 'columbus', 
            'charlotte', 'san francisco', 'indianapolis', 'seattle', 'denver', 'washington', 'boston', 
            'el paso', 'nashville', 'detroit', 'oklahoma city', 'portland', 'las vegas', 'memphis', 
            'louisville', 'baltimore', 'milwaukee', 'albuquerque', 'tucson', 'fresno', 'sacramento', 
            'atlanta', 'kansas city', 'long beach', 'colorado springs', 'raleigh', 'miami', 'virginia beach',
            'omaha', 'oakland', 'minneapolis', 'tulsa', 'arlington', 'tampa', 'new orleans', 'wichita',
            'cleveland', 'bakersfield', 'aurora', 'anaheim', 'honolulu', 'santa ana', 'corpus christi',
            'riverside', 'lexington', 'stockton', 'henderson', 'saint paul', 'st. louis', 'milwaukee',
            'baltimore', 'salt lake city', 'orlando', 'san antonio', 'laredo', 'chandler', 'madison',
            'lubbock', 'scottsdale', 'reno', 'buffalo', 'gilbert', 'glendale', 'north las vegas',
            'winston salem', 'chesapeake', 'norfolk', 'fremont', 'garland', 'irvine', 'hialeah',
            'laredo', 'lubbock', 'akron', 'arlington', 'rochester', 'stockton', 'bakersfield',
            'fremont', 'garland', 'huntington beach', 'modesto', 'glendale', 'des moines',
            'tacoma', 'irvine', 'durham', 'spokane', 'santa rosa', 'oxnard', 'fort lauderdale',
            'boise', 'richmond', 'baton rouge', 'hialeah', 'spokane', 'fremont', 'billings',
            'santa barbara', 'palm springs', 'palm desert', 'indio', 'coachella', 'cathedral city',
            'la quinta', 'rancho mirage', 'desert hot springs'
        }
        
        self.FALLBACK_COUNTRIES = {
            'united states', 'usa', 'us', 'canada', 'mexico', 'united kingdom', 'uk', 'england',
            'scotland', 'wales', 'northern ireland', 'ireland', 'france', 'germany', 'italy',
            'spain', 'portugal', 'netherlands', 'belgium', 'switzerland', 'austria', 'denmark',
            'norway', 'sweden', 'finland', 'iceland', 'poland', 'czech republic', 'slovakia',
            'hungary', 'romania', 'bulgaria', 'greece', 'turkey', 'russia', 'ukraine', 'belarus',
            'latvia', 'lithuania', 'estonia', 'moldova', 'georgia', 'armenia', 'azerbaijan',
            'kazakhstan', 'uzbekistan', 'turkmenistan', 'kyrgyzstan', 'tajikistan', 'afghanistan',
            'pakistan', 'india', 'bangladesh', 'sri lanka', 'nepal', 'bhutan', 'myanmar',
            'thailand', 'laos', 'cambodia', 'vietnam', 'malaysia', 'singapore', 'indonesia',
            'philippines', 'brunei', 'east timor', 'papua new guinea', 'australia', 'new zealand',
            'fiji', 'vanuatu', 'solomon islands', 'new caledonia', 'french polynesia', 'samoa',
            'tonga', 'tuvalu', 'kiribati', 'marshall islands', 'micronesia', 'palau', 'nauru',
            'japan', 'south korea', 'north korea', 'china', 'mongolia', 'taiwan', 'hong kong',
            'macau', 'brazil', 'argentina', 'chile', 'peru', 'bolivia', 'paraguay', 'uruguay',
            'ecuador', 'colombia', 'venezuela', 'guyana', 'suriname', 'french guiana', 'falkland islands',
            'south africa', 'namibia', 'botswana', 'zimbabwe', 'mozambique', 'zambia', 'malawi',
            'tanzania', 'kenya', 'uganda', 'rwanda', 'burundi', 'democratic republic of congo',
            'republic of congo', 'gabon', 'equatorial guinea', 'cameroon', 'central african republic',
            'chad', 'niger', 'nigeria', 'benin', 'togo', 'ghana', 'ivory coast', 'liberia',
            'sierra leone', 'guinea', 'guinea bissau', 'senegal', 'gambia', 'mauritania',
            'morocco', 'algeria', 'tunisia', 'libya', 'egypt', 'sudan', 'south sudan', 'ethiopia',
            'eritrea', 'djibouti', 'somalia', 'madagascar', 'mauritius', 'seychelles', 'comoros',
            'mayotte', 'reunion', 'cape verde', 'sao tome and principe', 'angola', 'saint helena',
            'ascension', 'tristan da cunha', 'western sahara'
        }
            'scotland', 'wales', 'northern ireland', 'ireland', 'france', 'germany', 'italy',
            'spain', 'portugal', 'netherlands', 'belgium', 'switzerland', 'austria', 'denmark',
            'norway', 'sweden', 'finland', 'iceland', 'poland', 'czech republic', 'slovakia',
            'hungary', 'romania', 'bulgaria', 'greece', 'turkey', 'russia', 'ukraine', 'belarus',
            'latvia', 'lithuania', 'estonia', 'moldova', 'georgia', 'armenia', 'azerbaijan',
            'kazakhstan', 'uzbekistan', 'turkmenistan', 'kyrgyzstan', 'tajikistan', 'afghanistan',
            'pakistan', 'india', 'bangladesh', 'sri lanka', 'nepal', 'bhutan', 'myanmar',
            'thailand', 'laos', 'cambodia', 'vietnam', 'malaysia', 'singapore', 'indonesia',
            'philippines', 'brunei', 'east timor', 'papua new guinea', 'australia', 'new zealand',
            'fiji', 'vanuatu', 'solomon islands', 'new caledonia', 'french polynesia', 'samoa',
            'tonga', 'tuvalu', 'kiribati', 'marshall islands', 'micronesia', 'palau', 'nauru',
            'japan', 'south korea', 'north korea', 'china', 'mongolia', 'taiwan', 'hong kong',
            'macau', 'brazil', 'argentina', 'chile', 'peru', 'bolivia', 'paraguay', 'uruguay',
            'ecuador', 'colombia', 'venezuela', 'guyana', 'suriname', 'french guiana', 'falkland islands',
            'south africa', 'namibia', 'botswana', 'zimbabwe', 'mozambique', 'zambia', 'malawi',
            'tanzania', 'kenya', 'uganda', 'rwanda', 'burundi', 'democratic republic of congo',
            'republic of congo', 'gabon', 'equatorial guinea', 'cameroon', 'central african republic',
            'chad', 'niger', 'nigeria', 'benin', 'togo', 'ghana', 'ivory coast', 'liberia',
            'sierra leone', 'guinea', 'guinea bissau', 'senegal', 'gambia', 'mauritania',
            'morocco', 'algeria', 'tunisia', 'libya', 'egypt', 'sudan', 'south sudan', 'ethiopia',
            'eritrea', 'djibouti', 'somalia', 'madagascar', 'mauritius', 'seychelles', 'comoros',
            'mayotte', 'reunion', 'cape verde', 'sao tome and principe', 'angola', 'saint helena',
            'ascension', 'tristan da cunha', 'western sahara', 'morocco', 'algeria', 'tunisia',
            'libya', 'egypt', 'sudan', 'south sudan', 'ethiopia', 'eritrea', 'djibouti', 'somalia',
            'madagascar', 'mauritius', 'seychelles', 'comoros', 'mayotte', 'reunion', 'cape verde',
            'sao tome and principe', 'angola', 'saint helena', 'ascension', 'tristan da cunha'
        }
        
        # Property-specific entity patterns
        self.PROPERTY_ENTITIES = {
            'property_type': [
                r'\b(house|apartment|villa|cabin|loft|condo|townhouse|studio|penthouse|chalet|cottage|bungalow|mansion|duplex|triplex)\b',
                r'\b(single family|multi family|residential|commercial|vacation home|beach house|mountain cabin)\b'
            ],
            'location': [
                r'\b(city|town|village|neighborhood|district|area|zone|region|state|province|country)\b',
                r'\b(downtown|uptown|suburb|rural|urban|coastal|mountain|lakefront|beachfront)\b'
            ],
            'capacity': [
                r'\b(\d+)\s*(guest|guests|person|people|occupant|occupants)\b',
                r'\b(accommodate|fit|sleep|host)\s*(\d+)\b',
                r'\b(maximum|max|up to|capacity of)\s*(\d+)\b'
            ],
            'bedrooms': [
                r'\b(\d+)\s*(bedroom|bedrooms|bed|beds)\b',
                r'\b(\d+)\s*BR\b',
                r'\b(bedroom|bedrooms|bed|beds)\s*(\d+)\b'
            ],
            'bathrooms': [
                r'\b(\d+)\s*(bathroom|bathrooms|bath|baths)\b',
                r'\b(\d+)\s*BA\b',
                r'\b(bathroom|bathrooms|bath|baths)\s*(\d+)\b'
            ],
            'price': [
                r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
                r'\b(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(dollars?|USD|per night|nightly|daily)\b',
                r'\b(rate|price|cost|charge)\s*(?:of|is|at)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\b'
            ],
            'amenities': [
                r'\b(wifi|internet|kitchen|parking|pool|gym|garden|balcony|terrace|fireplace|air conditioning|heating|washer|dryer|dishwasher|tv|netflix|amazon prime|hulu|disney plus|spotify|apple music|youtube music|youtube tv|hbo max|peacock|paramount plus|showtime|starz|cinemax|epix|mubi|criterion channel|kanopy|hoopla|tubi|pluto tv|roku channel|vudu|fandango now|google play movies|itunes|microsoft store|playstation store|xbox store|nintendo eshop|steam|epic games store|gog|origin|uplay|battle net|discord|twitch|reddit|facebook|instagram|twitter|tiktok|linkedin|pinterest|snapchat|whatsapp|telegram|signal|zoom|skype|teams|slack|discord|trello|asana|notion|evernote|dropbox|google drive|onedrive|icloud|box|mega|pcloud|sync|tresorit|protonmail|tutanota|posteo|mailbox|fastmail|zoho|yandex|outlook|gmail|yahoo|aol|icloud|protonmail|tutanota|posteo|mailbox|fastmail|zoho|yandex|outlook|gmail|yahoo|aol)\b',
                r'\b(full kitchen|equipped kitchen|modern kitchen|updated kitchen|granite countertops|stainless steel appliances|dishwasher|microwave|oven|stove|refrigerator|freezer|coffee maker|toaster|blender|mixer|food processor|slow cooker|instant pot|air fryer|rice cooker|bread maker|juicer|smoothie maker|ice cream maker|popcorn maker|waffle maker|panini press|grill|smoker|dehydrator|vacuum sealer|food scale|thermometer|timer|alarm clock|radio|bluetooth speaker|portable speaker|wireless speaker|smart speaker|echo|google home|apple homepod|sonos|bose|jbl|harman kardon|klipsch|definitive technology|polk|klipsch|definitive technology|polk|b&w|kef|monitor audio|focal|dynaudio|elac|psb|paradigm|energy|mirage|athena|axiom|aperion|ascend|htd|svs|rythmik|hsu|outlaw|emotiva|schiit|topping|smsl|fiio|ifi|audioquest|cardas|kimber|nordost|wireworld|audioquest|cardas|kimber|nordost|wireworld|monster|belkin|tripp lite|apc|cyberpower|ups|battery backup|surge protector|power strip|extension cord|outlet|switch|dimmer|smart switch|smart outlet|smart plug|smart bulb|smart light|smart thermostat|smart lock|smart doorbell|smart camera|smart sensor|smart hub|smart home|home automation|home security|alarm system|security system|monitoring|surveillance|cctv|ip camera|webcam|action camera|drone|gopro|dji|parrot|autel|skydio|ryze|hubsan|syma|holy stone|potensic|snaptain|contixo|altair|volantex|eachine|betafpv|emax|diatone|iflight|tbs|crossfire|expresslrs|frsky|flysky|turnigy|hitec|futaba|jr|spectrum|graupner|multiplex|robbe|sanwa|ko|ko propo|futaba|jr|spectrum|graupner|multiplex|robbe|sanwa|ko|ko propo|futaba|jr|spectrum|graupner|multiplex|robbe|sanwa|ko|ko propo)\b'
            ]
        }
        
        # Intent patterns
        self.INTENT_PATTERNS = {
            'provide_information': [
                r'\b(it is|it\'s|this is|that is|we have|i have|there is|there are)\b',
                r'\b(property|house|apartment|place|home|listing)\b',
                r'\b(located|situated|found|in|at|near|close to|next to)\b'
            ],
            'clarification': [
                r'\b(what do you mean|i don\'t understand|can you explain|clarify|repeat)\b',
                r'\b(sorry|excuse me|pardon|what was that)\b'
            ],
            'frustration': [
                r'\b(frustrated|annoyed|tired|bored|fed up|sick of)\b',
                r'\b(again|repeatedly|over and over|multiple times)\b',
                r'\b(why|how many times|when will this end)\b'
            ]
        }
    
    def validate_city(self, text: str) -> Tuple[bool, str]:
        """Validate if the text represents a valid city using multiple validation methods."""
        text_lower = text.lower().strip()
        
        # Method 1: Check against fallback city list
        if text_lower in self.FALLBACK_CITIES:
            return True, text_lower.title()
        
        # Method 2: Use geonamescache library if available
        if GEONAMES_AVAILABLE and self.cities:
            # Search for city in geonames data
            for city_id, city_data in self.cities.items():
                city_name = city_data.get('name', '').lower()
                if text_lower == city_name:
                    return True, city_data.get('name', text).title()
        
        # Method 3: Use geopy for geocoding validation
        if GEOPY_AVAILABLE and self.geolocator:
            try:
                location = self.geolocator.geocode(text, timeout=5)
                if location and 'city' in location.raw.get('type', '').lower():
                    return True, location.address.split(',')[0].title()
            except (GeocoderTimedOut, GeocoderUnavailable):
                pass
        
        # Method 4: Use pycountry for country validation (cities might be in country names)
        if PYCOUNTRY_AVAILABLE:
            try:
                # Check if it's a country name (sometimes users confuse cities with countries)
                country = pycountry.countries.search_fuzzy(text)
                if country:
                    return False, text  # It's a country, not a city
            except LookupError:
                pass
        
        # Method 5: Pattern matching for common city patterns
        city_patterns = [
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:city|town|village)\b',
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        ]
        
        for pattern in city_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                potential_city = match.group(1).lower()
                if potential_city in self.FALLBACK_CITIES:
                    return True, potential_city.title()
        
        return False, text
    
    def validate_country(self, text: str) -> Tuple[bool, str]:
        """Validate if the text represents a valid country using multiple validation methods."""
        text_lower = text.lower().strip()
        
        # Method 1: Check against fallback country list
        if text_lower in self.FALLBACK_COUNTRIES:
            return True, text_lower.title()
        
        # Method 2: Use pycountry library if available
        if PYCOUNTRY_AVAILABLE:
            try:
                # Search for exact match
                country = pycountry.countries.search_fuzzy(text)
                if country:
                    return True, country[0].name
            except LookupError:
                pass
        
        # Method 3: Use geonamescache library if available
        if GEONAMES_AVAILABLE and self.countries:
            # Search for country in geonames data
            for country_code, country_data in self.countries.items():
                country_name = country_data.get('name', '').lower()
                if text_lower == country_name:
                    return True, country_data.get('name', text).title()
        
        # Method 4: Handle common country abbreviations and variations
        country_mappings = {
            'usa': 'United States',
            'us': 'United States',
            'uk': 'United Kingdom',
            'england': 'United Kingdom',
            'scotland': 'United Kingdom',
            'wales': 'United Kingdom',
            'northern ireland': 'United Kingdom'
        }
        
        if text_lower in country_mappings:
            return True, country_mappings[text_lower]
        
        return False, text
    
    def extract_entities(self, text: str) -> List[ExtractedEntity]:
        """Extract entities using spaCy and pattern matching."""
        entities = []
        
        # Use spaCy if available
        if self.nlp:
            doc = self.nlp(text)
            for ent in doc.ents:
                entities.append(ExtractedEntity(
                    text=ent.text,
                    label=ent.label_,
                    confidence=0.8,
                    start=ent.start_char,
                    end=ent.end_char
                ))
        
        # Pattern-based extraction
        for entity_type, patterns in self.PROPERTY_ENTITIES.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entities.append(ExtractedEntity(
                        text=match.group(),
                        label=entity_type,
                        confidence=0.7,
                        start=match.start(),
                        end=match.end()
                    ))
        
        # Context-aware number extraction
        numbers = self._extract_contextual_numbers(text)
        entities.extend(numbers)
        
        # City and country extraction with validation
        city_country_entities = self._extract_city_country(text)
        entities.extend(city_country_entities)
        
        return entities
    
    def _extract_city_country(self, text: str) -> List[ExtractedEntity]:
        """Extract and validate city and country entities."""
        entities = []
        
        # Look for city/country patterns
        words = text.split()
        for i, word in enumerate(words):
            word_clean = re.sub(r'[^\w\s]', '', word).strip()
            if not word_clean:
                continue
            
            # Check for city
            is_valid_city, city_name = self.validate_city(word_clean)
            if is_valid_city:
                entities.append(ExtractedEntity(
                    text=city_name,
                    label='city',
                    confidence=0.9,
                    start=text.find(word),
                    end=text.find(word) + len(word)
                ))
            
            # Check for country
            is_valid_country, country_name = self.validate_country(word_clean)
            if is_valid_country:
                entities.append(ExtractedEntity(
                    text=country_name,
                    label='country',
                    confidence=0.9,
                    start=text.find(word),
                    end=text.find(word) + len(word)
                ))
        
        return entities
    
    def _extract_contextual_numbers(self, text: str) -> List[ExtractedEntity]:
        """Extract numbers with context awareness."""
        entities = []
        
        # Number patterns with context
        patterns = [
            (r'(\d+)\s*(bedroom|bedrooms|bed|beds)', 'bedrooms'),
            (r'(\d+)\s*(bathroom|bathrooms|bath|baths)', 'bathrooms'),
            (r'(\d+)\s*(guest|guests|person|people)', 'capacity'),
            (r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'price'),
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(dollars?|USD|per night)', 'price')
        ]
        
        for pattern, label in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append(ExtractedEntity(
                    text=match.group(),
                    label=label,
                    confidence=0.9,
                    start=match.start(),
                    end=match.end()
                ))
        
        return entities
    
    def classify_intent(self, text: str) -> UserIntent:
        """Classify user intent."""
        text_lower = text.lower()
        max_confidence = 0.0
        detected_intent = 'provide_information'  # default
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            confidence = 0.0
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    confidence += 0.3
            
            if confidence > max_confidence:
                max_confidence = confidence
                detected_intent = intent
        
        return UserIntent(
            intent=detected_intent,
            confidence=min(max_confidence, 1.0),
            entities=[]
        )
    
    def analyze_sentiment(self, text: str) -> SentimentAnalysis:
        """Analyze sentiment of user input."""
        scores = self.sentiment_analyzer.polarity_scores(text)
        
        # Determine sentiment
        if scores['compound'] >= 0.05:
            sentiment = 'positive'
        elif scores['compound'] <= -0.05:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return SentimentAnalysis(
            sentiment=sentiment,
            confidence=abs(scores['compound']),
            compound_score=scores['compound']
        )
    
    def should_move_to_next_question(self, extracted_data: Dict, missing_fields: List[Dict]) -> bool:
        """Determine if we should move to the next question based on extracted data."""
        if not extracted_data:
            return False
        
        # If we extracted any meaningful data, move to next question
        meaningful_fields = ['property_type', 'city', 'country', 'bedrooms', 'bathrooms', 'capacity', 'price', 'amenities']
        extracted_meaningful = any(field in extracted_data for field in meaningful_fields)
        
        return extracted_meaningful
    
    def generate_follow_up_question(self, 
                                  missing_fields: List[Dict], 
                                  user_intent: UserIntent,
                                  sentiment: SentimentAnalysis,
                                  extraction_attempts: int = 0,
                                  extracted_data: Dict = None) -> str:
        """Generate contextually appropriate follow-up questions."""
        
        if not missing_fields:
            return "Great! I think I have all the information I need. Is there anything else you'd like to add?"
        
        # Check if we should move to next question based on extracted data
        if extracted_data and self.should_move_to_next_question(extracted_data, missing_fields):
            # Move to the next missing field
            if len(missing_fields) > 1:
                next_field = missing_fields[1]  # Move to next field
            else:
                next_field = missing_fields[0]  # Stay on current field if it's the last one
        else:
            # Stay on current field
            next_field = missing_fields[0]
        
        # Handle frustration
        if sentiment.sentiment == 'negative' or user_intent.intent == 'frustration':
            if extraction_attempts >= 3:
                return "I apologize for the confusion. Let me ask you directly: what type of property are you listing?"
            else:
                return "I understand this might be frustrating. Let me try a different approach. Could you tell me more about your property?"
        
        field_name = next_field['name'].lower()
        
        # Apologetic starters based on sentiment
        if sentiment.sentiment == 'negative':
            starter = "I'm sorry, I didn't catch that. "
        elif extraction_attempts > 0:
            starter = "Excuse me, I still need to know about "
        else:
            starter = "Could you tell me about "
        
        # Field-specific questions with improved flow
        questions = {
            'property_type': f"{starter}what type of property you're listing? Is it a house, apartment, villa, cabin, or loft? 🏠",
            'location': f"{starter}where your property is located? 🌆",
            'city': f"{starter}which city is your property in? 🏙️",
            'country': f"{starter}which country is your property located in? 🌍",
            'guest_capacity': f"{starter}how many guests your property can accommodate? 👥",
            'bedrooms': f"{starter}how many bedrooms your property has? 🛏️",
            'bathrooms': f"{starter}how many bathrooms your property has? 🚿",
            'nightly_rate': f"{starter}what price you'd like to charge per night? 💰",
            'amenities': f"{starter}what amenities your property offers? Like wifi, kitchen, parking, pool, etc.? ⭐",
            'title': f"{starter}what you'd like to call your property listing? ✨",
            'description': f"{starter}what makes your property special? 📝",
            'house_rules': f"{starter}your house rules? Do you allow smoking or pets? 🏠"
        }
        
        return questions.get(field_name, f"{starter}{field_name}? 🏡")
    
    def extract_property_data(self, text: str, conversation_context: Dict) -> Dict[str, Any]:
        """Main extraction method that combines all NLP capabilities."""
        entities = self.extract_entities(text)
        intent = self.classify_intent(text)
        sentiment = self.analyze_sentiment(text)
        
        # Convert entities to extracted data with validation
        extracted_data = {}
        for entity in entities:
            if entity.label in ['property_type', 'location', 'capacity', 'bedrooms', 'bathrooms', 'price', 'amenities', 'city', 'country']:
                # Clean and normalize the extracted value
                value = self._normalize_entity_value(entity.text, entity.label)
                if value:
                    # For city and country, validate before adding
                    if entity.label == 'city':
                        is_valid, validated_value = self.validate_city(value)
                        if is_valid:
                            extracted_data[entity.label] = validated_value
                    elif entity.label == 'country':
                        is_valid, validated_value = self.validate_country(value)
                        if is_valid:
                            extracted_data[entity.label] = validated_value
                    else:
                        extracted_data[entity.label] = value
        
        # Determine if we should move to next question
        missing_fields = conversation_context.get('missing_fields', [])
        should_move = self.should_move_to_next_question(extracted_data, missing_fields)
        
        return {
            'extracted_entities': [{'text': e.text, 'label': e.label, 'confidence': e.confidence} for e in entities],
            'user_intent': intent.intent,
            'sentiment_analysis': {
                'sentiment': sentiment.sentiment,
                'confidence': sentiment.confidence
            },
            'extracted_data': extracted_data,
            'should_move_to_next': should_move,
            'follow_up_question': self.generate_follow_up_question(
                missing_fields,
                intent,
                sentiment,
                conversation_context.get('extraction_attempts', 0),
                extracted_data
            )
        }
    
    def _normalize_entity_value(self, text: str, label: str) -> str:
        """Normalize extracted entity values."""
        text = text.strip()
        
        if label == 'price':
            # Extract just the number from price
            match = re.search(r'(\d+(?:,\d{3})*(?:\.\d{2})?)', text)
            return match.group(1) if match else text
        
        elif label in ['bedrooms', 'bathrooms', 'capacity']:
            # Extract just the number
            match = re.search(r'(\d+)', text)
            return match.group(1) if match else text
        
        elif label == 'property_type':
            # Normalize property types
            text_lower = text.lower()
            if 'house' in text_lower:
                return 'house'
            elif 'apartment' in text_lower or 'apt' in text_lower:
                return 'apartment'
            elif 'villa' in text_lower:
                return 'villa'
            elif 'cabin' in text_lower:
                return 'cabin'
            elif 'loft' in text_lower:
                return 'loft'
            else:
                return text
        
        elif label in ['city', 'country']:
            # Return the text as-is for validation
            return text
        
        return text 
