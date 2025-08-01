"""
NLP Utilities for Enhanced Property Extraction
This module provides advanced NLP capabilities for better information extraction.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

# Conditional imports for NLP packages
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    pipeline = None

try:
    import nltk
    from nltk.sentiment import SentimentIntensityAnalyzer
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    nltk = None
    SentimentIntensityAnalyzer = None

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
if NLTK_AVAILABLE and nltk:
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
        # Initialize spaCy model
        if SPACY_AVAILABLE and spacy:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                # Fallback if model not available
                self.nlp = None
                print("Warning: spaCy model not available. Using fallback extraction.")
        else:
            self.nlp = None
            print("Warning: spaCy not available. Using fallback extraction.")
        
        # Initialize sentiment analyzer
        if NLTK_AVAILABLE and SentimentIntensityAnalyzer:
            try:
                self.sentiment_analyzer = SentimentIntensityAnalyzer()
            except Exception:
                self.sentiment_analyzer = None
                print("Warning: NLTK sentiment analyzer not available.")
        else:
            self.sentiment_analyzer = None
            print("Warning: NLTK not available. Sentiment analysis disabled.")
        
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
            'la quinta', 'rancho mirage', 'desert hot springs', 'lagos', 'abuja', 'kano', 'ibadan',
            'port harcourt', 'benin city', 'maiduguri', 'zaria', 'abeokuta', 'jos', 'ilorin',
            'oyo', 'enugu', 'kaduna', 'warri', 'calabar', 'akure', 'bauchi', 'katsina', 'gombe',
            'tokyo', 'osaka', 'kyoto', 'yokohama', 'nagoya', 'sapporo', 'kobe', 'fukuoka', 'kawasaki',
            'saitama', 'hiroshima', 'sendai', 'chiba', 'kitakyushu', 'sakai', 'niigata', 'hamamatsu',
            'kumamoto', 'sagamihara', 'shizuoka', 'okayama', 'kagoshima', 'funabashi', 'higashiosaka',
            'hachioji', 'matsuyama', 'machida', 'nagano', 'toyonaka', 'ichinomiya', 'nara', 'toyohashi',
            'toyota', 'gifu', 'himeji', 'kawaguchi', 'takamatsu', 'utsunomiya', 'asahikawa', 'iwaki',
            'nagasaki', 'suita', 'nishinomiya', 'hamamatsu', 'kumagaya', 'kawagoe', 'hirakata', 'akita',
            'yokkaichi', 'fukushima', 'maebashi', 'ibaraki', 'shizuoka', 'okazaki', 'koriyama', 'kakogawa',
            'tokorozawa', 'akashi', 'kasugai', 'aomori', 'yokosuka', 'morioka', 'takasaki', 'miyazaki',
            'koshigaya', 'kakamigahara', 'sakura', 'akishima', 'minato', 'shinjuku', 'shibuya', 'setagaya',
            'suginami', 'toshima', 'taito', 'chiyoda', 'nerima', 'itabashi', 'ota', 'adachi', 'katsushika',
            'edogawa', 'sumida', 'koto', 'chuo', 'meguro', 'nakano', 'bunkyo', 'toshima', 'kita', 'arakawa'
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
        
        # Property-specific entity patterns
        self.PROPERTY_ENTITIES = {
            'property_type': [
                r'\b(house|apartment|villa|cabin|loft|condo|townhouse|studio|penthouse|chalet|cottage|bungalow|mansion|duplex|triplex)\b',
                r'\b(single family|multi family|residential|commercial|vacation home|beach house|mountain cabin)\b',
                r'\b(it\'s|it is|this is|that is|we have|i have)\s+(?:a\s+)?(small\s+|large\s+|big\s+|tiny\s+)?(house|apartment|villa|cabin|loft|condo|townhouse|studio|penthouse|chalet|cottage|bungalow|mansion|duplex|triplex)\b',
                r'\b(my|our|the)\s+(?:property|place|home|listing)\s+(?:is\s+)?(?:a\s+)?(small\s+|large\s+|big\s+|tiny\s+)?(house|apartment|villa|cabin|loft|condo|townhouse|studio|penthouse|chalet|cottage|bungalow|mansion|duplex|triplex)\b',
                # More direct patterns for property types
                r'\b(?:a\s+)?(house|apartment|villa|cabin|loft|condo|townhouse|studio|penthouse|chalet|cottage|bungalow|mansion|duplex|triplex)\b',
                r'\b(house|apartment|villa|cabin|loft|condo|townhouse|studio|penthouse|chalet|cottage|bungalow|mansion|duplex|triplex)\s+(?:for\s+rent|listing|property)\b',
                # Handle cases where user just says "house" or similar
                r'(?:^|\s)(house|apartment|villa|cabin|loft|condo|townhouse|studio|penthouse|chalet|cottage|bungalow|mansion|duplex|triplex)(?:\s|$|[.,!?])',
            ],
            'location': [
                r'\b(city|town|village|neighborhood|district|area|zone|region|state|province|country)\b',
                r'\b(downtown|uptown|suburb|rural|urban|coastal|mountain|lakefront|beachfront)\b'
            ],
            'neighborhood': [
                r'\b(phase\s+\d+)\b',
                r'\b(area\s+\d+)\b',
                r'\b(zone\s+\d+)\b',
                r'\b(district\s+\d+)\b',
                r'\b(block\s+\d+)\b',
                r'\b(lekki|victoria island|ikoyi|banana island|ajah|surulere|yaba|ikeja)\b'
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
                r'\b(rate|price|cost|charge)\s*(?:of|is|at)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\b',
                r'\b(\d+(?:,\d{3})*(?:\.\d{2})?)\s*\$?\s*(?:per night|nightly|daily)\b'
            ],
            'check_in_time': [
                r'\b(check.?in|checkin|arrival)\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}:\d{2})\b',
                r'\b(\d{1,2}:\d{2})\s*(?:check.?in|checkin|arrival)\b',
                r'\b(check.?in|checkin)\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2})\s*(?:am|pm|AM|PM)?\b'
            ],
            'check_out_time': [
                r'\b(check.?out|checkout|departure)\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}:\d{2})\b',
                r'\b(\d{1,2}:\d{2})\s*(?:check.?out|checkout|departure)\b',
                r'\b(check.?out|checkout)\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2})\s*(?:am|pm|AM|PM)?\b'
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
        
        # Method 0: Check if it's a known country first (cities shouldn't be countries)
        if text_lower in self.FALLBACK_COUNTRIES:
            return False, text  # It's a country, not a city
        
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
        
        # Method 5: Handle neighborhood/area names that might be mistaken for cities
        # Common patterns like "Phase 1", "Phase 2", etc. are often neighborhoods
        neighborhood_patterns = [
            r'\b(phase\s+\d+)\b',
            r'\b(area\s+\d+)\b',
            r'\b(zone\s+\d+)\b',
            r'\b(district\s+\d+)\b',
            r'\b(block\s+\d+)\b'
        ]
        
        for pattern in neighborhood_patterns:
            if re.search(pattern, text_lower):
                # This is likely a neighborhood, not a city
                return False, text
        
        # Method 6: Pattern matching for common city patterns
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
        
        # Method 0: Check if it's a known city first (countries shouldn't be cities)
        if text_lower in self.FALLBACK_CITIES:
            return False, text  # It's a city, not a country
        
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
                    # Debug logging for property type extraction
                    if entity_type == 'property_type':
                        print(f"Property type pattern matched: '{match.group()}' from text: '{text}'")
                    
                    # For property_type, extract the actual property type word
                    if entity_type == 'property_type':
                        # Find the property type word within the match
                        property_types = ['house', 'apartment', 'villa', 'cabin', 'loft', 'condo', 'townhouse', 'studio', 'penthouse', 'chalet', 'cottage', 'bungalow', 'mansion', 'duplex', 'triplex']
                        matched_text = match.group().lower()
                        
                        for prop_type in property_types:
                            if prop_type in matched_text:
                                print(f"Extracted property type: '{prop_type}' from match: '{matched_text}'")
                                entities.append(ExtractedEntity(
                                    text=prop_type,
                                    label=entity_type,
                                    confidence=0.9,
                                    start=match.start(),
                                    end=match.end()
                                ))
                                break
                    else:
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
        print(f"Extracting city/country from: '{text}'")
        
        # Enhanced patterns for natural language
        location_patterns = [
            # "in Japan and in the city of tokyo"
            r'\bin\s+([A-Za-z\s]+)\s+and\s+in\s+the\s+city\s+of\s+([A-Za-z\s]+)',
            # "in Japan, tokyo"
            r'\bin\s+([A-Za-z\s]+),\s*([A-Za-z\s]+)',
            # "Japan, tokyo"
            r'\b([A-Za-z\s]+),\s*([A-Za-z\s]+)',
            # "located in Japan and tokyo"
            r'\blocated\s+in\s+([A-Za-z\s]+)\s+and\s+([A-Za-z\s]+)',
            # "from Japan, city is tokyo"
            r'\bfrom\s+([A-Za-z\s]+),?\s+(?:city\s+is\s+)?([A-Za-z\s]+)',
        ]
        
        for pattern in location_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                potential_country = match.group(1).strip()
                potential_city = match.group(2).strip()
                
                print(f"Pattern matched - potential country: '{potential_country}', potential city: '{potential_city}'")
                
                # Validate country first
                is_valid_country, country_name = self.validate_country(potential_country)
                if is_valid_country:
                    entities.append(ExtractedEntity(
                        text=country_name,
                        label='country',
                        confidence=0.95,
                        start=match.start(1),
                        end=match.end(1)
                    ))
                    print(f"Valid country found: '{country_name}'")
                
                # Validate city
                is_valid_city, city_name = self.validate_city(potential_city)
                if is_valid_city:
                    entities.append(ExtractedEntity(
                        text=city_name,
                        label='city',
                        confidence=0.95,
                        start=match.start(2),
                        end=match.end(2)
                    ))
                    print(f"Valid city found: '{city_name}'")
        
        # If we found entities with enhanced patterns, return them
        if entities:
            return entities
        
        # First, look for "City, Country" pattern (most common format)
        city_country_pattern = r'\b([A-Za-z\s]+),\s*([A-Za-z\s]+)\b'
        matches = re.finditer(city_country_pattern, text, re.IGNORECASE)
        
        for match in matches:
            potential_city = match.group(1).strip()
            potential_country = match.group(2).strip()
            
            # Validate city
            is_valid_city, city_name = self.validate_city(potential_city)
            if is_valid_city:
                entities.append(ExtractedEntity(
                    text=city_name,
                    label='city',
                    confidence=0.95,
                    start=match.start(1),
                    end=match.end(1)
                ))
            
            # Validate country
            is_valid_country, country_name = self.validate_country(potential_country)
            if is_valid_country:
                entities.append(ExtractedEntity(
                    text=country_name,
                    label='country',
                    confidence=0.95,
                    start=match.start(2),
                    end=match.end(2)
                ))
        
        # If we found city/country pairs, don't process individual words to avoid duplicates
        if entities:
            return entities
        
        # Fallback: Look for individual city/country patterns
        words = text.split()
        processed_words = set()  # Track processed words to avoid duplicates
        
        for i, word in enumerate(words):
            word_clean = re.sub(r'[^\w\s]', '', word).strip().lower()
            if not word_clean or word_clean in processed_words:
                continue
            
            # Check for country first (prioritize countries over cities)
            is_valid_country, country_name = self.validate_country(word_clean)
            if is_valid_country:
                entities.append(ExtractedEntity(
                    text=country_name,
                    label='country',
                    confidence=0.9,
                    start=text.lower().find(word_clean),
                    end=text.lower().find(word_clean) + len(word_clean)
                ))
                processed_words.add(word_clean)
                print(f"Individual country found: '{country_name}'")
                continue
            
            # Check for city
            is_valid_city, city_name = self.validate_city(word_clean)
            if is_valid_city:
                entities.append(ExtractedEntity(
                    text=city_name,
                    label='city',
                    confidence=0.9,
                    start=text.lower().find(word_clean),
                    end=text.lower().find(word_clean) + len(word_clean)
                ))
                processed_words.add(word_clean)
                print(f"Individual city found: '{city_name}'")
        
        # Extract multi-word patterns (like "Lekki Phase 1")
        multi_word_patterns = [
            (r'\b(lekki\s+phase\s+\d+)\b', 'neighborhood'),
            (r'\b(victoria\s+island)\b', 'neighborhood'),
            (r'\b(banana\s+island)\b', 'neighborhood'),
            (r'\b(phase\s+\d+)\b', 'neighborhood'),
            (r'\b(area\s+\d+)\b', 'neighborhood'),
            (r'\b(zone\s+\d+)\b', 'neighborhood'),
        ]
        
        for pattern, label in multi_word_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append(ExtractedEntity(
                    text=match.group(1).title(),
                    label=label,
                    confidence=0.95,
                    start=match.start(),
                    end=match.end()
                ))
        
        print(f"Final extracted entities: {[(e.text, e.label) for e in entities]}")
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
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(dollars?|USD|per night)', 'price'),
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*\$?\s*(?:per night|nightly|daily)', 'price'),
            # Timing patterns
            (r'\b(check.?in|checkin|arrival)\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}):(\d{2})\b', 'check_in_time'),
            (r'\b(\d{1,2}):(\d{2})\s*(?:check.?in|checkin|arrival)\b', 'check_in_time'),
            (r'\b(check.?out|checkout|departure)\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}):(\d{2})\b', 'check_out_time'),
            (r'\b(\d{1,2}):(\d{2})\s*(?:check.?out|checkout|departure)\b', 'check_out_time'),
        ]
        
        for pattern, label in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if label in ['check_in_time', 'check_out_time']:
                    # Handle time format
                    if len(match.groups()) >= 2:
                        hour = match.group(-2)
                        minute = match.group(-1)
                        time_value = f"{hour}:{minute}"
                    else:
                        time_value = match.group(1)
                else:
                    time_value = match.group()
                
                entities.append(ExtractedEntity(
                    text=time_value,
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
        if not self.sentiment_analyzer:
            # Fallback sentiment analysis when NLTK is not available
            text_lower = text.lower()
            
            # Simple keyword-based sentiment detection
            positive_words = ['good', 'great', 'excellent', 'perfect', 'love', 'like', 'yes', 'sure', 'ok', 'okay']
            negative_words = ['bad', 'terrible', 'hate', 'no', 'not', 'never', 'wrong', 'error', 'problem']
            
            positive_count = sum(1 for word in positive_words if word in text_lower)
            negative_count = sum(1 for word in negative_words if word in text_lower)
            
            if positive_count > negative_count:
                sentiment = 'positive'
                confidence = 0.6
            elif negative_count > positive_count:
                sentiment = 'negative'
                confidence = 0.6
            else:
                sentiment = 'neutral'
                confidence = 0.5
            
            return SentimentAnalysis(
                sentiment=sentiment,
                confidence=confidence,
                compound_score=0.0
            )
        
        # Use NLTK sentiment analyzer
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
        meaningful_fields = ['property_type', 'city', 'country', 'neighborhood', 'bedrooms', 'bathrooms', 'capacity', 'price', 'check_in_time', 'check_out_time']
        extracted_meaningful = any(field in extracted_data for field in meaningful_fields)
        
        # Also check if we have enough data to move forward
        if extracted_meaningful:
            # If we have at least 2 meaningful fields, definitely move forward
            meaningful_count = sum(1 for field in meaningful_fields if field in extracted_data)
            if meaningful_count >= 2:
                return True
            
            # If we have at least one high-confidence field, move forward
            high_confidence_fields = ['property_type', 'bedrooms', 'bathrooms', 'price', 'check_in_time', 'check_out_time']
            if any(field in extracted_data for field in high_confidence_fields):
                return True
        
        return extracted_meaningful
    
    def generate_follow_up_question(self, 
                                  missing_fields: List[Dict], 
                                  user_intent: UserIntent,
                                  sentiment: SentimentAnalysis,
                                  extraction_attempts: int = 0,
                                  extracted_data: Dict = None) -> str:
        """Generate contextually appropriate follow-up questions."""
        
        # Fields to exclude from follow-up questions (handled by UI components)
        excluded_fields = {
            'images', 'amenities', 'smoking_allowed', 'pets_allowed', 
            'events_allowed', 'children_welcome', 'house_rules',
            'trust_level_1_discount', 'trust_level_2_discount', 'trust_level_3_discount',
            'trust_level_4_discount', 'trust_level_5_discount'
        }
        
        # Filter out excluded fields
        filtered_missing_fields = [
            field for field in missing_fields 
            if field.get('key', '').lower() not in excluded_fields
        ]
        
        if not filtered_missing_fields:
            return "Great! I think I have all the essential information I need. Is there anything else you'd like to add?"
        
        # Use filtered fields for the rest of the logic
        missing_fields = filtered_missing_fields
        
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
        
        # If we extracted significant data, acknowledge it and move forward
        if extracted_data and len(extracted_data) >= 2:
            # We have good data, move to next question
            if len(missing_fields) > 1:
                next_field = missing_fields[1]
        
        # Handle frustration
        if sentiment.sentiment == 'negative' or user_intent.intent == 'frustration':
            if extraction_attempts >= 3:
                return "I apologize for the confusion. Let me ask you directly: what type of property are you listing?"
            else:
                return "I understand this might be frustrating. Let me try a different approach. Could you tell me more about your property?"
        
        field_name = next_field['name'].lower()
        
        # Apologetic starters based on sentiment
        if sentiment.sentiment == 'negative':
            starter = "I need to know: "
        elif extraction_attempts > 0:
            starter = "I still need: "
        else:
            starter = "What is your "
        
        # Field-specific questions with improved flow
        questions = {
            'property_type': f"{starter}what type of property you're listing? (house, apartment, villa, cabin, loft)",
            'location': f"{starter}where your property is located?",
            'city': f"{starter}which city is your property in?",
            'country': f"{starter}which country is your property located in?",
            'guest_capacity': f"{starter}how many guests your property can accommodate?",
            'bedrooms': f"{starter}how many bedrooms your property has?",
            'bathrooms': f"{starter}how many bathrooms your property has?",
            'nightly_rate': f"{starter}what price you'd like to charge per night?",
            'check_in_time': f"{starter}what is your check-in time?",
            'check_out_time': f"{starter}what is your check-out time?",
            'title': f"{starter}what you'd like to call your property listing?",
            'description': f"{starter}what makes your property special?"
        }
        
        return questions.get(field_name, f"{starter}{field_name}? 🏡")
    
    def extract_property_data(self, text: str, conversation_context: Dict = None) -> Dict[str, Any]:
        """Extract property data from text with conversation flow."""
        print(f"NLP extracting from text: '{text}'")
        
        entities = self.extract_entities(text)
        print(f"NLP extracted entities: {[(e.text, e.label) for e in entities]}")
        
        # Convert entities to extracted data with validation
        extracted_data = {}
        for entity in entities:
            if entity.label in ['property_type', 'location', 'capacity', 'bedrooms', 'bathrooms', 'price', 'check_in_time', 'check_out_time', 'city', 'country', 'neighborhood']:
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
                    elif entity.label == 'neighborhood':
                        # Neighborhoods don't need validation, just add them
                        extracted_data[entity.label] = value
                    else:
                        extracted_data[entity.label] = value
        
        print(f"NLP processed data: {extracted_data}")
        
        # Initialize conversation context if not provided
        if conversation_context is None:
            conversation_context = {}
        
        # Analyze user intent and sentiment
        intent = self.classify_intent(text)
        sentiment = self.analyze_sentiment(text)
        
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
        
        elif label in ['check_in_time', 'check_out_time']:
            # Normalize time format
            time_match = re.search(r'(\d{1,2}):(\d{2})', text)
            if time_match:
                hour = time_match.group(1)
                minute = time_match.group(2)
                return f"{hour}:{minute}"
            return text
        
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
