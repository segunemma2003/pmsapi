"""
NLP Utilities for Enhanced Property Extraction
This module provides NLP capabilities for the property creation flow.
"""

import re
import logging
import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Try to import NLP libraries (optional)
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    pipeline = None

logger = logging.getLogger(__name__)

@dataclass
class ExtractedEntity:
    """Represents an extracted entity with confidence score"""
    value: Any
    confidence: float
    entity_type: str
    field_mapping: str
    context: str = ""

@dataclass
class UserIntent:
    """Represents user intent with confidence score"""
    primary_intent: str
    confidence: float
    secondary_intents: List[str] = None

@dataclass
class SentimentAnalysis:
    """Represents sentiment analysis results"""
    frustration_level: float
    confidence_level: float
    engagement_level: float
    overall_sentiment: str

# Property-specific entity patterns
PROPERTY_ENTITIES = {
    'PROPERTY_TYPE': {
        'patterns': ['house', 'apartment', 'villa', 'cabin', 'loft', 'condo', 'townhouse', 'studio'],
        'field_mapping': 'property_type'
    },
    'LOCATION': {
        'patterns': ['city', 'town', 'village', 'neighborhood', 'district', 'area'],
        'field_mapping': 'city'
    },
    'CAPACITY': {
        'patterns': ['guests', 'people', 'persons', 'visitors', 'accommodate', 'fit'],
        'field_mapping': 'max_guests'
    },
    'ROOMS': {
        'patterns': ['bedrooms', 'bathrooms', 'beds', 'rooms', 'br', 'ba'],
        'field_mapping': 'bedrooms'
    },
    'AMENITY': {
        'patterns': ['wifi', 'kitchen', 'parking', 'pool', 'gym', 'tv', 'air conditioning', 'washer', 'dryer'],
        'field_mapping': 'amenities'
    },
    'PRICE': {
        'patterns': ['dollars', 'per night', 'rate', 'cost', 'price', '$'],
        'field_mapping': 'display_price'
    },
    'POLICY': {
        'patterns': ['smoking', 'pets', 'events', 'children', 'parties'],
        'field_mapping': 'smoking_allowed'
    }
}

# Intent classification patterns
INTENT_PATTERNS = {
    'PROVIDE_PROPERTY_INFO': [
        'house', 'apartment', 'property', 'place', 'home', 'listing'
    ],
    'PROVIDE_LOCATION': [
        'located', 'address', 'city', 'town', 'neighborhood', 'area'
    ],
    'PROVIDE_PRICING': [
        'price', 'rate', 'cost', 'dollars', 'per night', 'charge'
    ],
    'PROVIDE_AMENITIES': [
        'wifi', 'kitchen', 'parking', 'pool', 'gym', 'amenities', 'features'
    ],
    'PROVIDE_POLICIES': [
        'smoking', 'pets', 'events', 'children', 'rules', 'policies'
    ],
    'CLARIFICATION_REQUEST': [
        'what do you mean', 'clarify', 'explain', 'not sure', 'confused'
    ],
    'COMPLETION_REQUEST': [
        'done', 'finished', 'complete', 'ready', 'submit'
    ]
}

class NLPProcessor:
    """Main NLP processing class with enhanced capabilities"""
    
    def __init__(self):
        self.nlp = None
        self.sentiment_analyzer = None
        
        # Initialize spaCy if available
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("spaCy model loaded successfully")
            except OSError:
                logger.warning("spaCy model not found. Install with: python -m spacy download en_core_web_sm")
        
        # Initialize sentiment analyzer if available
        if TRANSFORMERS_AVAILABLE:
            try:
                self.sentiment_analyzer = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
                logger.info("Sentiment analyzer loaded successfully")
            except Exception as e:
                logger.warning(f"Sentiment analyzer not available: {e}")
    
    def extract_entities(self, text: str, previous_data: Dict = None) -> Dict[str, ExtractedEntity]:
        """Enhanced entity extraction using multiple methods"""
        entities = {}
        
        # Method 1: spaCy NER
        if self.nlp:
            doc = self.nlp(text.lower())
            for ent in doc.ents:
                if ent.label_ in ['GPE', 'LOC', 'ORG']:  # Location entities
                    entities['location'] = ExtractedEntity(
                        value=ent.text,
                        confidence=0.8,
                        entity_type='LOCATION',
                        field_mapping='city',
                        context=ent.text
                    )
        
        # Method 2: Pattern-based extraction
        pattern_entities = self._extract_by_patterns(text)
        entities.update(pattern_entities)
        
        # Method 3: Context-aware number extraction
        number_entities = self._extract_numbers_with_context(text, previous_data)
        entities.update(number_entities)
        
        return entities
    
    def _extract_by_patterns(self, text: str) -> Dict[str, ExtractedEntity]:
        """Extract entities using predefined patterns"""
        entities = {}
        text_lower = text.lower()
        
        # Property type extraction
        for prop_type in PROPERTY_ENTITIES['PROPERTY_TYPE']['patterns']:
            if prop_type in text_lower:
                entities['property_type'] = ExtractedEntity(
                    value=prop_type,
                    confidence=0.9,
                    entity_type='PROPERTY_TYPE',
                    field_mapping='property_type'
                )
                break
        
        # Amenities extraction
        amenities = []
        for amenity in PROPERTY_ENTITIES['AMENITY']['patterns']:
            if amenity in text_lower:
                amenities.append(amenity)
        
        if amenities:
            entities['amenities'] = ExtractedEntity(
                value=amenities,
                confidence=0.85,
                entity_type='AMENITY',
                field_mapping='amenities'
            )
        
        # Policy extraction
        for policy in PROPERTY_ENTITIES['POLICY']['patterns']:
            if policy in text_lower:
                # Determine if it's allowed or not
                is_allowed = self._determine_policy_allowance(text_lower, policy)
                field_name = f"{policy}_allowed" if policy != 'children' else 'children_welcome'
                
                entities[field_name] = ExtractedEntity(
                    value=is_allowed,
                    confidence=0.8,
                    entity_type='POLICY',
                    field_mapping=field_name
                )
        
        return entities
    
    def _extract_numbers_with_context(self, text: str, previous_data: Dict = None) -> Dict[str, ExtractedEntity]:
        """Extract numbers with context resolution to avoid ambiguity"""
        entities = {}
        numbers = re.findall(r'\b(\d+)\b', text)
        
        for number in numbers:
            number_int = int(number)
            context = self._analyze_number_context(text, number, previous_data)
            
            if context['type'] == 'price':
                entities['display_price'] = ExtractedEntity(
                    value=number_int,
                    confidence=context['confidence'],
                    entity_type='PRICE',
                    field_mapping='display_price'
                )
            elif context['type'] == 'capacity':
                entities['max_guests'] = ExtractedEntity(
                    value=number_int,
                    confidence=context['confidence'],
                    entity_type='CAPACITY',
                    field_mapping='max_guests'
                )
            elif context['type'] == 'rooms':
                if 'bedroom' in context['context']:
                    entities['bedrooms'] = ExtractedEntity(
                        value=number_int,
                        confidence=context['confidence'],
                        entity_type='ROOMS',
                        field_mapping='bedrooms'
                    )
                elif 'bathroom' in context['context']:
                    entities['bathrooms'] = ExtractedEntity(
                        value=number_int,
                        confidence=context['confidence'],
                        entity_type='ROOMS',
                        field_mapping='bathrooms'
                    )
            elif context['type'] == 'address':
                # Don't extract as capacity/price if it's part of address
                continue
        
        return entities
    
    def _analyze_number_context(self, text: str, number: str, previous_data: Dict = None) -> Dict:
        """Analyze the context around a number to determine its type"""
        text_lower = text.lower()
        number_int = int(number)
        
        # Price indicators
        price_indicators = ['dollars', 'per night', 'rate', 'cost', 'price', '$', 'usd']
        if any(indicator in text_lower for indicator in price_indicators):
            return {'type': 'price', 'confidence': 0.9, 'context': 'price'}
        
        # Capacity indicators
        capacity_indicators = ['guests', 'people', 'persons', 'accommodate', 'fit', 'capacity']
        if any(indicator in text_lower for indicator in capacity_indicators):
            return {'type': 'capacity', 'confidence': 0.85, 'context': 'capacity'}
        
        # Room indicators
        room_indicators = ['bedrooms', 'bathrooms', 'beds', 'rooms', 'br', 'ba']
        if any(indicator in text_lower for indicator in room_indicators):
            return {'type': 'rooms', 'confidence': 0.8, 'context': text_lower}
        
        # Address indicators (don't extract as capacity/price)
        address_indicators = ['street', 'avenue', 'road', 'drive', 'lane', 'boulevard']
        if any(indicator in text_lower for indicator in address_indicators):
            return {'type': 'address', 'confidence': 0.7, 'context': 'address'}
        
        # Default based on number range
        if 1 <= number_int <= 20:
            return {'type': 'capacity', 'confidence': 0.6, 'context': 'default_capacity'}
        elif 20 <= number_int <= 1000:
            return {'type': 'price', 'confidence': 0.6, 'context': 'default_price'}
        
        return {'type': 'unknown', 'confidence': 0.3, 'context': 'unknown'}
    
    def _determine_policy_allowance(self, text: str, policy: str) -> bool:
        """Determine if a policy is allowed or not based on context"""
        text_lower = text.lower()
        
        # Negative indicators
        negative_indicators = ['no ', 'not ', 'not allowed', 'prohibited', 'forbidden', 'banned']
        if any(indicator in text_lower for indicator in negative_indicators):
            return False
        
        # Positive indicators
        positive_indicators = ['allowed', 'welcome', 'ok', 'fine', 'permitted']
        if any(indicator in text_lower for indicator in positive_indicators):
            return True
        
        # Default based on policy type
        if policy in ['smoking', 'pets', 'events']:
            return False  # Default to not allowed for these
        elif policy == 'children':
            return True   # Default to allowed for children
        
        return True
    
    def classify_intent(self, text: str) -> UserIntent:
        """Classify user intent from text"""
        text_lower = text.lower()
        
        # Calculate similarity scores for each intent
        intent_scores = {}
        for intent, patterns in INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if pattern in text_lower:
                    score += 1
            intent_scores[intent] = score / len(patterns)
        
        # Find primary intent
        primary_intent = max(intent_scores.items(), key=lambda x: x[1])
        
        # Find secondary intents (scores > 0.3)
        secondary_intents = [intent for intent, score in intent_scores.items() 
                           if score > 0.3 and intent != primary_intent[0]]
        
        return UserIntent(
            primary_intent=primary_intent[0],
            confidence=primary_intent[1],
            secondary_intents=secondary_intents
        )
    
    def analyze_sentiment(self, text: str) -> SentimentAnalysis:
        """Analyze user sentiment and engagement"""
        text_lower = text.lower()
        
        # Frustration indicators
        frustration_indicators = [
            'already told you', 'said that', 'mentioned', 'repeated',
            'don\'t understand', 'confused', 'frustrated', 'annoyed',
            'tired of', 'again', 'still', 'yet'
        ]
        
        frustration_score = sum(1 for indicator in frustration_indicators if indicator in text_lower)
        frustration_level = min(frustration_score / len(frustration_indicators), 1.0)
        
        # Engagement indicators
        engagement_indicators = [
            'great', 'awesome', 'perfect', 'love', 'like', 'excellent',
            'wonderful', 'amazing', 'fantastic', 'super', 'cool'
        ]
        
        engagement_score = sum(1 for indicator in engagement_indicators if indicator in text_lower)
        engagement_level = min(engagement_score / len(engagement_indicators), 1.0)
        
        # Confidence indicators
        confidence_indicators = [
            'sure', 'certain', 'definitely', 'absolutely', 'of course',
            'yes', 'correct', 'right', 'exactly'
        ]
        
        confidence_score = sum(1 for indicator in confidence_indicators if indicator in text_lower)
        confidence_level = min(confidence_score / len(confidence_indicators), 1.0)
        
        # Overall sentiment using external analyzer if available
        if self.sentiment_analyzer:
            try:
                sentiment_result = self.sentiment_analyzer(text)[0]
                overall_sentiment = sentiment_result['label']
            except:
                overall_sentiment = 'NEUTRAL'
        else:
            overall_sentiment = 'NEUTRAL'
        
        return SentimentAnalysis(
            frustration_level=frustration_level,
            confidence_level=confidence_level,
            engagement_level=engagement_level,
            overall_sentiment=overall_sentiment
        )
    
    def generate_follow_up_question(self, 
                                  extracted_entities: Dict[str, ExtractedEntity],
                                  user_intent: UserIntent,
                                  sentiment: SentimentAnalysis,
                                  missing_fields: List[Dict],
                                  completion_percentage: float) -> str:
        """Generate contextually appropriate follow-up questions"""
        
        # If user is frustrated, be more apologetic
        if sentiment.frustration_level > 0.5:
            apology_prefix = "I'm really sorry, but "
        elif sentiment.frustration_level > 0.2:
            apology_prefix = "Sorry, I didn't get "
        else:
            apology_prefix = "Excuse me, I didn't capture "
        
        # Prioritize missing fields
        critical_fields = [field for field in missing_fields if field.get('weight', 1) >= 1]
        
        if not critical_fields:
            return "Perfect! It looks like we have all the information we need. Would you like to review your property listing?"
        
        field = critical_fields[0]
        field_name = field['name'].lower()
        
        # Generate field-specific questions
        questions = {
            'property type': f"{apology_prefix}what type of property you're listing. Could you tell me if it's a house, apartment, villa, or something else? 🏠",
            'city': f"{apology_prefix}the city. Where is your property located? 🌆",
            'country': f"{apology_prefix}the country. Which country is your property in? 🌍",
            'max guests': f"{apology_prefix}how many guests your property can accommodate. Could you tell me the maximum number of guests? 👥",
            'bedrooms': f"{apology_prefix}the bedroom count. How many bedrooms does your property have? 🛏️",
            'bathrooms': f"{apology_prefix}the bathroom count. How many bathrooms does your property have? 🚿",
            'display price': f"{apology_prefix}your nightly rate. What price would you like to charge per night? 💰",
            'amenities': f"{apology_prefix}what amenities your property offers. Could you list the amenities like wifi, kitchen, parking, etc.? ⭐",
            'title': f"{apology_prefix}what you'd like to call your property. Could you suggest a title for your listing? ✨",
            'description': f"{apology_prefix}the description. Could you tell me more about your property and what makes it special? 📝"
        }
        
        return questions.get(field_name, f"{apology_prefix}the {field_name}. Could you please clarify? 🏡")

# Initialize global NLP processor
nlp_processor = NLPProcessor() 
